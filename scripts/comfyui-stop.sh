#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/image/logs/comfyui.pid"
if [[ ! -f "$PID_FILE" ]]; then
  echo "ComfyUI: no tracked PID; not stopping unrelated processes" >&2
  exit 1
fi
pid="$(cat "$PID_FILE")"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  echo "ComfyUI: invalid PID file" >&2
  exit 1
fi
if kill -0 "$pid" 2>/dev/null; then
  command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  if [[ "$command_line" != *"$ROOT/image/comfyui/main.py"* ]]; then
    echo "PID $pid no longer matches project ComfyUI; refusing to kill" >&2
    exit 1
  fi
  kill "$pid"
  echo "Stopping ComfyUI (PID $pid)"
fi
for attempt in {1..30}; do
  if ! lsof -nP -iTCP:8188 -sTCP:LISTEN >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "ComfyUI stopped"
    exit 0
  fi
  sleep 1
done
echo "Port 8188 still listening; investigate before restarting" >&2
exit 1
