"""Lecture-unit segmentation (per lecture). Splits ONE lecture video into
time-balanced topic units so the Orchestrator can fan out to several Worker
agents. Globally-unique ids are lecture-scoped: "L03-U02", "L03-U02-c001".

Called by engine.ingest for each video; can also be run standalone:
    python -m engine.segment <lecture_id>
Reads data/lectures/<id>/{transcript.json,slides/slides.json}
Writes data/lectures/<id>/units.json = {units: LectureUnit[], chunks: Chunk[]}
"""
from __future__ import annotations
import json, re, sys
from config.config import settings
from engine.schemas import LectureUnit, Chunk


def fmt(t: float) -> str:
    return f"{int(t//3600):02d}:{int((t%3600)//60):02d}:{int(t%60):02d}"


def _target_units(n_slides: int) -> int:
    return max(4, min(12, round(n_slides / 7)))


def _salient(text: str, n: int = 26) -> str:
    text = re.sub(r"^(OK[,， ]*|那么?[,， ]*|然后[,， ]*|好[,， ]*)+", "", text).strip()
    return text[:n]


def build_units(lecture_id: str, lecture_title: str = "") -> dict:
    tr = json.loads(settings.lec_transcript(lecture_id).read_text(encoding="utf-8"))
    sl = json.loads(settings.lec_slides_json(lecture_id).read_text(encoding="utf-8"))
    segs, slides, dur = tr["segments"], sl["slides"], tr["duration_sec"]
    if not slides:                                   # degenerate: no slides -> time windows
        slides = [{"slide_index": 0, "start_sec": 0.0, "end_sec": dur}]
    n_units = _target_units(len(slides))
    target = dur / n_units

    groups, cur, g0 = [], [], slides[0]["start_sec"]
    for s in slides:
        if cur and (s["start_sec"] - g0) >= target and len(groups) < n_units - 1:
            groups.append(cur); cur, g0 = [], s["start_sec"]
        cur.append(s)
    if cur:
        groups.append(cur)

    units: list[LectureUnit] = []
    for k, g in enumerate(groups):
        start = g[0]["start_sec"]
        end = groups[k + 1][0]["start_sec"] if k + 1 < len(groups) else dur
        units.append(LectureUnit(
            unit_id=f"{lecture_id}-U{k:02d}", title=f"{lecture_id}-U{k:02d}",
            lecture_id=lecture_id, lecture_title=lecture_title,
            slide_indices=[s["slide_index"] for s in g],
            start_sec=round(start, 1), end_sec=round(end, 1), ts=fmt(start)))

    def unit_of(t):
        for u in units:
            if u.start_sec <= t < u.end_sec:
                return u
        return units[-1]

    def slides_in(a, b):
        return [s["slide_index"] for s in slides if s["start_sec"] < b and s["end_sec"] > a]

    per_unit = {u.unit_id: [] for u in units}
    for s in segs:
        per_unit[unit_of(s["start"]).unit_id].append(s)

    chunks: list[Chunk] = []
    for u in units:
        usegs = per_unit[u.unit_id]
        u.transcript_text = "".join(s["text"] for s in usegs)
        if usegs:
            u.title = f"{u.unit_id} · {_salient(usegs[0]['text'])}"
            u.summary = u.transcript_text[:160]
        buf, cid = [], 0
        def flush():
            nonlocal buf, cid
            if not buf:
                return
            a, b = buf[0]["start"], buf[-1]["end"]
            ch = Chunk(chunk_id=f"{u.unit_id}-c{cid:03d}", unit_id=u.unit_id,
                       lecture_id=lecture_id, text="".join(x["text"] for x in buf),
                       start_sec=round(a, 1), end_sec=round(b, 1), ts=fmt(a),
                       slide_indices=slides_in(a, b),
                       is_question=any(x["is_question_candidate"] for x in buf))
            chunks.append(ch); u.chunk_ids.append(ch.chunk_id); cid += 1; buf = []
        cur_len = 0
        for s in usegs:
            buf.append(s); cur_len += len(s["text"])
            if cur_len >= settings.CHUNK_MAX_CHARS:
                flush(); cur_len = 0
        flush()

    out = {"lecture_id": lecture_id, "lecture_title": lecture_title,
           "n_units": len(units), "n_chunks": len(chunks),
           "units": [u.to_dict() for u in units], "chunks": [c.to_dict() for c in chunks]}
    settings.lec_units(lecture_id).write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    lid = sys.argv[1] if len(sys.argv) > 1 else "L01"
    out = build_units(lid, sys.argv[2] if len(sys.argv) > 2 else "")
    print(f"[segment:{lid}] {out['n_units']} units, {out['n_chunks']} chunks -> {settings.lec_units(lid)}")
    for u in out["units"]:
        print(f"  {u['unit_id']}  {u['ts']}  slides {u['slide_indices'][0]}-{u['slide_indices'][-1]}  {u['title'][:36]}")
