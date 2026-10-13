#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FILE="$ROOT/logs/n8n.pid"
if [[ ! -f "$FILE" ]]; then
  echo "n8n: no tracked PID; not stopping an unrelated process" >&2
  exit 1
fi
pid="$(cat "$FILE")"
if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
  echo "n8n: invalid PID file" >&2
  exit 1
fi
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  echo "Stopped n8n (PID $pid)"
fi
for attempt in {1..30}; do
  if ! lsof -nP -iTCP:5678 -sTCP:LISTEN >/dev/null 2>&1; then
    rm -f "$FILE"
    exit 0
  fi
  sleep 1
done
echo "Port 5678 still listening; investigate before restarting" >&2
exit 1
