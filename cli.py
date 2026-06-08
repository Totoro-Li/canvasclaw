#!/usr/bin/env python3
"""CanvasClaw CLI — quick end-to-end test of the agent engine.

    python cli.py "老师在哪节课讲了检索增强？"
    python cli.py --stream "短期记忆和长期记忆的区别是什么？"
"""
import sys
from config.config import settings
from engine.agent import CanvasClaw


def main():
    args = [a for a in sys.argv[1:]]
    stream = "--stream" in args
    args = [a for a in args if a != "--stream"]
    q = " ".join(args) or "这节课主要讲了什么？"
    if not settings.ready():
        sys.exit("LLM not configured — fill canvasclaw/config/.env (see config/.env.example).")
    print(f"# {settings.summary()}\n# Q: {q}\n" + "-" * 60)
    cc = CanvasClaw()
    if stream:
        for ev in cc.stream(q):
            if ev["type"] == "status":
                print(f"[{ev['stage']}] {ev['msg']}")
            elif ev["type"] == "token":
                print(ev["text"], end="", flush=True)
            elif ev["type"] == "done":
                print()
    else:
        res = cc.answer(q)
        print(res.answer)
        print("-" * 60)
        print(f"讲次: {', '.join(res.units_used)}")
        seen = set()
        for c in res.citations:
            k = (c.unit_id, c.ts)
            if k in seen:
                continue
            seen.add(k)
            print(f"  📍 {c.unit_id}《{c.unit_title[:20]}》 ⏱ {c.ts}"
                  + (f" · slide {c.slide_index}" if c.slide_index is not None else ""))


if __name__ == "__main__":
    main()
