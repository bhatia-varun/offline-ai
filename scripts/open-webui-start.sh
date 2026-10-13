#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -c 'import open_webui' 2>/dev/null; then
  echo "Install Open WebUI in .venv while online: .venv/bin/python -m pip install open-webui" >&2
  exit 1
fi
if ! curl -fsS --max-time 3 http://127.0.0.1:4000/health/liveliness >/dev/null; then
  echo "LiteLLM is not running. Start the local-only stack with ./scripts/start.sh first." >&2
  exit 1
fi
if lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port 3000 is already in use; not starting Open WebUI." >&2
  exit 1
fi
if [[ -f logs/open-webui.pid ]] && kill -0 "$(cat logs/open-webui.pid)" 2>/dev/null; then
  echo "Open WebUI has a tracked process already; stop it first." >&2
  exit 1
fi

mkdir -p logs
export DATA_DIR="$ROOT/open-webui/data"
mkdir -p "$DATA_DIR"
export HOST=127.0.0.1 PORT=3000
export OFFLINE_MODE=true DO_NOT_TRACK=true
export ENABLE_OLLAMA_API=false ENABLE_OPENAI_API=true
# This is a plain-chat client. Prevent unrelated Open WebUI built-in calendar calls.
export ENABLE_CALENDAR=false
export OPENAI_API_BASE_URL=http://127.0.0.1:4000/v1
export OPENAI_API_KEY="${LITELLM_API_KEY:-local-demo-key}"
# Create a stable key without printing it. The data and key stay outside version control.
if [[ ! -f "$DATA_DIR/secret_key" ]]; then
  (umask 077; openssl rand -hex 32 >"$DATA_DIR/secret_key")
fi
export WEBUI_SECRET_KEY="$(cat "$DATA_DIR/secret_key")"
nohup "$ROOT/.venv/bin/open-webui" serve --host 127.0.0.1 --port 3000 >logs/open-webui.log 2>&1 &
pid=$!
echo "$pid" >logs/open-webui.pid
for attempt in {1..60}; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f logs/open-webui.pid
    echo "Open WebUI exited; inspect logs/open-webui.log" >&2
    exit 1
  fi
  if curl -fsS --max-time 3 http://127.0.0.1:3000/health >/dev/null 2>&1; then
    echo "Open WebUI ready at http://127.0.0.1:3000 (LiteLLM model: general)."
    exit 0
  fi
  sleep 2
done
echo "Open WebUI did not become ready; inspect logs/open-webui.log" >&2
exit 1
