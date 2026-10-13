#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PID_FILE="$ROOT/image/logs/comfyui.pid"
PYTHON="$ROOT/image/venv/bin/python"
CHECKPOINT="$ROOT/image/models/v1-5-pruned-emaonly.safetensors"
if [[ ! -x "$PYTHON" || ! -f "$ROOT/image/comfyui/main.py" || ! -s "$CHECKPOINT" ]]; then
  echo "ComfyUI installation or checkpoint missing; see README (Phase E)" >&2
  exit 1
fi
if lsof -nP -iTCP:8188 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 8188 is occupied; will not start an unrelated image service" >&2
  exit 1
fi
mkdir -p image/output image/input image/temp image/logs image/user
nohup "$PYTHON" "$ROOT/image/comfyui/main.py" \
  --listen 127.0.0.1 --port 8188 --offline --disable-all-custom-nodes \
  --disable-auto-launch --output-directory "$ROOT/image/output" \
  --input-directory "$ROOT/image/input" --temp-directory "$ROOT/image/temp" \
  --user-directory "$ROOT/image/user" >"$ROOT/image/logs/comfyui.log" 2>&1 &
pid=$!
printf '%s\n' "$pid" >"$PID_FILE"
echo "Starting ComfyUI (PID $pid, localhost:8188). Stop with ./scripts/comfyui-stop.sh"
for attempt in {1..60}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "ComfyUI exited; inspect image/logs/comfyui.log" >&2
    exit 1
  fi
  if curl -fsS --max-time 2 http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    echo "ComfyUI ready at http://127.0.0.1:8188"
    exit 0
  fi
  sleep 2
done
echo "ComfyUI not ready; inspect image/logs/comfyui.log and stop with ./scripts/comfyui-stop.sh" >&2
exit 1
