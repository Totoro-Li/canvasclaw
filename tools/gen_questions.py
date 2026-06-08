#!/usr/bin/env python3
"""Build the evaluation question bank from the enriched corpus (manifest + per-lecture
meta.json keywords). Deterministic & reproducible. Categories:
  factual    : one content question per lecture (expected_lecture set)
  locate     : "which lecture / when did it cover X" (routing + timestamp)
  compare    : cross-lecture comparative (multi-lecture fan-out)
  oos        : out-of-scope honesty checks (should answer 'not covered')
Writes data/eval/questions.json
"""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import settings

OOS = ["量子计算的纠错码", "区块链的共识算法", "自动驾驶的激光雷达标定", "蛋白质三维折叠预测"]


def load_meta():
    man = json.loads(settings.MANIFEST.read_text(encoding="utf-8"))["lectures"]
    out = []
    for lec in man:
        mp = settings.lec_dir(lec["lecture_id"]) / "meta.json"
        meta = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
        kws = [k for k in meta.get("keywords", []) if 2 <= len(k) <= 20]
        out.append({"lid": lec["lecture_id"], "week": lec.get("week"),
                    "title": lec.get("title", ""), "keywords": kws,
                    "summary": meta.get("summary", "")})
    return out


def build(metas):
    qs, qid = [], 0
    def add(query, kind, exp=None):
        nonlocal qid
        qs.append({"id": f"Q{qid:03d}", "query": query, "kind": kind, "expected_lecture": exp})
        qid += 1

    # 1) factual: one per lecture, from its first distinctive keyword
    for m in metas:
        kw = m["keywords"][0] if m["keywords"] else m["title"]
        add(f"课程里讲到的「{kw}」是什么？它的核心思想或做法是怎样的？", "factual", m["lid"])

    # 2) locate: routing+timestamp, distinctive keywords spread across lectures
    picks = [(m["lid"], m["keywords"][1]) for m in metas if len(m["keywords"]) > 1][:12]
    for lid, kw in picks:
        add(f"老师在哪一讲、大概什么时间讲了「{kw}」？", "locate", lid)

    # 3) compare: pair keywords from different lectures
    rich = [m for m in metas if len(m["keywords"]) >= 2]
    for i in range(0, min(len(rich) - 1, 12), 2):
        a, b = rich[i], rich[i + 1]
        add(f"「{a['keywords'][0]}」和「{b['keywords'][0]}」有什么区别或联系？分别在课程的哪部分讲到？",
            "compare", None)

    # 4) out-of-scope honesty
    for x in OOS:
        add(f"这门《智能体及应用》课程里讲过「{x}」吗？如果讲过是在哪一讲？", "oos", None)

    return qs


if __name__ == "__main__":
    metas = load_meta()
    qs = build(metas)
    outdir = settings.DATA / "eval"; outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "questions.json").write_text(json.dumps(qs, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"[gen] {len(qs)} questions -> {outdir/'questions.json'}")
    print("  by kind:", dict(Counter(q["kind"] for q in qs)))
