#!/usr/bin/env bash
set -uo pipefail
cd /workspace/canvasclaw
source .venv/bin/activate
LOG=logs/slides.log
exec > >(tee -a "$LOG") 2>&1
echo "=========== $(date) slide-keyframe start ==========="
python -m pip install -q Pillow imagehash
# remove the 2 weak scene-detect frames so the hash-based set is authoritative
rm -f data/slides/slide_0001.jpg data/slides/slide_0002.jpg data/slides/done.flag data/slides/scene.log data/slides/timestamps.txt 2>/dev/null
python scripts/extract_slides.py ../course.mp4
echo "=========== $(date) slide-keyframe DONE ==========="
