# CanvasClaw 🎓 — 多智能体课程问答助手

A faithful implementation of the team's midterm-survey design: a **LangGraph
Orchestrator–Worker multi-agent** assistant that answers natural-language
questions about a lecture, with **lecture-grained routing** and
**timestamp/slide-cited** answers. Demo course = `course.mp4` (55-min lecture on
*记忆管理与检索增强*).

## Architecture (maps 1:1 to the 调研报告)

```
student question
   │  Feishu bot  /  Streamlit                       ← frontend (报告 §6)
   ▼
retrieve_candidates → select_lectures(router LLM, 1–N) → dispatch(fan-out)
   → worker × N (RAG within one lecture unit, cited) → aggregate(merge + stream)
   └──────────────────────  LangGraph  (报告 §4–5, Fig.1)  ──────────────────────┘
```

| Design decision (report) | Here |
|---|---|
| Orchestrator–Worker (报告 §4.2) | `engine/graph.py` nodes + `Send` fan-out |
| LangGraph + State Reducer (§5) | `GraphState.worker_outputs` additive reducer |
| LLM = DeepSeek-V3.2, provider-flexible (§5) | `engine/llm.py`, any OpenAI-compatible endpoint via `config/.env` |
| ASR Whisper large-v3 + word ts (§2) | `scripts/transcribe.py` (faster-whisper, GPU) |
| 2-stage question detection (§2.3) | regex stage in `transcribe.py`; LLM stage in worker |
| PPT parse + VLM fallback (§3) | `engine/slides_ocr.py` (perceptual-hash keyframes + vision OCR) |
| PPT↔video alignment {slide_index,start,end} (§3.2) | `engine/segment.py` + `slides/slides.json` |
| Feishu bot, cards, sessions (§6) | `frontend/feishu_bot.py` (lark-cli events + interactive card) |

## Layout
```
config/config.py      central settings (reads config/.env)
engine/schemas.py     locked data contract
engine/llm.py         OpenAI-compatible chat/vision + local bge embeddings
engine/segment.py     transcript+slides → time-balanced lecture units + chunks
engine/slides_ocr.py  vision OCR per slide → titles + slide chunks
engine/index.py       hybrid (bge + BM25) retrieval; unit routing + chunk search
engine/graph.py       LangGraph Orchestrator-Worker
engine/agent.py       CanvasClaw.answer() / .stream()   ← public API
frontend/streamlit_app.py   chat UI + slide thumbnails + jump-to-timestamp video
frontend/feishu_bot.py      Feishu bot (interactive cards, multi-turn)
cli.py                quick test
data/                 transcript.json · slides/ · lecture_units.json · index/
```

## Setup
1. Data prep (already run on GPU): `bash scripts/01_dataprep.sh` (ASR) + slide keyframes.
2. Put your LLM endpoint in `config/.env` (copy from `config/.env.example`):
   ```
   OPENAI_BASE_URL=...   OPENAI_API_KEY=...   LLM_MODEL=...   VISION_MODEL=...
   ```
3. Build the knowledge index: `bash scripts/03_build_index.sh`
4. Use it:
   ```
   python cli.py --stream "老师在哪节课讲了检索增强？"
   streamlit run frontend/streamlit_app.py        # web demo
   python frontend/feishu_bot.py                   # Feishu bot
   ```

## Full-semester evaluation & ablation

Validated end-to-end on a **full 26-lecture semester** (~23 h; 19 lectures with usable audio, 7 source-broken). 48-question battery (factual / locate / compare / out-of-scope) scored by a **244-agent adversarial LLM judge**.

**Foundation-model ablation** (identical battery, same retrieval/prompts, swap only the LLM):

| Model | Correct (judged) | Faithful | Quality | Routing | Grounding | Latency |
|---|---|---|---|---|---|---|
| **qwen3.6-plus** ⭐ | 56% | 4.23 | 3.90 | 44/48 | 97% | 160 s |
| deepseek-v4-flash | 48% | 3.71 | 3.54 | 40/48 | 83% | 35 s |
| gpt-5.5 | 40% | 3.92 | 3.15 | 40/48 | 100% | 35 s |

**Settings ablation:** hybrid retrieval (α=0.5) routing **71%** vs vector-only 55% vs BM25-only 68%; cross-lecture fan-out is critical (fanout=1 → routing 50%); top-k 3/6/12 barely matters.

Extras: runtime **model selector** (auto-detects `/v1/models`), **live multi-agent status blocks** in the UI, and an auto-generated **~1-min explainer video** (screen recording + Motion Canvas animation, see `video/`). Full report + methodology in `reports/`.

## Status
- ✅ Multi-lecture pipeline (ASR → slides → OCR → hybrid index), Orchestrator–Worker RAG, timestamp/slide-cited answers — verified on a full semester.
- ✅ Streamlit UI (model selector, agent-status blocks, jump-to-timestamp) + Feishu bot.
- ▶️ Quickstart: `pip install -r requirements.txt`, copy `config/.env.example` → `config/.env`, ingest videos (`scripts/ingest_all.sh`), then `streamlit run frontend/streamlit_app.py`.
