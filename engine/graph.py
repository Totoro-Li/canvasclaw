"""CanvasClaw LangGraph engine — Orchestrator-Worker (report Fig.1):

  retrieve_candidates -> select_lectures (router LLM, 1..N) -> dispatch (Send fan-out)
   -> worker (RAG within ONE unit, cited) -> aggregate (merge, stream)

Node logic lives in plain functions (reused by both the compiled LangGraph app and
the streaming path in agent.py). worker_outputs uses an additive reducer so the
fan-out workers append concurrently into shared state.
"""
from __future__ import annotations
import json, re
from typing import List, Dict, Any
from config.config import settings
from engine.schemas import GraphState, Citation, WorkerOutput, AnswerResult
from engine import llm, index as index_mod

_INDEX: index_mod.LectureIndex | None = None


def get_index() -> index_mod.LectureIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = index_mod.LectureIndex.load()
    return _INDEX


# ---- precise timestamp grounding -------------------------------------------
# Chunks span ~tens of seconds, so the worker can only cite the chunk-START ts.
# We recover the TRUE time of a cited sentence by aligning the quote text back
# to the original ASR segments (which are accurate to <1s).
_SEG_CACHE: dict = {}


def _segments(lecture_id: str):
    if lecture_id not in _SEG_CACHE:
        _SEG_CACHE[lecture_id] = json.loads(
            settings.lec_transcript(lecture_id).read_text(encoding="utf-8"))["segments"]
    return _SEG_CACHE[lecture_id]


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z一-鿿]", "", (s or "").lower())


def _fmt(t: float) -> str:
    return f"{int(t//3600):02d}:{int((t%3600)//60):02d}:{int(t%60):02d}"


def _match_chunk(quote: str, chunks: list):
    """Find which evidence chunk a quote came from (used to time slide-text quotes,
    which aren't in the transcript) — returns that chunk's precise ts/start_sec."""
    qn = _norm(quote)
    if len(qn) < 6:
        return None
    for c in chunks:
        cn = _norm(c.get("text", ""))
        if cn and (qn[:10] in cn or qn[:6] in cn or cn[:10] in qn):
            return c
    return None


def ctx_query(query: str, history) -> str:
    """Fold recent user turns into the query so follow-ups (pronouns, '它', '那') keep
    context for retrieval/routing/workers. No-op when there is no history."""
    prev = [h["content"] for h in (history or []) if h.get("role") == "user"][-2:]
    return (" ".join(prev) + " " + query).strip() if prev else query


def locate_quote(quote: str, lo: float, hi: float, lecture_id: str = "L01"):
    """Return the precise start_sec where `quote` is actually spoken, by matching
    its (normalized) text against the lecture's ASR segments in [lo,hi]."""
    q = _norm(quote)
    if len(q) < 5:
        return None
    allsegs = _segments(lecture_id)
    segs = [s for s in allsegs if lo - 2 <= s["start"] <= hi + 2] or allsegs
    cat, cmap = [], []
    for s in segs:
        ns = _norm(s["text"])
        cat.append(ns); cmap.extend([s["start"]] * len(ns))
    cat = "".join(cat)
    for L in (20, 14, 10, 7):                      # progressively shorter anchors
        if len(q) >= L:
            idx = cat.find(q[:L])
            if idx >= 0:
                return cmap[idx]
    if len(q) >= 14:                               # try a middle slice
        m = len(q) // 2
        idx = cat.find(q[m:m + 8])
        if idx >= 0:
            return cmap[idx]
    return None


# ---------------- node functions ----------------
def retrieve_candidates_fn(state: GraphState) -> Dict[str, Any]:
    idx = get_index()
    ranked = idx.search_candidates(ctx_query(state["query"], state.get("history")),
                                   scope=state.get("scope"))
    return {"candidates": [uid for uid, _ in ranked],
            "meta": {**state.get("meta", {}), "candidate_scores": dict(ranked)}}


