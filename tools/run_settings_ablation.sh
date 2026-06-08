#!/usr/bin/env bash
# Tunable-settings ablation on a fixed model. Each run = full 48-q eval with one
# knob changed; compare via AUTO metrics (routing hit / grounding / latency).
# Usage: bash tools/run_settings_ablation.sh "aliyun/deepseek-v4-flash"
cd /workspace/canvasclaw; source .venv/bin/activate; export HF_HOME=/workspace/canvasclaw/.hf_cache
MODEL="${1:-aliyun/deepseek-v4-flash}"; Q=data/eval/questions.json
run(){ name="$1"; shift
  echo "=== [$(date +%H:%M)] $name : $* ==="
  env "$@" CUDA_VISIBLE_DEVICES=0 LLM_MODEL="$MODEL" ROUTER_MODEL="$MODEL" \
    python tools/ask_batch.py --in "$Q" --out "data/eval/abl_$name.json" --conc 6 2> "logs/abl_$name.log"
  echo "  $(grep 'DONE 48' logs/abl_$name.log)"; }

run base                                    # defaults: alpha0.5 fanout5 topk6
run alpha0   HYBRID_ALPHA=0.0               # BM25-only retrieval
run alpha1   HYBRID_ALPHA=1.0               # vector-only retrieval
run fanout1  MAX_LECTURES_FANOUT=1          # single-lecture (no cross-lecture fan-out)
run topk3    TOP_K_CHUNKS=3                  # less per-worker context
run topk12   TOP_K_CHUNKS=12                 # more per-worker context
echo SETTINGS_ABLATION_DONE
