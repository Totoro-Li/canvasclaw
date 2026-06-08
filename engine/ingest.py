"""Ingest ONE lecture video into its own lecture dir, and register it in the
manifest. Pipeline: ffmpeg audio -> ASR -> slide keyframes -> segmentation
(-> optional vision OCR). Idempotent: skips stages whose output already exists.

    python -m engine.ingest --video /path/lec03.mp4 --id L03 --title "推理与规划" --week 3 [--ocr]

Manifest: data/lectures.json = {"lectures": [{lecture_id,title,week,date,video,dir}, ...]}
"""
from __future__ import annotations
import json, subprocess, sys, argparse
from pathlib import Path
from config.config import settings

sys.path.insert(0, str(settings.ROOT / "scripts"))   # transcribe.py / extract_slides.py


def load_manifest() -> dict:
    if settings.MANIFEST.exists():
        return json.loads(settings.MANIFEST.read_text(encoding="utf-8"))
    return {"lectures": []}


def _upsert(entry: dict) -> None:
    m = load_manifest()
    m["lectures"] = [l for l in m["lectures"] if l["lecture_id"] != entry["lecture_id"]]
    m["lectures"].append(entry)
    m["lectures"].sort(key=lambda l: (l.get("week") or 0, l["lecture_id"]))
    settings.MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def ingest(video: str, lecture_id: str, title: str = "", week=None, date=None,
           do_ocr: bool = False) -> dict:
    video = str(Path(video).resolve())
    d = settings.lec_dir(lecture_id)
    (d / "slides").mkdir(parents=True, exist_ok=True)

    wav = d / "audio.wav"
    if not wav.exists():
        print(f"[ingest:{lecture_id}] extracting audio…", flush=True)
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", str(wav), "-loglevel", "error"], check=True)

    import transcribe, extract_slides
    if not settings.lec_transcript(lecture_id).exists():
        transcribe.transcribe(str(wav), str(settings.lec_transcript(lecture_id)))
    if not settings.lec_slides_json(lecture_id).exists():
        extract_slides.extract_slides(video, str(d / "slides"))

    from engine.segment import build_units
    out = build_units(lecture_id, title)
    print(f"[ingest:{lecture_id}] {out['n_units']} units, {out['n_chunks']} chunks", flush=True)

    if do_ocr and settings.ready():
        from engine import slides_ocr
        slides_ocr.ocr_slides(lecture_id)
        slides_ocr.enrich_units(lecture_id)

    _upsert({"lecture_id": lecture_id, "title": title, "week": week, "date": date,
             "video": video, "dir": str(d)})
    print(f"[ingest:{lecture_id}] registered in manifest ({video})", flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--id", required=True, dest="lecture_id")
    ap.add_argument("--title", default="")
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--ocr", action="store_true")
    a = ap.parse_args()
    ingest(a.video, a.lecture_id, a.title, a.week, a.date, a.ocr)
