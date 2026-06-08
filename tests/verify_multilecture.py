"""Cross-lecture routing precision check (real engine, multi-lecture index).
Confirms the Orchestrator routes each query to the RIGHT lecture and citations
carry the correct lecture_id + precise timestamps.
"""
import sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.agent import CanvasClaw
from engine import graph as G

cc = CanvasClaw()
idx = cc.index
print(f"[index] lectures={len(idx.lectures)} units={len(idx.units)} chunks={len(idx.chunks)}")
for l in idx.lectures:
    nu = sum(1 for u in idx.units if u['lecture_id'] == l['lecture_id'])
    print(f"   {l['lecture_id']}  {l.get('title','')[:30]}  units={nu}  video={Path(l.get('video','')).name}")

UWIN = {u["unit_id"]: (u["start_sec"], u["end_sec"]) for u in idx.units}

# (query, expected dominant lecture or None if topic overlaps both halves)
CASES = [
    ("检索机制是怎么实现的？先检索再增强", "L02"),
    ("内容摘要与提取这个功能是做什么的？", "L02"),
    ("用GPT作为课程理解助手的场景是怎样的？", "L01"),
    ("长期记忆可以分为哪几类？用户偏好和画像", None),   # previously returned 0 citations
]
ok_all = True
for q, expect in CASES:
    res = cc.answer(q)
    lecs = [c.lecture_id for c in res.citations]
    dom = Counter(lecs).most_common(1)[0][0] if lecs else "—"
    has_cites = len(res.citations) > 0
    # grounded = every citation's time sits inside its cited unit's window (transcript- or slide-timed)
    grounded = has_cites and all(
        c.unit_id in UWIN and UWIN[c.unit_id][0] - 3 <= c.start_sec <= UWIN[c.unit_id][1] + 3
        for c in res.citations)
    route_ok = (expect is None) or (dom == expect)
    ok = route_ok and has_cites and grounded
    ok_all &= ok
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] expect {expect or 'any'} got {dom}  "
          f"units={sorted(set(res.units_used))} grounded={grounded} cites={len(res.citations)}")

print("\n" + ("ALL ROUTING PASS ✓" if ok_all else "SOME ROUTING FAILED ✗"))
sys.exit(0 if ok_all else 1)
