"""Headless AppTest harness for the CanvasClaw Streamlit UI.

Runs the real frontend/streamlit_app.py under streamlit.testing.v1.AppTest with a
deterministic fake engine injected, so UI bugs surface fast and without LLM calls.
Each scenario prints PASS/FAIL and any uncaught exception traceback.
"""
import sys, traceback
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import streamlit as st
from streamlit.testing.v1 import AppTest
import engine.agent as A

APP = str(ROOT / "frontend" / "streamlit_app.py")

# ---- injectable fake engine -------------------------------------------------
FAKE = {"answer": "这是一个测试答案。", "citations": []}


def _cit(uid="U01", title="测试单元", ts="00:13:06", si=38, quote="它需要对我的用户的画像有一个非常清晰的定义"):
    return {"unit_id": uid, "unit_title": title, "ts": ts, "start_sec": 786.0,
            "end_sec": 900.0, "slide_index": si, "quote": quote}


class FakeEngine:
    def __init__(self):
        pass

    def stream(self, query, history=None):
        yield {"type": "status", "stage": "retrieve", "msg": "检索到候选", "candidates": ["U01", "U03"]}
        yield {"type": "status", "stage": "route", "msg": "选定 U01", "units": ["U01"]}
        for tok in FAKE["answer"]:
            yield {"type": "token", "text": tok}
        if FAKE["citations"]:
            yield {"type": "citations", "citations": FAKE["citations"]}
        yield {"type": "done", "result": {"query": query, "answer": FAKE["answer"],
                                          "citations": FAKE["citations"], "units_used": ["U01"]}}

    def answer(self, query, history=None):
        from engine.schemas import AnswerResult
        return AnswerResult(query=query, answer=FAKE["answer"])


A.CanvasClaw = FakeEngine   # patch before the app imports it


def fresh():
    st.cache_resource.clear(); st.cache_data.clear()
    return AppTest.from_file(APP, default_timeout=60)


def show_exc(at, label):
    if at.exception:
        print(f"  ✗ {label}: {len(at.exception)} EXCEPTION(S)")
        for e in at.exception:
            print("    ", (e.value or e.message or str(e)).splitlines()[0] if hasattr(e, 'value') else e)
        return False
    print(f"  ✓ {label}")
    return True


results = {}

# ── Scenario 1: initial load, no input ──────────────────────────────────────
print("\n[1] initial load")
FAKE.update(answer="x", citations=[])
at = fresh(); at.run()
results["1_initial"] = show_exc(at, "renders without exception")

# ── Scenario 2: single query with a normal citation ─────────────────────────
print("\n[2] single query + citation render")
FAKE.update(answer="短期记忆与长期记忆的区别如下。", citations=[_cit()])
at = fresh(); at.run()
at.chat_input[0].set_value("短期记忆和长期记忆的区别？").run()
ok = show_exc(at, "query processed")
mds = " ".join(m.value for m in at.markdown)
ok &= ("短期记忆与长期记忆" in mds) or print("    answer text missing!")
ok = ok and ("来源" in mds)
print(f"    answer rendered={'短期记忆与长期记忆' in mds}  citations-header={'来源' in mds}  buttons={len(at.button)}")
results["2_query"] = bool(ok)

# ── Scenario 3: slide_index TYPE robustness (int/str/float/None/oob) ─────────
print("[3] slide_index type robustness (suspected crash)")
FAKE.update(answer="测试切片类型。", citations=[
    _cit(ts="00:01:01", si=5), _cit(ts="00:02:02", si="38"),
    _cit(ts="00:03:03", si=12.0), _cit(ts="00:04:04", si=None),
    _cit(ts="00:05:05", si=999)])
at = fresh(); at.run()
at.chat_input[0].set_value("各种 slide_index 类型").run()
results["3_slidetype"] = show_exc(at, "mixed slide_index types render")

# ── Scenario 4: jump button -> session_state.jump + answer persists ─────────
print("[4] jump button updates time AND response persists")
FAKE.update(answer="检索增强在第四单元讲解。", citations=[_cit(ts="00:40:04", si=38)])
at = fresh(); at.run()
at.chat_input[0].set_value("检索增强在哪讲？").run()
ok = show_exc(at, "query ok")
jbtns = [b for b in at.button if "跳转" in b.label]
print(f"    jump buttons found: {len(jbtns)}")
if jbtns:
    at.chat_input[0].set_value("")   # avoid re-submitting on rerun
    jbtns[0].click().run()
    ok2 = show_exc(at, "after jump click")
    jump = at.session_state["jump"] if "jump" in at.session_state else None
    mds2 = " ".join(m.value for m in at.markdown)
    persisted = "检索增强在第四单元讲解" in mds2
    print(f"    session_state.jump={jump} (expect 2404)  response_persisted={persisted}")
    results["4_jump"] = ok2 and jump == 2404 and persisted
else:
    results["4_jump"] = False

# ── Scenario 5: multi-turn, duplicate widget-key check ──────────────────────
print("[5] multi-turn (two queries) — no duplicate key / crash")
FAKE.update(answer="回答一。", citations=[_cit(ts="00:07:21")])
at = fresh(); at.run()
at.chat_input[0].set_value("问题一").run()
ok = show_exc(at, "turn 1")
FAKE.update(answer="回答二。", citations=[_cit(ts="00:11:32", uid="U02")])
at.chat_input[0].set_value("问题二").run()
ok &= show_exc(at, "turn 2")
mds = " ".join(m.value for m in at.markdown)
both = ("回答一" in mds) and ("回答二" in mds)
print(f"    both answers present={both}  total buttons={len(at.button)}")
results["5_multiturn"] = ok and both

# ── Scenario 6: no-citation (no units found) path ───────────────────────────
print("[6] no-citation answer path")
FAKE.update(answer="抱歉，未找到相关内容。", citations=[])
at = fresh(); at.run()
at.chat_input[0].set_value("无关问题 xyz").run()
ok = show_exc(at, "no-citation query")
mds = " ".join(m.value for m in at.markdown)
results["6_nocite"] = ok and ("抱歉" in mds)

print("\n==================== SUMMARY ====================")
for k, v in results.items():
    print(f"  {'PASS' if v else 'FAIL'}  {k}")
print("=================================================")
sys.exit(0 if all(results.values()) else 1)
