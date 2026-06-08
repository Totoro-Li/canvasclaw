#!/usr/bin/env bash
# CanvasClaw data-prep pipeline (answer-independent): venv + faster-whisper + ASR + slide frames.
set -uo pipefail
cd /workspace/canvasclaw
export HF_HOME=/workspace/canvasclaw/.hf_cache
mkdir -p "$HF_HOME" data data/slides logs
LOG=logs/dataprep.log
exec > >(tee -a "$LOG") 2>&1
echo "=========== $(date) dataprep start ==========="

# 1) venv + faster-whisper (CTranslate2; bundles CUDA, no torch needed)
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -q --upgrade pip
echo "[pip] installing faster-whisper + cudnn/cublas ..."
python -m pip install -q faster-whisper "nvidia-cudnn-cu12==9.*" "nvidia-cublas-cu12" || {
  echo "[pip] FAILED faster-whisper install"; }
# expose bundled cudnn/cublas to ctranslate2
CUDNN_DIR=$(python -c "import os,nvidia.cudnn,nvidia.cublas; print(os.path.dirname(nvidia.cudnn.__file__)+'/lib:'+os.path.dirname(nvidia.cublas.__file__)+'/lib')" 2>/dev/null)
export LD_LIBRARY_PATH="${CUDNN_DIR}:${LD_LIBRARY_PATH:-}"
echo "[env] LD_LIBRARY_PATH=$LD_LIBRARY_PATH"

# 2) extract 16k mono wav (source audio is already 16k mono aac)
if [ ! -f data/audio.wav ]; then
  echo "[ffmpeg] extracting audio ..."
  ffmpeg -y -i ../course.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le data/audio.wav -loglevel error
fi
echo "[ffmpeg] audio: $(du -h data/audio.wav | cut -f1)"

# 3) slide-frame extraction via scene-change detection (parallel-safe, fast)
if [ ! -f data/slides/done.flag ]; then
  echo "[ffmpeg] extracting slide frames (scene>0.30) ..."
  ffmpeg -y -i ../course.mp4 -vf "select='gt(scene,0.30)',showinfo,scale=1280:-1" \
    -vsync vfr data/slides/slide_%04d.jpg -loglevel info 2> data/slides/scene.log
  # capture pts_time for each extracted frame from showinfo log
  grep -oE "pts_time:[0-9.]+" data/slides/scene.log | sed 's/pts_time://' > data/slides/timestamps.txt 2>/dev/null || true
  ls data/slides/*.jpg 2>/dev/null | wc -l | xargs echo "[ffmpeg] extracted slide frames:"
  touch data/slides/done.flag
fi

# 4) ASR transcription (the long pole)
echo "[asr] starting transcription ..."
python scripts/transcribe.py data/audio.wav data/transcript.json

echo "=========== $(date) dataprep DONE ==========="
echo "ALLDONE_MARKER"
