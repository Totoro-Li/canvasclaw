#!/usr/bin/env bash
set -uo pipefail
cd /workspace/canvasclaw
source .venv/bin/activate
exec > >(tee -a logs/install_engine.log) 2>&1
echo "=========== $(date) engine deps install ==========="
python -m pip install -q --retries 5 --timeout 120 \
  torch --index-url https://download.pytorch.org/whl/cu124 || \
  python -m pip install -q --retries 5 --timeout 120 torch
python -m pip install -q --retries 5 --timeout 120 \
  sentence-transformers rank-bm25 faiss-cpu openai langgraph langchain-core
echo "[install] versions:"
python - <<'PY'
import importlib
for m in ["torch","sentence_transformers","rank_bm25","faiss","openai","langgraph","langchain_core"]:
    try:
        mod=importlib.import_module(m); print(f"  {m} {getattr(mod,'__version__','?')}")
    except Exception as e: print(f"  {m} FAIL {e}")
import torch; print("  cuda:", torch.cuda.is_available(), torch.cuda.device_count())
PY
echo "=========== $(date) engine deps DONE ==========="
echo "ENGINE_DEPS_DONE"