def select_lectures_fn(state: GraphState) -> Dict[str, Any]:
    idx = get_index()
    q = ctx_query(state["query"], state.get("history"))
    cands = state["candidates"][: settings.CANDIDATE_TOP_K]
    ev = idx.candidate_evidence(q, cands)           # route on real matched content
    listing = "\n".join(
        f"- {uid}（{idx.unit(uid).get('lecture_title', '')[:14]}）：" +
        ((ev.get(uid) or idx.unit(uid).get('summary', ''))[:120] or "(无)")
        for uid in cands)
    msgs = [
        {"role": "system", "content":
            "你是课程问答助手的调度器(Orchestrator)。每个候选给出了与问题匹配到的原文摘录。"
            f"选出最相关的 1 到 {settings.MAX_LECTURES_FANOUT} 个单元，覆盖回答所需内容即可。"
            "若同一规则/大纲/考核内容在多个讲次重复出现（摘录高度相似），最早讲次信息最权威，"
            "可一并选入最早与最新的讲次以便核对是否被修订。"
            '只输出 JSON：{"units":["L02-U00",...],"reason":"..."}'},
        {"role": "user", "content": f"问题：{q}\n\n候选单元（含匹配原文摘录）：\n{listing}"},
    ]
    try:
        out = llm.chat_json(msgs)
        picked = [u for u in out.get("units", []) if u in set(cands)]
    except Exception:
        picked = []
    if cands and cands[0] not in picked:            # safety net: top-retrieved always gets a worker
        picked = [cands[0]] + picked
    if not picked:
        picked = cands[: min(3, len(cands))]
    return {"selected_units": picked[: settings.MAX_LECTURES_FANOUT]}


def _worker(unit_id: str, query: str) -> WorkerOutput:
    idx = get_index()
    u = idx.unit(unit_id)
    chunks = idx.search_chunks(query, [unit_id], settings.TOP_K_CHUNKS)
    evidence = "\n".join(f"[{c['ts']} | slides {c.get('slide_indices')}] {c['text']}" for c in chunks)
    msgs = [
        {"role": "system", "content":
            f"你是课程讲次单元 {unit_id}《{u['title']}》(约 {u['ts']} 起) 的助教，依据下面提供的本单元转录/课件内容回答。"
            "found 表示本单元材料是否与问题【相关】：只要材料涉及该话题就 found=true——即便结论是『课程里没有/已过期/否定』，也要 found=true 并在 answer 给出该结论及依据；仅当材料与问题完全无关时才 found=false。"
            "忠于材料：可基于材料中【明确出现】的事实做必要的归纳与计算（如比较日期、汇总分值），但不要编造材料未写明的规则、结论或数字，也不要用『因为…所以应该…』补全未写明的规则。"
            "引用(quote)必须是材料中的逐字原文片段并给出时间戳(ts)；若该片段来自幻灯片课件而非老师口播，请在 answer 中注明『（幻灯片）』。"
            '只输出 JSON：{"found":bool,"answer":"...","citations":[{"ts":"HH:MM:SS","slide_index":int|null,"quote":"原文片段"}]}'},
        {"role": "user", "content": f"问题：{query}\n\n本单元材料：\n{evidence}\n\n本单元概要：{u.get('summary','')}"},
    ]
    try:
        out = llm.chat_json(msgs, model=settings.LLM_MODEL)
        cits = []
        for c in out.get("citations", []):
            quote = (c.get("quote") or "")[:160]
            lid = u.get("lecture_id", "L01")
            precise = locate_quote(quote, u["start_sec"], u["end_sec"], lid)  # true sentence time
            if precise is not None:
                ts, start = _fmt(precise), round(precise, 1)
            else:
                mc = _match_chunk(quote, chunks)     # slide-text quote -> precise slide time
                if mc is not None:
                    ts, start = mc["ts"], round(mc["start_sec"], 1)
                else:                                # last resort: LLM ts / unit start
                    ts, start = c.get("ts") or u["ts"], u["start_sec"]
            try:                                    # LLM may emit slide_index as str/float
                si = int(c["slide_index"]) if c.get("slide_index") is not None else None
            except (TypeError, ValueError):
                si = None
            cits.append(Citation(unit_id=unit_id, unit_title=u["title"], ts=ts,
                                 start_sec=start, end_sec=u["end_sec"],
                                 lecture_id=lid, lecture_title=u.get("lecture_title", ""),
                                 slide_index=si, quote=quote))
        return WorkerOutput(unit_id=unit_id, unit_title=u["title"],
                            answer=out.get("answer", ""), found=bool(out.get("found")),
                            citations=cits)
    except Exception as e:                           # noqa: BLE001
        return WorkerOutput(unit_id=unit_id, unit_title=u["title"],
                            answer=f"(worker error: {e})", found=False, citations=[])


