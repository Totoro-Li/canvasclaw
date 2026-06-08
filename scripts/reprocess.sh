#!/usr/bin/env bash
set -uo pipefail
cd /workspace/canvasclaw; source .venv/bin/activate
export HF_HOME=/workspace/canvasclaw/.hf_cache
while IFS='|' read -r lid video title week; do
  [ "$lid" = "lecture_id" ] && continue; [ -z "${lid// }" ] && continue
  python -m engine.ingest --video "$video" --id "$lid" --title "$title" --week "$week" --ocr \
     > "logs/reproc_${lid}.log" 2>&1 &
done < data/videos.csv
wait
echo "[reprocess] re-segment+OCR done; rebuilding index…"
python -m engine.index > logs/reproc_index.log 2>&1 && echo "REPROCESS_DONE"
