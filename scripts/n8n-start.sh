#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
NODE_BIN="$HOME/.nvm/versions/node/v24.16.0/bin"
if [[ ! -x "$NODE_BIN/node" ]]; then
  echo "Node 24 is required at $NODE_BIN (no download performed)" >&2
  exit 1
fi
export PATH="$NODE_BIN:$PATH"
if lsof -nP -iTCP:5678 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 5678 is already listening; not starting another n8n" >&2
  exit 1
fi
export N8N_USER_FOLDER="$ROOT/n8n/data"
export N8N_HOST=127.0.0.1 N8N_LISTEN_ADDRESS=127.0.0.1 N8N_PORT=5678
export N8N_BLOCK_ENV_ACCESS_IN_NODE=false
export N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
export N8N_DIAGNOSTICS_ENABLED=false N8N_VERSION_NOTIFICATIONS_ENABLED=false
export LITELLM_API_KEY="${LITELLM_API_KEY:-local-demo-key}"
mkdir -p "$N8N_USER_FOLDER" logs
nohup n8n start >logs/n8n.log 2>&1 &
echo $! >logs/n8n.pid
echo "Started n8n (PID $!, localhost:5678). Stop: ./scripts/n8n-stop.sh"
for attempt in {1..90}; do
  if curl -fsS --max-time 3 http://127.0.0.1:5678/healthz >/dev/null 2>&1; then
    echo "n8n ready at http://127.0.0.1:5678"
    exit 0
  fi
  sleep 2
done
echo "n8n did not become ready; check logs/n8n.log" >&2
exit 1
