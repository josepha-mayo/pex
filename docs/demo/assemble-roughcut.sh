#!/bin/bash
# Rough-cut assembly for the <3min hackathon video.
# Segments follow docs/demo/FOOTAGE_MANIFEST.md beat order.
set -e
cd "$(dirname "$0")/../.."
A=docs/demo/assets
OUT=build/cut-segs
mkdir -p "$OUT"
FONT="'C\:/Windows/Fonts/arial.ttf'"
RES=1280:800

# Beat-card style overlay: centered uppercase label at top-left, thin rule.
overlay() { echo "drawtext=fontfile=$FONT:text='$1':fontsize=30:fontcolor=0x7ee0b8:x=48:y=48"; }

# 0 — title card (4s)
ffmpeg -y -f lavfi -i color=c=0x0b0f10:s=1280x800:d=4 \
  -vf "drawtext=fontfile=$FONT:text='PEX':fontsize=96:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-30,drawtext=fontfile=$FONT:text='goal-aware supervision for coding agents':fontsize=30:fontcolor=0x7ee0b8:x=(w-text_w)/2:y=(h-text_h)/2+60" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s0-title.mp4"

# 1 — claim ledger cold open (18s -> 33s)
ffmpeg -y -ss 24 -t 15 -i $A/pex-claim-ledger-2193282.mp4 \
  -vf "scale=$RES,$(overlay 'WORKER CLAIM vs WORKSPACE EVIDENCE')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s1-ledger.mp4"

# 2 — injection diff hold (6s)
ffmpeg -y -loop 1 -t 6 -i $A/pex-injection-diff.png \
  -vf "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2:0x0b0f10,$(overlay 'CONFIG INJECTION CAUGHT')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s2-injection.mp4"

# 3 — MCP eval (20s -> 30s)
ffmpeg -y -ss 20 -t 10 -i $A/pex-mcp-eval.mp4 \
  -vf "scale=$RES,$(overlay 'WORKER MCP SURFACE')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s3-mcp.mp4"

# 4 — ruling arc centerpiece (42s -> 57s)
ffmpeg -y -ss 42 -t 15 -i $A/pex-ruling-arc-eabd646.mp4 \
  -vf "scale=$RES,$(overlay 'DURABLE HUMAN RULING')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s4-ruling.mp4"

# 5 — escalation arc (8s -> 20s)
ffmpeg -y -ss 8 -t 12 -i $A/pex-escalation-arc-6d16888.mp4 \
  -vf "scale=$RES,$(overlay 'WORKER ESCALATES, PEX ROUTES')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s5-escalation.mp4"

# 6 — positive control tail (33s -> 45s)
ffmpeg -y -ss 33 -t 12 -i $A/pex-replay-walkthrough-b28d999.mp4 \
  -vf "scale=$RES,$(overlay 'EVIDENCE EARNS verified_complete')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s6-verified.mp4"

# 7 — pack verify hold (6s)
ffmpeg -y -loop 1 -t 6 -i $A/pex-pack-verify-browser.png \
  -vf "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2:0x0b0f10,$(overlay 'SELF-VERIFYING EVIDENCE PACK')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s7-pack.mp4"

# 8 — live tamper catch (60s -> 70s)
ffmpeg -y -ss 60 -t 10 -i $A/pex-live-tamper-demo.mp4 \
  -vf "scale=$RES,$(overlay 'LIVE WORKER — TAMPER CAUGHT')" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s8-live.mp4"

# 9 — end card (6s)
ffmpeg -y -f lavfi -i color=c=0x0b0f10:s=1280x800:d=6 \
  -vf "drawtext=fontfile=$FONT:text='NVIDIA Nemotron on Nebius Token Factory':fontsize=40:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-40,drawtext=fontfile=$FONT:text='nvidia/nemotron-3-super-120b-a12b':fontsize=26:fontcolor=0x7ee0b8:x=(w-text_w)/2:y=(h-text_h)/2+20,drawtext=fontfile=$FONT:text='github.com/josepha-mayo/pex':fontsize=26:fontcolor=0x9fb4ad:x=(w-text_w)/2:y=(h-text_h)/2+70" \
  -c:v libx264 -pix_fmt yuv420p "$OUT/s9-end.mp4"

cat > "$OUT/concat.txt" <<EOF
file 's0-title.mp4'
file 's1-ledger.mp4'
file 's2-injection.mp4'
file 's3-mcp.mp4'
file 's4-ruling.mp4'
file 's5-escalation.mp4'
file 's6-verified.mp4'
file 's7-pack.mp4'
file 's8-live.mp4'
file 's9-end.mp4'
EOF

ffmpeg -y -f concat -safe 0 -i "$OUT/concat.txt" -c copy build/pex-demo-roughcut.mp4
ffprobe -v quiet -show_entries format=duration -of csv=p=0 build/pex-demo-roughcut.mp4
