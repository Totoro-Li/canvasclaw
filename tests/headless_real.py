"""Real-engine headless integration test (hits the live LLM via llm.dp.tech).
Runs the actual Streamlit app under AppTest with the REAL CanvasClaw engine.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest

APP = str(ROOT / "frontend" / "streamlit_app.py")


def exc(at, label):
    if at.exception:
        print(f"  ✗ {label}:")
        for e in at.exception:
            v = getattr(e, "value", None) or getattr(e, "message", None) or str(e)
            print("    ", str(v).splitlines()[0])
        return False
    print(f"  ✓ {label}")
    return True


results = {}
at = AppTest.from_file(APP, default_timeout=300)
print("[real] initial load (builds index + bge + LangGraph)…")
at.run()
results["load"] = exc(at, "initial load")

print("[real] on-topic query (live fan-out → workers → aggregate)…")
at.chat_input[0].set_value("短期记忆和长期记忆有什么区别？").run()
ok = exc(at, "on-topic query")
mds = " ".join(m.value for m in at.markdown)
answer_ok = len(mds) > 200 and "来源" in mds
jbtns = [b for b in at.button if "跳转" in b.label]
print(f"    answer_len~{len(mds)}  citations_header={'来源讲次' in mds}  jump_buttons={len(jbtns)}")
results["ontopic"] = ok and answer_ok and len(jbtns) > 0

print("[real] jump button on a real citation…")
if jbtns:
    at.chat_input[0].set_value("")
    jbtns[0].click().run()
    ok = exc(at, "jump click")
    jump = at.session_state["jump"] if "jump" in at.session_state else None
    persisted = "短期记忆" in " ".join(m.value for m in at.markdown)
    print(f"    jump_sec={jump}  response_persisted={persisted}")
    results["jump"] = ok and isinstance(jump, int) and jump > 0 and persisted
else:
    results["jump"] = False

print("[real] off-topic query (should answer gracefully, no crash)…")
at.chat_input[0].set_value("今天上海天气怎么样？").run()
ok = exc(at, "off-topic query")
results["offtopic"] = ok

print("[real] multi-turn follow-up (pronoun needs history context)…")
at2 = AppTest.from_file(APP, default_timeout=300); at2.run()
at2.chat_input[0].set_value("短期记忆是怎么实现的？").run()
ok = exc(at2, "turn 1")
at2.chat_input[0].set_value("那长期记忆呢？").run()       # bare follow-up
ok &= exc(at2, "follow-up turn")
mds = " ".join(m.value for m in at2.markdown)
followup_ok = ("长期记忆" in mds) and ("来源" in mds)
print(f"    follow-up on-topic+cited={followup_ok}")
results["multiturn"] = ok and followup_ok

print("\n==================== REAL SUMMARY ====================")
for k, v in results.items():
    print(f"  {'PASS' if v else 'FAIL'}  {k}")
print("=====================================================")
sys.exit(0 if all(results.values()) else 1)
