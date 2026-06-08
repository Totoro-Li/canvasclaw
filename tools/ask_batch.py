#!/usr/bin/env python3
"""Batch query runner for CanvasClaw evaluation.

Loads the engine ONCE, runs a list of queries, and for every citation it
AUTO-VERIFIES grounding against the cited lecture's ASR transcript:
  - quote_grounded : the cited quote actually appears in that lecture's transcript
  - ts_delta_sec   : |citation.start_sec - matched-segment.start| (timestamp accuracy)

Usage:
  python tools/ask_batch.py --in questions.json --out results.json
  # questions.json = [{"id","query","expected_lecture"(opt),"kind"(opt)}, ...]
"""
from __future__ import annotations
import json, re, sys, time, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import settings
from engine.agent import CanvasClaw

_norm = lambda s: re.sub(r"[\s，。、；：,.!?！？\-—…·\"'《》()（）]", "", (s or "")).lower()

_TX_CACHE: dict = {}
def _transcript(lid: str):
    if lid not in _TX_CACHE:
        p = settings.lec_transcript(lid)
        segs = json.loads(p.read_text(encoding="utf-8"))["segments"] if p.exists() else []
        _TX_CACHE[lid] = (segs, _norm("".join(s["text"] for s in segs)))
    return _TX_CACHE[lid]


def verify_citation(c: dict) -> dict:
    """Return grounding facts for one citation dict."""
    lid = c.get("lecture_id", "")
    quote = c.get("quote", "") or ""
    segs, full = _transcript(lid)
    nq = _norm(quote)
    grounded = bool(nq) and nq in full
    ts_delta = None
    if grounded:
        # find the segment that contains (most of) the quote, compare timestamps
        for s in segs:
            if nq[:24] and nq[:24] in _norm(s["text"]):
                ts_delta = round(abs(float(c.get("start_sec", 0)) - float(s["start"])), 1)
                break
    return {"quote_grounded": grounded, "ts_delta_sec": ts_delta,
            "quote_len": len(quote)}


def _one(cc, i, n, q):
    query = q["query"]
    t = time.time()
    try:
        res = cc.answer(query).to_dict()
        err = None
    except Exception as e:                           # noqa: BLE001
        res = {"answer": "", "citations": [], "units_used": []}
        err = f"{type(e).__name__}: {e}"
    lat = round(time.time() - t, 1)
    cites = res.get("citations", [])
    for c in cites:
        c["_grounding"] = verify_citation(c)
    gc = sum(1 for c in cites if c["_grounding"]["quote_grounded"])
    rec = {
        "id": q.get("id", i), "kind": q.get("kind", ""),
        "expected_lecture": q.get("expected_lecture"),
        "query": query, "answer": res.get("answer", ""),
        "lectures_cited": sorted({c.get("lecture_id") for c in cites}),
        "units_used": res.get("units_used", []),
        "n_citations": len(cites), "n_grounded": gc,
        "grounding_rate": round(gc / len(cites), 2) if cites else None,
        "latency_sec": lat, "error": err,
        "citations": [{k: c.get(k) for k in
                       ("lecture_id", "lecture_title", "unit_id", "ts",
                        "start_sec", "slide_index", "quote", "_grounding")}
                      for c in cites],
    }
    print(f"[{i+1}/{n}] {lat:5.1f}s cite={len(cites)} grounded={gc} "
          f"lec={rec['lectures_cited']} :: {query[:42]}", file=sys.stderr, flush=True)
    return rec


def run(questions: list, conc: int = 6) -> list:
    from concurrent.futures import ThreadPoolExecutor
    cc = CanvasClaw()                                 # one shared engine (LLM calls are IO-bound)
    n = len(questions)
    out = [None] * n
    with ThreadPoolExecutor(max_workers=conc) as ex:
        futs = {ex.submit(_one, cc, i, n, q): i for i, q in enumerate(questions)}
        for f in futs:
            i = futs[f]; out[i] = f.result()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--conc", type=int, default=6)
    a = ap.parse_args()
    qs = json.loads(Path(a.inp).read_text(encoding="utf-8"))
    results = run(qs, conc=a.conc)
    Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    # quick aggregate to stderr
    grs = [r["grounding_rate"] for r in results if r["grounding_rate"] is not None]
    print(f"\nDONE {len(results)} q | avg latency "
          f"{sum(r['latency_sec'] for r in results)/len(results):.1f}s | "
          f"citations {sum(r['n_citations'] for r in results)} | "
          f"avg grounding {sum(grs)/len(grs):.2f}" if grs else "no grounded", file=sys.stderr)
