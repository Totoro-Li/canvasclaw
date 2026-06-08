#!/usr/bin/env python3
"""Slide keyframe extraction via perceptual hashing (design's '视觉切页').
Importable: extract_slides(video, outdir). Writes <outdir>/slides.json and
<outdir>/slide_NNN.jpg with {slide_index, start_sec, end_sec, ts, frame}.
"""
import json, os, sys, glob, subprocess
from PIL import Image
import imagehash


def _fmt(t):
    return f"{int(t//3600):02d}:{int((t%3600)//60):02d}:{int(t%60):02d}"


def extract_slides(video: str, outdir: str, fps: float = 0.5, ham: int = 8) -> dict:
    raw = os.path.join(outdir, "raw")
    os.makedirs(raw, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", video, "-vf", f"fps={fps},scale=1280:-1",
                    "-q:v", "3", os.path.join(raw, "f_%06d.jpg"), "-loglevel", "error"], check=True)
    frames = sorted(glob.glob(os.path.join(raw, "f_*.jpg")))
    slides, last, cur = [], None, None
    for i, fp in enumerate(frames):
        try:
            h = imagehash.dhash(Image.open(fp), hash_size=12)
        except Exception:
            continue
        t = round(i / fps, 1)
        if last is None or (h - last) > ham:
            if cur is not None:
                cur["end_sec"] = t; slides.append(cur)
            idx = len(slides)
            keep = os.path.join(outdir, f"slide_{idx:03d}.jpg")
            Image.open(fp).save(keep)
            cur = {"slide_index": idx, "start_sec": t, "end_sec": None, "ts": _fmt(t), "frame": keep}
            last = h
    if cur is not None:
        cur["end_sec"] = round(len(frames) / fps, 1); slides.append(cur)
    out = {"n_slides": len(slides), "fps": fps, "slides": slides}
    with open(os.path.join(outdir, "slides.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for fp in frames:
        try: os.remove(fp)
        except OSError: pass
    try: os.rmdir(raw)
    except OSError: pass
    print(f"[slides] {len(slides)} unique slides -> {outdir}/slides.json", flush=True)
    return out


if __name__ == "__main__":
    extract_slides(sys.argv[1] if len(sys.argv) > 1 else "../course.mp4",
                   sys.argv[2] if len(sys.argv) > 2 else "data/slides")
