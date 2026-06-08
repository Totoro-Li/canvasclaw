#!/usr/bin/env bash
# Parallel multi-GPU ingestion of a full semester, then build the global index.
# Input CSV (pipe-delimited, header skipped):  lecture_id|video|title|week
#   data/videos.csv
# Each lecture is ingested on its own GPU (round-robin); up to $MAXPAR concurrent.
set -uo pipefail
cd /workspace/canvasclaw
source .venv/bin/activate
export HF_HOME=/workspace/canvasclaw/.hf_cache
CSV="${1:-data/videos.csv}"
NGPU=$(nvidia-smi -L 2>/dev/null | wc -l); [ "${NGPU:-0}" -lt 1 ] && NGPU=1
MAXPAR="${MAXPAR:-$NGPU}"
mkdir -p logs
echo "[ingest_all] csv=$CSV  GPUs=$NGPU  parallel=$MAXPAR"

i=0
# Read the CSV on fd 3 (not stdin) AND give each child </dev/null, so backgrounded
# ffmpeg can't inherit the CSV as stdin and consume lines (which silently dropped
# lectures from the loop). Belt-and-suspenders against the stdin-eating bug.
while IFS='|' read -r lid video title week <&3; do
  [ "$lid" = "lecture_id" ] && continue
  [ -z "${lid// }" ] && continue
  gpu=$(( i % NGPU ))
  echo "[ingest_all] -> $lid on GPU $gpu : $video"
  CUDA_VISIBLE_DEVICES=$gpu python -m engine.ingest \
      --video "$video" --id "$lid" --title "$title" ${week:+--week "$week"} \
      < /dev/null > "logs/ingest_${lid}.log" 2>&1 &
  i=$((i+1))
  while [ "$(jobs -r | wc -l)" -ge "$MAXPAR" ]; do sleep 2; done
done 3< "$CSV"
wait
echo "[ingest_all] ingestion done; building GLOBAL index…"
python -m engine.index >/dev/null 2>&1 && echo "[ingest_all] index built ✓"
echo "INGEST_ALL_DONE"
