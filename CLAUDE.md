# CLAUDE.md — working in the CanvasClaw repo

Guidance for AI agents (Claude Code) editing this codebase. Keep changes minimal and match the
surrounding style.

## What this is
A LangGraph **Orchestrator–Worker** multi-agent assistant that answers questions over a whole
semester of lecture videos with **lecture-grained routing** and **timestamp/slide-grounded
citations**. Pipeline: `video → ASR → slide keyframes → vision OCR → hybrid (bge+BM25) index →
orchestrator routes to parallel Worker RAG → aggregate (cited, streamed)`.

## Architecture & where things live
- `config/config.py` — all settings (`Settings`), read from `config/.env`. Most knobs are env-overridable.
- `engine/schemas.py` — **locked data contract** (Chunk / LectureUnit / Citation / AnswerResult / GraphState).
  Change shapes here first; everything imports from it.
- `engine/llm.py` — provider-agnostic: `chat / chat_json / chat_stream / vision_describe` (any
  OpenAI-compatible endpoint) + `embed` (LOCAL bge on GPU/CPU). All LLM access funnels through here.
- `engine/index.py` — `LectureIndex`: hybrid retrieval, `search_candidates(query, scope=…)` (unit routing),
  `search_chunks` (worker RAG). Build/persist to `data/index/` (`emb.npy` + `store.json`).
- `engine/graph.py` — LangGraph nodes: `retrieve_candidates → select_lectures → dispatch (Send fan-out)
  → worker → aggregate`. **Worker & aggregator prompts live here** — they encode faithfulness rules
  (no fabricating quotes, resolve conflicting numbers as syllabus revisions, `found`=relevance).
- `engine/agent.py` — **public API**: `CanvasClaw().answer(q, history=…, scope=…)` and `.stream(...)`.
  `stream()` emits `status / dispatch / worker / token / citations / done` events (the UI's agent blocks
  + scope-miss handling depend on these).
- `engine/{segment,slides_ocr,ingest}.py` — ingestion: transcript+slides → units/chunks; vision OCR.
- `frontend/streamlit_app.py` — chat UI (model selector, scope selector, agent-status blocks,
  jump-to-timestamp). `frontend/feishu_bot.py` — Feishu bot.
- `tools/` — eval (`ask_batch`, `gen_questions`), ablation (`ablation_metrics`, `run_settings_ablation`,
  `scope_eval`, `judge_*.js` = Workflow scripts), media (`capture_ui`, `mc_render`, `make_video`).

## Data layout (gitignored — regenerated, not committed)
`data/lectures/<id>/{audio.wav, transcript.json, slides/, units.json, meta.json}` ·
`data/lectures.json` (manifest) · `data/index/` (global index) · `data/eval/` (eval outputs).

## Common commands
```bash
# ingest a semester (CUDA box; videos listed in data/videos.csv = lecture_id|video|title|week)
ASR_LANG=zh MAXPAR=4 bash scripts/ingest_all.sh
python tools/enrich_titles.py && python tools/ocr_all.py && python -m engine.index   # titles + slide OCR
# run
python cli.py --stream "老师在哪节课讲了检索增强？"
streamlit run frontend/streamlit_app.py --server.fileWatcherType none
# eval / ablation
python tools/gen_questions.py && python tools/ask_batch.py --in data/eval/questions.json --out data/eval/results.json
python tools/scope_eval.py            # scope + faithful-none experiment
```
Override knobs via env: `HYBRID_ALPHA`, `MAX_LECTURES_FANOUT`, `TOP_K_CHUNKS`, `CHUNK_MAX_CHARS`,
`INDEX_DIR`, `EXCLUDE_SLIDE_CHUNKS`, `EMBED_DEVICE`, `ASR_LANG`, `LLM_MODEL`, `ROUTER_MODEL`.

## Gotchas (learned the hard way)
- **Streamlit needs `torchvision` installed** (transformers lazily imports image processors) and
  `--server.fileWatcherType none`. Launch it from a normal shell / `run_in_background`, **not** via a
  stale tmux/nohup env.
- **faster-whisper is CUDA-only**, ASR is flaky without `ASR_LANG=zh` + `condition_on_previous_text=False`
  (language misdetect + decoder-cascade truncation). Run ASR sequentially-ish; ffmpeg needs `-nostdin`.
- **Never commit secrets**: `config/.env` (+ `*.bak`) are gitignored; use `config/.env.example`.
  `data/`, `.venv/`, `.hf_cache/`, `*.zip`, `video/mc/{node_modules,output}` are also ignored.
- Embeddings are **local** (no creds needed); only chat/vision hit the endpoint.

## Conventions
- Citations must trace to real ASR/slide text (the engine verifies); workers must not invent quotes.
- When adding retrieval/LLM behavior, thread it through `engine/agent.py` (both `answer` and `stream`).
- Verify UI changes headlessly with `streamlit.testing.v1.AppTest` (see how the existing tests drive it).
