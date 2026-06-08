"""CanvasClaw — Streamlit demo UI (multi-lecture / full semester).

    streamlit run frontend/streamlit_app.py
Chat over ALL indexed lectures; streams Orchestrator→Worker progress and the
answer, cites lecture + timestamp + slide, and jumps the CORRECT lecture's video.
"""
import sys, json
from pathlib import Path
from datetime import date
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import streamlit as st
from config.config import settings
from engine.agent import CanvasClaw, ts_to_sec

# ---- NotebookLM-style quick actions (predefined one-click workflows) ----
def _quick_actions():
    today = date.today().isoformat()
    return [
        ("📚 最新一讲讲了啥", "课程里周次/日期最新的那一讲主要讲了哪些内容？请概述核心要点，并给出讲次与时间戳。"),
        ("📝 课程怎么评分", "这门课的成绩是如何评定的？是考试还是报告/项目？各部分各占多少分、占比是多少？"),
        ("⏰ 最近要交的作业", f"今天是 {today}。根据课程中各次课程作业与课程项目的截止时间，现在最近一个需要提交的是哪一个？它的截止时间、要求和分值是什么？还剩多久？"),
        ("📋 列出全部作业", "请列出本课程的全部课程作业（第几次、第几周、分值、提交要求与页数限制），并标注信息出自哪一讲。"),
        ("🗺️ 课程大纲脉络", "这门课的整体大纲是什么？包含哪些模块、每一讲的主题分别是什么？"),
        ("🎯 课程项目要求", "课程项目（大作业）的要求是什么？需要提交哪些材料、占多少分、各阶段（分组/提案/最终）的时间安排是怎样的？"),
        ("🧩 核心概念速览", "这门课最重要的几个核心概念/方法是什么？分别在哪一讲、大概什么时间讲到？"),
        ("🔁 记忆 vs 检索增强", "智能体的记忆机制与检索增强(RAG)有什么区别和联系？分别在课程的哪部分讲到？"),
    ]


def render_quick_actions():
    st.markdown("##### 💡 快捷提问")
    actions = _quick_actions()
    for row in (actions[:4], actions[4:]):
        cols = st.columns(4)
        for col, (label, query) in zip(cols, row):
            if col.button(label, key=f"qa_{label}", use_container_width=True):
                st.session_state["pending_q"] = query
                st.rerun()

st.set_page_config(page_title="CanvasClaw 课程学习助手", page_icon="🎓", layout="wide")


@st.cache_resource(show_spinner="加载课程索引…")
def load_engine():
    return CanvasClaw()


@st.cache_data
def lectures():
    if settings.MANIFEST.exists():
        return json.loads(settings.MANIFEST.read_text(encoding="utf-8"))["lectures"]
    return []


@st.cache_data
def units_of(lid):
    f = settings.lec_units(lid)
    return json.loads(f.read_text(encoding="utf-8"))["units"] if f.exists() else []


def lec_by_id(lid):
    return {l["lecture_id"]: l for l in lectures()}.get(lid, {})


@st.cache_data(show_spinner=False, ttl=300)
def available_models():
    """Auto-detect models if the endpoint is OpenAI-compatible (GET /v1/models)."""
    try:
        from openai import OpenAI
        c = OpenAI(base_url=settings.OPENAI_BASE_URL, api_key=settings.OPENAI_API_KEY, timeout=10)
        return sorted(m.id for m in c.models.list().data)
    except Exception:
        return []


LECS = lectures()
DEFAULT_LEC = LECS[0]["lecture_id"] if LECS else "L01"
st.session_state.setdefault("jump", 0)
st.session_state.setdefault("jump_lec", DEFAULT_LEC)

with st.sidebar:
    st.header("🎓 CanvasClaw")
    st.caption("多智能体课程问答助手 · Orchestrator–Worker (LangGraph)")
    if not settings.ready():
        st.error("未配置 LLM：config/.env 填写 OPENAI_BASE_URL / OPENAI_API_KEY / LLM_MODEL")
    else:
        models = available_models()
        if models:
            cur = settings.LLM_MODEL if settings.LLM_MODEL in models else models[0]
            chosen = st.selectbox(f"🧠 模型（端点自动识别 {len(models)} 个）", models,
                                  index=models.index(cur))
            settings.LLM_MODEL = chosen          # override LLM + router at runtime
            settings.ROUTER_MODEL = chosen
            st.caption(f"作答/路由: `{chosen}` · 视觉: `{settings.VISION_MODEL}`")
        else:
            st.success(f"LLM: {settings.LLM_MODEL}")
            st.caption("（端点未返回模型列表，使用 .env 配置）")
    # scope: restrict Q&A to a subset of lectures (empty = all)
    all_ids = [l["lecture_id"] for l in LECS]
    scope_sel = st.multiselect(
        "🎯 限定范围（留空 = 全部讲次）", all_ids,
        default=st.session_state.get("scope_default", []),
        format_func=lambda lid: f"{lid} · {(lec_by_id(lid).get('title') or '')[:12]}")
    if scope_sel:
        st.caption(f"已限定 {len(scope_sel)} 讲，范围外将如实回答“未找到”")
    st.markdown(f"**课程讲次（{len(LECS)} 节）**")
    for l in LECS:
        st.markdown(f"- `{l['lecture_id']}` {(l.get('title') or '')[:18]} · {len(units_of(l['lecture_id']))} 单元")
    lec = lec_by_id(st.session_state["jump_lec"])
    vpath = lec.get("video")
    if vpath and Path(vpath).exists():
        st.markdown(f"**▶ {lec.get('title') or st.session_state['jump_lec']}**")
        st.video(vpath, start_time=int(st.session_state["jump"]))

