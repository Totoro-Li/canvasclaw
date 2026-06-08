#!/usr/bin/env python3
"""Headless-browser capture of the CanvasClaw Streamlit UI:
 - records the whole session to a webm video (record_video_dir)
 - saves representative screenshots at key moments
Usage: python tools/capture_ui.py [URL]
"""
import sys, time, pathlib
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501/"
OUT = pathlib.Path("/workspace/canvasclaw/video/shots"); OUT.mkdir(parents=True, exist_ok=True)
VID = pathlib.Path("/workspace/canvasclaw/video/rec"); VID.mkdir(parents=True, exist_ok=True)

def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    print("shot:", name, flush=True)

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--force-color-profile=srgb"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                        record_video_dir=str(VID), record_video_size={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.goto(URL, wait_until="domcontentloaded", timeout=60000)
    # wait for Streamlit to finish first render (quick-action buttons present)
    pg.wait_for_selector("text=快捷提问", timeout=60000)
    pg.wait_for_timeout(2500)
    shot(pg, "01_home")

    # click a cross-lecture question (multiple workers -> agent blocks animate)
    pg.get_by_text("🔁 记忆 vs 检索增强", exact=True).first.click()
    # capture the multi-agent blocks while they run
    try:
        pg.wait_for_selector("text=多智能体并行作答", timeout=30000)
        pg.wait_for_timeout(900); shot(pg, "02_agents_running")
    except Exception as e:
        print("agents panel not caught:", e, flush=True)
    # wait for the answer + citations to FULLY render (jump buttons appear last)
    try:
        pg.wait_for_selector("text=跳转到", timeout=150000)
        pg.wait_for_timeout(2000); shot(pg, "03_answer_citations")
    except Exception as e:
        print("citations not caught:", e, flush=True)
        pg.wait_for_timeout(2000); shot(pg, "03_answer_citations")

    # jump-to-timestamp: click first 跳转 button -> sidebar video seeks
    try:
        pg.get_by_text("跳转到", exact=False).first.click()
        pg.wait_for_timeout(3000); shot(pg, "04_video_jump")
    except Exception as e:
        print("jump not caught:", e, flush=True)

    pg.wait_for_timeout(1000)
    ctx.close()   # finalizes the video
    b.close()
    # report the produced video file
    vids = list(VID.glob("*.webm"))
    print("VIDEO:", vids[0] if vids else "none", flush=True)
