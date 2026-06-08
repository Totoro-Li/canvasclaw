#!/usr/bin/env python3
"""Dump a compact map of the ingested corpus: per-lecture title, duration,
counts, and unit titles/summaries. Used for test-question generation and the
report. Writes JSON to stdout (or --out)."""
from __future__ import annotations
import json, sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import settings


def dump() -> dict:
    man = json.loads(settings.MANIFEST.read_text(encoding="utf-8"))
    lectures = []
    tot_units = tot_chunks = tot_dur = 0
    for lec in man["lectures"]:
        lid = lec["lecture_id"]
        up = settings.lec_units(lid)
        tp = settings.lec_transcript(lid)
        units, n_chunks, dur, n_seg = [], 0, 0, 0
        if up.exists():
            lu = json.loads(up.read_text(encoding="utf-8"))
            n_chunks = lu.get("n_chunks", len(lu.get("chunks", [])))
            for u in lu.get("units", []):
                units.append({"unit_id": u["unit_id"], "ts": u["ts"],
                              "title": u.get("title", ""),
                              "summary": (u.get("summary", "") or u.get("transcript_text", ""))[:160]})
        if tp.exists():
            tj = json.loads(tp.read_text(encoding="utf-8"))
            dur = tj.get("duration_sec", 0); n_seg = tj.get("n_segments", 0)
        tot_units += len(units); tot_chunks += n_chunks; tot_dur += dur
        lectures.append({"lecture_id": lid, "title": lec.get("title", ""),
                         "week": lec.get("week"), "duration_min": round(dur/60, 1),
                         "n_segments": n_seg, "n_units": len(units), "n_chunks": n_chunks,
                         "units": units})
    return {"n_lectures": len(lectures), "total_units": tot_units,
            "total_chunks": tot_chunks, "total_hours": round(tot_dur/3600, 2),
            "lectures": lectures}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    d = dump()
    s = json.dumps(d, ensure_ascii=False, indent=1)
    (Path(a.out).write_text(s, encoding="utf-8") if a.out else print(s))
