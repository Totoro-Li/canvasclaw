"""Global hybrid retrieval over ALL lectures' unit-chunks (full semester).

Loads every lecture's units.json (via data/lectures.json manifest), concatenates
their units + chunks, embeds chunks once with bge (GPU), and serves:
  - search_candidates(query) -> rank UNITS across all lectures (orchestrator routing)
  - search_chunks(query, unit_ids) -> top chunks within chosen units (worker RAG)

Chinese-friendly BM25 (char-bigram + ascii-word). Embeddings are local (no creds).
At semester scale (~hundreds of units / few-thousand chunks) numpy dot is sub-ms.
"""
from __future__ import annotations
import json, re
import numpy as np
from typing import List, Dict, Tuple, Optional
from config.config import settings


def _tok(s: str) -> List[str]:
    s = s.lower()
    toks = re.findall(r"[a-z0-9]+", s)
    han = re.findall(r"[一-鿿]", s)
    toks += ["".join(p) for p in zip(han, han[1:])] or han
    return toks or ["∅"]


def _minmax(x: np.ndarray) -> np.ndarray:
    if x.size == 0:
        return x
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


class LectureIndex:
    def __init__(self, units, chunks, lectures, emb=None):
        self.units = units
        self.unit_by_id = {u["unit_id"]: u for u in units}
        self.chunks = chunks
        self.lectures = lectures
        self.lecture_by_id = {l["lecture_id"]: l for l in lectures}
        self.emb = emb
        from rank_bm25 import BM25Okapi
        self._bm25 = BM25Okapi([_tok(c["text"]) for c in chunks]) if chunks else None

    # ---------- build / persist ----------
    @classmethod
    def _collect(cls):
        import os
        exclude_slide = bool(os.environ.get("EXCLUDE_SLIDE_CHUNKS"))   # ablation: drop slide-OCR chunks
        man = json.loads(settings.MANIFEST.read_text(encoding="utf-8"))["lectures"]
        units, chunks = [], []
        for lec in man:
            uf = settings.lec_units(lec["lecture_id"])
            if not uf.exists():
                continue
            d = json.loads(uf.read_text(encoding="utf-8"))
            cks = d["chunks"]
            if exclude_slide:
                cks = [c for c in cks if c.get("source") != "slide"]
            units.extend(d["units"]); chunks.extend(cks)
        return man, units, chunks

    @classmethod
    def build(cls) -> "LectureIndex":
        from engine import llm
        man, units, chunks = cls._collect()
        emb = np.asarray(llm.embed([c["text"] for c in chunks]), dtype="float32") if chunks \
            else np.zeros((0, 512), "float32")
        settings.INDEX_DIR.mkdir(parents=True, exist_ok=True)
        np.save(settings.INDEX_DIR / "emb.npy", emb)
        (settings.INDEX_DIR / "store.json").write_text(
            json.dumps({"units": units, "chunks": chunks, "lectures": man}, ensure_ascii=False),
            encoding="utf-8")
        return cls(units, chunks, man, emb)

    @classmethod
    def load(cls) -> "LectureIndex":
        s = json.loads((settings.INDEX_DIR / "store.json").read_text(encoding="utf-8"))
        emb = np.load(settings.INDEX_DIR / "emb.npy")
        return cls(s["units"], s["chunks"], s.get("lectures", []), emb)

    # ---------- scoring ----------
    def _chunk_scores(self, query: str) -> np.ndarray:
        from engine import llm
        qv = np.asarray(llm.embed([query], is_query=True), dtype="float32")[0]
        vec = self.emb @ qv if self.emb.size else np.zeros(len(self.chunks))
        bm = np.asarray(self._bm25.get_scores(_tok(query))) if self._bm25 else np.zeros(len(self.chunks))
        a = settings.HYBRID_ALPHA
        return a * _minmax(vec) + (1 - a) * _minmax(bm)

    def search_candidates(self, query: str, k: Optional[int] = None) -> List[Tuple[str, float]]:
        """Rank UNITS (across all lectures) by best-matching chunk + title/summary hit."""
        k = k or settings.CANDIDATE_TOP_K
        cs = self._chunk_scores(query)
        best: Dict[str, float] = {}
        for c, s in zip(self.chunks, cs):
            best[c["unit_id"]] = max(best.get(c["unit_id"], 0.0), float(s))
        qt = set(_tok(query))
        for u in self.units:
            hit = len(qt & set(_tok(u.get("title", "") + u.get("summary", "") + u.get("lecture_title", ""))))
            if hit:
                best[u["unit_id"]] = best.get(u["unit_id"], 0.0) + 0.05 * hit
        return sorted(best.items(), key=lambda x: x[1], reverse=True)[:k]

    def search_chunks(self, query: str, unit_ids: List[str], k: Optional[int] = None) -> List[dict]:
        k = k or settings.TOP_K_CHUNKS
        cs = self._chunk_scores(query)
        keep = [(c, float(s)) for c, s in zip(self.chunks, cs) if c["unit_id"] in set(unit_ids)]
        keep.sort(key=lambda x: x[1], reverse=True)
        out = []
        for c, s in keep[:k]:
            d = dict(c); d["score"] = round(s, 4); out.append(d)
        return out

    def candidate_evidence(self, query: str, unit_ids: List[str]) -> Dict[str, str]:
        """Best-matching chunk text per candidate unit (so the router routes on real
        content, not weak provisional titles). One embed for all units."""
        cs = self._chunk_scores(query)
        uset, best = set(unit_ids), {}
        for c, s in zip(self.chunks, cs):
            if c["unit_id"] in uset and float(s) > best.get(c["unit_id"], (-1.0, ""))[0]:
                best[c["unit_id"]] = (float(s), c["text"])
        return {u: best.get(u, (0.0, ""))[1] for u in unit_ids}

    def unit(self, unit_id: str) -> dict:
        return self.unit_by_id[unit_id]

    def lecture(self, lecture_id: str) -> dict:
        return self.lecture_by_id.get(lecture_id, {})


if __name__ == "__main__":
    import sys
    idx = LectureIndex.build()
    print(f"[index] {len(idx.lectures)} lectures, {len(idx.units)} units, "
          f"{len(idx.chunks)} chunks, emb={idx.emb.shape}")
    q = sys.argv[1] if len(sys.argv) > 1 else "什么是检索增强？"
    print(f"\n[query] {q}\ncandidate units:")
    for uid, sc in idx.search_candidates(q, 5):
        u = idx.unit(uid)
        print(f"  {uid}  {sc:.3f}  [{u.get('lecture_id')}] {u['title'][:34]}")
