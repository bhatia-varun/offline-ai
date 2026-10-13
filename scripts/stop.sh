#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for entry in streamlit:8501 api:8000 litellm:4000; do
  name="${entry%%:*}"
  port="${entry##*:}"
  pid_file="$ROOT/logs/$name.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name: no PID file; refusing to stop an untracked listener" >&2
    continue
  fi
  pid="$(cat "$pid_file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    echo "$name: invalid PID file" >&2
    exit 1
  fi
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "Stopped $name (PID $pid)"
  else
    echo "$name: process $pid is not running"
  fi
  for attempt in {1..30}; do
    if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      rm -f "$pid_file"
      break
    fi
    sleep 1
  done
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "$name: port $port is still listening; investigate before restarting" >&2
    exit 1
  fi
done