st.title("CanvasClaw 课程学习助手")
st.caption("多讲次课程问答 — 跨讲次检索定位，answer 附讲次 / 时间戳 / 幻灯片来源")

render_quick_actions()


def render_citations(citations, msg_idx):
    """Render citations + per-lecture jump buttons. Called from BOTH the live
    answer and the history loop so it survives reruns; keys stable per (msg, cite)."""
    if not citations:
        return
    st.markdown("##### 📌 来源（讲次 / 时间戳 / 幻灯片）")
    seen = set()
    for ci, c in enumerate(citations):
        lid = c.get("lecture_id", "L01")
        key = (lid, c["unit_id"], c.get("ts"))
        if key in seen:
            continue
        seen.add(key)
        lectitle = c.get("lecture_title") or lec_by_id(lid).get("title") or lid
        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown(f"**[{lid}] {lectitle[:16]} · {c['unit_id']}** · ⏱ {c['ts']}")
            if c.get("quote"):
                st.caption("“" + c["quote"][:80] + "”")
            if st.button(f"▶ 跳转到 {c['ts']}", key=f"jmp_{msg_idx}_{ci}"):
                st.session_state["jump"] = ts_to_sec(c["ts"])
                st.session_state["jump_lec"] = lid
                st.rerun()
        si = c.get("slide_index")
        try:
            si = int(si) if si is not None else None
        except (TypeError, ValueError):
            si = None
        if si is not None:
            fp = settings.lec_dir(lid) / "slides" / f"slide_{si:03d}.jpg"
            if fp.exists():
                cols[1].image(str(fp), caption=f"slide {si}")


def render_scope_miss(query, msg_idx):
    """On a limited-scope miss, offer to re-run the same query over ALL lectures."""
    st.caption("🔎 当前为限定范围检索，未命中。")
    if st.button("🔍 在全部讲次中重新搜索", key=f"full_{msg_idx}"):
        st.session_state["pending_q"] = query
        st.session_state["force_full"] = True
        st.rerun()


if "msgs" not in st.session_state:
    st.session_state.msgs = []
for idx, m in enumerate(st.session_state.msgs):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant" and m.get("citations"):
            render_citations(m["citations"], idx)
        if m["role"] == "assistant" and m.get("scope_miss"):
            render_scope_miss(m.get("query", ""), idx)

q = st.chat_input("提问，例如：老师在哪节课讲了检索增强？短期记忆和长期记忆的区别是什么？")
q = q or st.session_state.pop("pending_q", None)   # quick-action buttons feed in here
if q:
    _force_full = st.session_state.pop("force_full", False)   # "search full range" button
    scope = None if (_force_full or not scope_sel) else scope_sel
    st.session_state.msgs.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        status = st.status("Orchestrator 正在分发任务…", expanded=True)
        agents_slot = st.empty()        # live multi-agent status blocks (grey -> green)
        slot = st.empty()
        cc = load_engine()
        buf, citations = [], []
        order, agents, collapsed, scope_miss = [], {}, False, False

        def render_agents():
            n, done = len(order), sum(agents.values())
            cells = "".join(
                f'<span style="display:inline-block;width:22px;height:22px;margin:3px;border-radius:5px;'
                f'background:{"#3fb950" if agents[u] else "#30363d"};'
                f'box-shadow:0 0 7px {"#3fb95099" if agents[u] else "transparent"};'
                f'transition:background .35s,box-shadow .35s" title="{u}"></span>' for u in order)
            agents_slot.markdown(
                '<div style="padding:8px 12px;border:1px solid #30363d;border-radius:10px;background:#0d111744;margin:4px 0">'
                f'<span style="color:#8b949e;font-size:0.9em">🤖 多智能体并行作答 · {done}/{n} 完成</span>'
                f'<div style="margin-top:6px">{cells}</div></div>', unsafe_allow_html=True)

        history = [{"role": m["role"], "content": m["content"]}
                   for m in st.session_state.msgs[:-1][-6:]]   # prior turns only
        for ev in cc.stream(q, history, scope=scope):
            t = ev["type"]
            if t == "status":
                status.write(f"**{ev['stage']}** — {ev['msg']}")
            elif t == "dispatch":
                order = list(ev["units"]); agents = {u: False for u in order}; render_agents()
            elif t == "worker":
                if ev["unit_id"] in agents:
                    agents[ev["unit_id"]] = True
                render_agents()
            elif t == "token":
                if not collapsed:        # all workers finished -> collapse panel back toward input
                    agents_slot.empty(); collapsed = True
                buf.append(ev["text"]); slot.markdown("".join(buf))
            elif t == "citations":
                citations = ev["citations"]
            elif t == "done":
                agents_slot.empty()
                scope_miss = ev.get("scope_miss", False)
                status.update(label="完成 ✓", state="complete", expanded=False)
        answer = "".join(buf)
        st.session_state.msgs.append(
            {"role": "assistant", "content": answer, "citations": citations,
             "scope_miss": scope_miss, "query": q})
        render_citations(citations, len(st.session_state.msgs) - 1)
        if scope_miss:
            render_scope_miss(q, len(st.session_state.msgs) - 1)
