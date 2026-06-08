"""CanvasClaw public engine API used by every frontend.

    cc = CanvasClaw()
    res = cc.answer("老师在哪节课讲了检索增强？")      # -> AnswerResult
    for ev in cc.stream(...):  ...                       # status + token events

answer() runs the compiled LangGraph app (faithful to the design). stream() reuses
the same node functions but runs workers concurrently and streams the final
aggregation token-by-token (the design's '流式输出 / 异步并行').
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Iterator, Optional
from engine.schemas import AnswerResult, Citation
from engine import graph as G
from engine import llm


def _to_result(query: str, state: Dict[str, Any]) -> AnswerResult:
    cits = [Citation(**c) if not isinstance(c, Citation) else c
            for c in state.get("citations", [])]
    return AnswerResult(
        query=query, answer=state.get("answer", ""), citations=cits,
        units_used=state.get("meta", {}).get("units_used", []),
        meta=state.get("meta", {}),
    )


class CanvasClaw:
    def __init__(self):
        self.index = G.get_index()
        self._app = None

    @property
    def app(self):
        if self._app is None:
            self._app = G.build_app()
        return self._app

    # ---- non-streaming (compiled LangGraph) ----
    def answer(self, query: str, history: Optional[List[Dict[str, str]]] = None) -> AnswerResult:
        state = self.app.invoke({"query": query, "history": history or []})
        return _to_result(query, state)

    # ---- streaming (status + tokens) ----
    def stream(self, query: str,
               history: Optional[List[Dict[str, str]]] = None) -> Iterator[Dict[str, Any]]:
        idx = self.index
        history = history or []
        cq = G.ctx_query(query, history)            # fold history in for follow-ups
        ranked = idx.search_candidates(cq)
        candidates = [u for u, _ in ranked]
        yield {"type": "status", "stage": "retrieve",
               "msg": f"检索到 {len(candidates)} 个候选讲次", "candidates": candidates}

        sel = G.select_lectures_fn({"query": query, "candidates": candidates, "history": history})
        units = sel["selected_units"]
        yield {"type": "status", "stage": "route",
               "msg": "Orchestrator 选定讲次：" + ", ".join(units), "units": units}
        # tell the UI how many Worker agents are dispatched (one block each)
        yield {"type": "dispatch", "units": units}

        # fan-out workers concurrently; emit each completion as it finishes (incremental)
        outs = []
        with ThreadPoolExecutor(max_workers=max(1, len(units))) as ex:
            futs = {ex.submit(G._worker, u, cq): u for u in units}
            for fut in as_completed(futs):
                w = fut.result(); outs.append(w)
                yield {"type": "worker", "stage": "worker", "unit_id": w.unit_id,
                       "found": w.found, "done": len(outs), "total": len(units),
                       "msg": f"{w.unit_id}《{w.unit_title[:18]}》: {'命中' if w.found else '无关'}"}

        found = [w for w in outs if w.found]
        if not found:
            msg = "抱歉，在本课程已索引的讲次中没有找到与该问题直接相关的内容。"
            yield {"type": "token", "text": msg}
            yield {"type": "done", "result": AnswerResult(query=query, answer=msg).to_dict()}
            return

        cits: List[Dict[str, Any]] = []
        for w in found:
            cits.extend(c.to_dict() for c in w.citations)
        msgs = G._aggregate_messages(query, [w.to_dict() for w in found], history)
        buf = []
        for tok in llm.chat_stream(msgs):
            buf.append(tok)
            yield {"type": "token", "text": tok}
        result = AnswerResult(query=query, answer="".join(buf),
                              citations=[Citation(**c) for c in cits],
                              units_used=[w.unit_id for w in found],
                              meta={"units_used": [w.unit_id for w in found]})
        yield {"type": "citations", "citations": cits}
        yield {"type": "done", "result": result.to_dict()}


# convenience for video deep-links: HH:MM:SS -> seconds
def ts_to_sec(ts: str) -> int:
    p = [int(x) for x in ts.split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else (p[0] * 60 + p[1] if len(p) == 2 else p[0])
