#!/usr/bin/env bash
# Assemble the ~1-min explainer: animation (mechanism) interleaved with the UI screen recording.
set -e
cd /workspace/canvasclaw; source .venv/bin/activate
A=video/canvasclaw_agent_anim.mp4      # Motion Canvas animation (27s, 1920x1080)
R=video/ui_walkthrough.mp4             # screen recording (79s, 1440x900)
N="scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0d1117,fps=30,format=yuv420p"

# 1) anim intro: title + query -> orchestrator -> retrieve -> route  [0:14]
ffmpeg -y -ss 0 -to 14 -i "$A" -vf "$N" -an -c:v libx264 -crf 20 /tmp/seg1.mp4 -loglevel error
# 2) screen recording, sped 3x (79s -> ~26s): home -> ask -> agent blocks -> answer -> citations -> jump
ffmpeg -y -i "$R" -vf "setpts=PTS/3.0,$N" -an -c:v libx264 -crf 20 /tmp/seg2.mp4 -loglevel error
# 3) anim outro: fan-out -> aggregate -> answer + citation spotlight  [14:end]
ffmpeg -y -ss 14 -i "$A" -vf "$N" -an -c:v libx264 -crf 20 /tmp/seg3.mp4 -loglevel error

printf "file /tmp/seg1.mp4\nfile /tmp/seg2.mp4\nfile /tmp/seg3.mp4\n" > /tmp/vlist.txt
ffmpeg -y -f concat -safe 0 -i /tmp/vlist.txt -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart \
  video/canvasclaw_explainer_1min.mp4 -loglevel error
echo "done"
