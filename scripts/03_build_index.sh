#!/usr/bin/env bash
# Build/refresh the full knowledge index. Steps 1-2 need no LLM; 3-4 need the vision/LLM endpoint.
set -euo pipefail
cd /workspace/canvasclaw
source .venv/bin/activate
export HF_HOME=/workspace/canvasclaw/.hf_cache

echo "[1/4] segment lecture into units (no creds)…"
python -m engine.segment

if python -c "from config.config import settings; import sys; sys.exit(0 if settings.ready() else 1)"; then
  echo "[2/4] slide OCR via vision endpoint…"
  python -m engine.slides_ocr
  echo "[3/4] enrich unit titles + slide chunks…"
  python -m engine.slides_ocr enrich
else
  echo "[2-3/4] SKIP slide OCR (no LLM endpoint configured)"
fi

echo "[4/4] build hybrid retrieval index (local embeddings)…"
python -m engine.index >/dev/null && echo "    index built."
echo "DONE. Try:  python cli.py '老师在哪节课讲了检索增强？'"
