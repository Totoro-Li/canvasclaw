#!/usr/bin/env python3
"""Run slide OCR (vision LLM) + unit enrichment for every lecture in the manifest.
Adds slide titles + slide-text chunks to each lecture's units.json (idempotent-ish:
re-runs OCR and overwrites slides_ocr.json). Run AFTER enrich_titles, BEFORE index.

    python tools/ocr_all.py            # all lectures
    python tools/ocr_all.py L01 L05    # subset
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import settings
from engine import slides_ocr


def main(lids=None):
    man = json.loads(settings.MANIFEST.read_text(encoding="utf-8"))["lectures"]
    ids = lids or [l["lecture_id"] for l in man]
    tot_slides = tot_chunks = 0
    for lid in ids:
        if not settings.lec_slides_json(lid).exists():
            print(f"[ocr_all] {lid}: no slides.json, skip"); continue
        try:
            r = slides_ocr.ocr_slides(lid)
            lu = slides_ocr.enrich_units(lid)
            ns = len(r["slides"]); tot_slides += ns
            slide_chunks = sum(1 for c in lu["chunks"] if c.get("source") == "slide")
            tot_chunks += slide_chunks
            print(f"[ocr_all] {lid}: {ns} slides OCR'd, {slide_chunks} slide-chunks, {lu['n_chunks']} chunks total", flush=True)
        except Exception as e:                          # noqa: BLE001
            print(f"[ocr_all] {lid}: FAILED {type(e).__name__}: {e}", flush=True)
    print(f"\n[ocr_all] done: {tot_slides} slides OCR'd, {tot_chunks} slide-chunks added")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