def worker_fn(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph worker node: receives a Send payload {unit_id, query}."""
    out = _worker(state["unit_id"], state["query"])
    return {"worker_outputs": [out.to_dict()]}


def dispatch(state: GraphState):
    """Conditional edge: fan out one Send per selected unit."""
    from langgraph.types import Send
    cq = ctx_query(state["query"], state.get("history"))
    return [Send("worker", {"unit_id": uid, "query": cq})
            for uid in state["selected_units"]]


def _aggregate_messages(query: str, found: List[dict], history=None) -> List[Dict[str, str]]:
    blocks = "\n\n".join(
        f"【{w['unit_id']}《{w['unit_title']}》】\n{w['answer']}" for w in found)
    convo = ""
    if history:
        convo = "对话历史（供理解指代/上下文）：\n" + "\n".join(
            f"{h['role']}: {h['content'][:200]}" for h in history[-4:]) + "\n\n"
    return [
        {"role": "system", "content":
            "你是课程学习助手 CanvasClaw 的主智能体。综合各讲次助教的回答，为学生给出"
            "统一、准确、有条理的中文回答；明确标注信息来自哪一讲次及时间戳；多处重复请去重；"
            "若材料不足以回答，请如实说明。不要编造课程中没有的内容。"
            "【冲突处理】当不同讲次对同一课程规则/分数给出不同数值时，这通常是大纲在学期中被修订——"
            "请同时给出各版本及其讲次出处（例如『原始 50 分，后修订为 50–60 分』），不要擅自折中或只取其一。"
            "【拒绝伪证】只采信材料中【明确陈述】的事实；若某讲次的回答是靠推测/『应该』得出、并无原文明文支持，"
            "不要采纳它，更不要把这种推测与明确事实并列成『两种说法』制造虚假对立——以明确写明的规则为准。"},
        {"role": "user", "content": f"{convo}学生当前问题：{query}\n\n各讲次助教的回答：\n{blocks}"},
    ]


def aggregate_fn(state: GraphState) -> Dict[str, Any]:
    found = [w for w in state.get("worker_outputs", []) if w.get("found")]
    cits: List[dict] = []
    for w in found:
        cits.extend(w.get("citations", []))
    if not found:
        scoped = bool(state.get("scope"))
        msg = ("在所选的限定范围内没有找到与该问题相关的内容（可在全部讲次中重新搜索）。"
               if scoped else "抱歉，在本课程已索引的讲次中没有找到与该问题直接相关的内容。")
        return {"answer": msg, "citations": [],
                "meta": {**state.get("meta", {}), "units_used": [], "scope_miss": scoped}}
    answer = llm.chat(_aggregate_messages(state["query"], found, state.get("history")),
                      model=settings.LLM_MODEL)
    return {"answer": answer, "citations": cits,
            "meta": {**state.get("meta", {}), "units_used": [w["unit_id"] for w in found]}}


# ---------------- compiled LangGraph app ----------------
def build_app():
    from langgraph.graph import StateGraph, START, END
    g = StateGraph(GraphState)
    g.add_node("retrieve_candidates", retrieve_candidates_fn)
    g.add_node("select_lectures", select_lectures_fn)
    g.add_node("worker", worker_fn)
    g.add_node("aggregate", aggregate_fn)
    g.add_edge(START, "retrieve_candidates")
    g.add_edge("retrieve_candidates", "select_lectures")
    g.add_conditional_edges("select_lectures", dispatch, ["worker"])
    g.add_edge("worker", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()
