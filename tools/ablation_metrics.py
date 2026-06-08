#!/usr/bin/env python3
"""Compute comparable AUTO metrics for one or more eval result files (ablation).
Per file: routing exact-hit, fragment-aware citation grounding (transcript+slides),
oos-honesty (out-of-scope -> 0 citations), avg latency, citations, by-kind coverage.

    python tools/ablation_metrics.py gpt55=data/eval/results_gpt5.json dsv4=data/eval/results_dsv4flash.json ...
"""
from __future__ import annotations
import sys, json, re, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_norm = lambda s: re.sub(r"[\s，。、；：,.!?！？\-—…·\"'《》()（）]", "", (s or "")).lower()

def _corpus():
    TX, SL = {}, {}
    for f in glob.glob("data/lectures/L*/transcript.json"):
        lid = f.split("/")[2]; TX[lid] = _norm("".join(s["text"] for s in json.load(open(f))["segments"]))
    for f in glob.glob("data/lectures/L*/slides/slides_ocr.json"):
        lid = f.split("/")[2]; d = json.load(open(f)); SL[lid] = _norm("".join((s.get("title","")+s.get("ocr_text","")) for s in d["slides"]))
    return {lid: TX.get(lid,"")+"≈"+SL.get(lid,"") for lid in set(list(TX)+list(SL))}

_HAY = None
def _frags(q):
    return [p for p in (_norm(x) for x in re.split(r"…+|\.\.\.|。{2,}", q)) if len(p) >= 8]

def grounded(c):
    global _HAY
    if _HAY is None: _HAY = _corpus()
    hay = _HAY.get(c.get("lecture_id",""), "")
    fs = _frags(c.get("quote","")) or [_norm(c.get("quote",""))]
    return bool(_norm(c.get("quote",""))) and all(fr in hay for fr in fs)

def metrics(results):
    n = len(results)
    exp = [r for r in results if r.get("expected_lecture")]
    routing_hit = sum(1 for r in exp if r["expected_lecture"] in r.get("lectures_cited", []))
    cites = [c for r in results for c in r.get("citations", [])]
    g = sum(1 for c in cites if grounded(c))
    oos = [r for r in results if r.get("kind") == "oos"]
    oos_ok = sum(1 for r in oos if r["n_citations"] == 0)
    lat = [r["latency_sec"] for r in results]
    from collections import defaultdict
    bk = defaultdict(lambda: [0, 0])
    for r in results:
        bk[r["kind"]][0] += 1; bk[r["kind"]][1] += (r["n_citations"] > 0)
    return {
        "n": n,
        "routing_hit": f"{routing_hit}/{len(exp)}" if exp else "-",
        "routing_hit_pct": round(routing_hit/len(exp)*100) if exp else None,
        "citations": len(cites),
        "grounded_pct": round(g/len(cites)*100) if cites else None,
        "oos_honesty": f"{oos_ok}/{len(oos)}" if oos else "-",
        "avg_latency": round(sum(lat)/n, 1) if n else None,
        "by_kind_cite": {k: f"{v[1]}/{v[0]}" for k, v in bk.items()},
    }

if __name__ == "__main__":
    rows = {}
    for arg in sys.argv[1:]:
        tag, path = arg.split("=", 1)
        rows[tag] = metrics(json.load(open(path)))
    # print table
    cols = ["n", "routing_hit_pct", "grounded_pct", "oos_honesty", "avg_latency", "citations"]
    print(f"{'model':14}" + "".join(f"{c:>16}" for c in cols))
    for tag, m in rows.items():
        print(f"{tag:14}" + "".join(f"{str(m[c]):>16}" for c in cols))
    print("\nby-kind citation coverage:")
    for tag, m in rows.items():
        print(f"  {tag}: {m['by_kind_cite']}")
    json.dump(rows, open("data/eval/model_compare_auto.json", "w"), ensure_ascii=False, indent=1)
