#!/usr/bin/env python3
"""Experiment for the range-scoped retrieval + faithful-no-answer feature.

For each topic (with gold lectures that DO cover it, and an out-of-scope set that
does NOT), run 3 conditions and check behaviour:
  in_scope   (scope=gold) -> should ANSWER and cite only within scope
  oos        (scope=oos)  -> should faithfully ABSTAIN (scope_miss, 0 citations)
  full_range (scope=None) -> should ANSWER and recover the gold lecture
"""
from __future__ import annotations
import json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.agent import CanvasClaw

CASES = [
    ("检索增强生成(RAG)是怎么做的？", ["L07", "L08"], ["L01", "L02", "L03"]),
    ("短期记忆和上下文窗口是什么关系？", ["L07"], ["L03", "L04", "L05"]),
    ("多智能体系统是怎么协作的？", ["L15", "L16"], ["L01", "L02", "L07"]),
    ("大模型的指令微调是什么？", ["L17"], ["L01", "L05", "L15"]),
    ("Transformer 的注意力机制是怎样的？", ["L03"], ["L15", "L16", "L21"]),
    ("智能体是如何评估的？", ["L05"], ["L08", "L09", "L17"]),
    ("智能体怎么调用外部工具？", ["L06", "L09"], ["L01", "L02", "L17"]),
    ("这门课怎么评分？", ["L01"], ["L07", "L08", "L15"]),
    ("强化微调/RLHF 是怎么做的？", ["L19"], ["L01", "L02", "L03"]),
    ("提示工程有哪些技巧？", ["L03", "L04"], ["L15", "L16", "L22"]),
]


def run():
    cc = CanvasClaw()

    def ask(q, scope):
        r = cc.answer(q, scope=scope).to_dict()
        cites = sorted({c["lecture_id"] for c in r["citations"]})
        return {"scope_miss": bool(r["meta"].get("scope_miss")),
                "answered": not r["meta"].get("scope_miss") and bool(r["answer"]) and not r["meta"].get("scope_miss"),
                "lectures_cited": cites, "n_cit": len(r["citations"])}

    rows = []
    def one(case):
        q, gold, oos = case
        ins = ask(q, gold); o = ask(q, oos); full = ask(q, None)
        return {
            "query": q, "gold": gold, "oos": oos,
            "in_scope": ins, "oos_cond": o, "full": full,
            # metrics
            "in_answered": (not ins["scope_miss"]) and ins["n_cit"] > 0,
            "in_contained": all(l in gold for l in ins["lectures_cited"]) if ins["lectures_cited"] else None,
            "oos_faithful_none": o["scope_miss"] and o["n_cit"] == 0,
            "full_recovered": (not full["scope_miss"]) and any(l in gold for l in full["lectures_cited"]),
        }

    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, CASES))

    n = len(rows)
    ina = sum(r["in_answered"] for r in rows)
    cont = [r["in_contained"] for r in rows if r["in_contained"] is not None]
    contn = sum(1 for x in cont if x)
    oosf = sum(r["oos_faithful_none"] for r in rows)
    rec = sum(r["full_recovered"] for r in rows)
    summary = {
        "n_topics": n,
        "in_scope_answered": f"{ina}/{n}",
        "scope_containment": f"{contn}/{len(cont)}",
        "oos_faithful_none": f"{oosf}/{n}",
        "full_range_recovery": f"{rec}/{n}",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in rows:
        print(f"  [{'OK' if r['oos_faithful_none'] else 'LEAK'}] oos={r['oos_cond']['scope_miss']}/{r['oos_cond']['lectures_cited']}"
              f"  in={r['in_scope']['lectures_cited']}  full={r['full']['lectures_cited']}  :: {r['query'][:30]}",
              file=sys.stderr)
    Path("data/eval/scope_eval.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    run()
