#!/usr/bin/env python3
"""Repair lectures whose first ASR pass produced ~0 segments. Two failure modes:
  (a) fluke (normal-volume audio, VAD init race under 8-way parallel start)
  (b) very quiet mic -> VAD treats speech as silence
Fix: re-extract audio with loudness normalization (dynaudnorm) and re-transcribe
SEQUENTIALLY (no race). The hallucination filter rejects pure-noise lectures, so
genuinely silent sources end up empty (reported), not polluted.

    python tools/repair_lectures.py L11 L13 L14 L20 L25 L26
"""
from __future__ import annotations
import sys, json, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import settings
import scripts.transcribe as T
from engine.segment import build_units


def repair(lids):
    man = {l["lecture_id"]: l for l in json.loads(settings.MANIFEST.read_text(encoding="utf-8"))["lectures"]}
    rows = []
    for lid in lids:
        lec = man[lid]; video = lec["video"]; d = settings.lec_dir(lid)
        norm = d / "audio_norm.wav"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
                        "-af", "dynaudnorm=f=150:g=15:p=0.9", "-c:a", "pcm_s16le",
                        str(norm), "-loglevel", "error"], check=True)
        data = T.transcribe(str(norm), str(settings.lec_transcript(lid)))
        out = build_units(lid, lec.get("title", ""))
        rows.append((lid, data["n_segments"], data.get("n_hallucinations_filtered", 0), out["n_units"], out["n_chunks"]))
        print(f"[repair] {lid}: {data['n_segments']} segs, {data.get('n_hallucinations_filtered',0)} hallu filtered, "
              f"{out['n_units']} units, {out['n_chunks']} chunks", flush=True)
    print("\n=== REPAIR SUMMARY ===")
    for lid, s, h, u, c in rows:
        verdict = "RECOVERED" if s > 30 else ("EMPTY (no usable speech)" if s < 5 else "PARTIAL")
        print(f"  {lid}: {s} segs / {u} units / {c} chunks  -> {verdict}")


if __name__ == "__main__":
    repair(sys.argv[1:] or ["L11", "L13", "L14", "L20", "L25", "L26"])
