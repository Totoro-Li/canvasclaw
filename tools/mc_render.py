#!/usr/bin/env python3
"""Headless Motion Canvas render: open the editor (localhost:9000), click RENDER,
wait until PNG frames stop accumulating in output/. Frames -> mp4 done separately.
"""
import sys, time, glob, os
from playwright.sync_api import sync_playwright

OUT = "/workspace/canvasclaw/video/mc/output"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000/"

def nframes():
    return len(glob.glob(OUT + "/**/*.png", recursive=True))

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    pg.goto(URL, wait_until="networkidle", timeout=40000)
    pg.wait_for_timeout(5000)
    before = nframes()
    btn = None
    for e in pg.query_selector_all("button,[role=button],a"):
        t = (e.get_attribute("title") or e.get_attribute("aria-label") or e.inner_text() or "").strip()
        if t.upper() == "RENDER":
            btn = e; break
    if btn is None:
        print("[mc_render] RENDER button not found"); b.close(); sys.exit(1)
    btn.click()
    print(f"[mc_render] clicked RENDER (frames before={before})", flush=True)
    # poll until frames appear and then plateau
    last, stable, t0 = before, 0, time.time()
    while time.time() - t0 < 900:
        time.sleep(5)
        n = nframes()
        print(f"  frames={n}  (+{n-last})", flush=True)
        if n > before and n == last:
            stable += 1
            if stable >= 4:   # ~20s no growth -> done
                break
        else:
            stable = 0
        last = n
    print(f"[mc_render] DONE frames={nframes()}", flush=True)
    b.close()
