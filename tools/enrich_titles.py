#!/usr/bin/env python3
"""Derive a real topic title + keywords + summary for each lecture from its ASR
transcript (LLM), then propagate into the manifest and each lecture's units.json.
Run AFTER base ingestion, BEFORE rebuilding the global index.

    python tools/enrich_titles.py
"""
from __future__ import annotations
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import settings
from engine import llm

SYS = ("你是《智能体及应用》研究生课程的助教。下面是某一讲的语音转写（可能含识别噪声）。"
       "请基于内容输出 JSON：{\"title\":\"≤18字的本讲主题标题\","
       "\"keywords\":[\"5-8个核心概念/术语\"],\"summary\":\"2-3句话中文概述本讲讲了什么\"}。"
       "只返回 JSON，不要解释。")


def _sample(segs, budget=6000):
    txt = " ".join(s["text"] for s in segs)
    if len(txt) <= budget:
        return txt
    a, b = budget // 2, budget // 4
    mid = len(txt) // 2
    return txt[:a] + " …… " + txt[mid:mid + b] + " …… " + txt[-b:]


def enrich_one(lec: dict) -> dict:
    lid = lec["lecture_id"]
    tp = settings.lec_transcript(lid)
    if not tp.exists():
        return {"lecture_id": lid, "ok": False, "reason": "no transcript"}
    segs = json.loads(tp.read_text(encoding="utf-8"))["segments"]
    if sum(len(s["text"]) for s in segs) < 300:        # silent/non-speech source -> no usable transcript
        return {"lecture_id": lid, "ok": False, "reason": "empty/no usable speech"}
    try:
        obj = llm.chat_json(
            [{"role": "system", "content": SYS},
             {"role": "user", "content": _sample(segs)}],
            model=settings.LLM_MODEL)
        title = str(obj.get("title", "")).strip()[:18]
        kws = [str(k) for k in (obj.get("keywords") or [])][:8]
        summary = str(obj.get("summary", "")).strip()
    except Exception as e:                              # noqa: BLE001
        return {"lecture_id": lid, "ok": False, "reason": str(e)}
    # write per-lecture meta
    (settings.lec_dir(lid) / "meta.json").write_text(
        json.dumps({"title": title, "keywords": kws, "summary": summary},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    # propagate lecture_title into units.json
    up = settings.lec_units(lid)
    full_title = f"第{lec.get('week')}讲 · {title}" if lec.get("week") else title
    if up.exists():
        lu = json.loads(up.read_text(encoding="utf-8"))
        for u in lu.get("units", []):
            u["lecture_title"] = full_title
        up.write_text(json.dumps(lu, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"lecture_id": lid, "ok": True, "title": full_title, "keywords": kws, "summary": summary}


def main():
    man = json.loads(settings.MANIFEST.read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(enrich_one, man["lectures"]))
    by_id = {r["lecture_id"]: r for r in results}
    for lec in man["lectures"]:
        r = by_id.get(lec["lecture_id"], {})
        if r.get("ok"):
            lec["title"] = r["title"]
    settings.MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results if r.get("ok"))
    print(f"[enrich] {ok}/{len(results)} lectures titled")
    for r in results:
        if r.get("ok"):
            print(f"  {r['lecture_id']}  {r['title']}")
        else:
            print(f"  {r['lecture_id']}  FAILED: {r.get('reason')}")


if __name__ == "__main__":
    main()
