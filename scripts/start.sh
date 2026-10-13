#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate
mkdir -p logs
CONFIG="${LITELLM_CONFIG:-config/litellm.local.yaml}"
# Load optional Azure credentials for the proxy without evaluating .env as shell code.
if [[ "$CONFIG" == "config/litellm.hybrid.yaml" ]]; then
  .venv/bin/python - <<'PY'
import os
from dotenv import dotenv_values
values = dotenv_values('.env')
for name in ('AZURE_API_BASE', 'AZURE_API_KEY', 'AZURE_API_VERSION'):
    value = os.environ.get(name) or values.get(name)
    if not value or '\n' in value or '\r' in value:
        raise SystemExit(f'{name} must be set before hybrid startup')
PY
  while IFS= read -r entry; do
    export "$entry"
  done < <(.venv/bin/python - <<'PY'
import os
from dotenv import dotenv_values
values = dotenv_values('.env')
for name in ('AZURE_API_BASE', 'AZURE_API_KEY', 'AZURE_API_VERSION'):
    print(f'{name}={os.environ.get(name) or values[name]}')
PY
  )
fi

start_service() {
  local name="$1" port="$2" command="$3"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "$name already has a listener on port $port; stop it before switching configurations" >&2
    exit 1
  fi
  nohup bash -lc "cd '$ROOT' && source .venv/bin/activate && exec $command" >"logs/$name.log" 2>&1 &
  echo $! >"logs/$name.pid"
  echo "Started $name (PID $!, port $port)"
}

start_service litellm 4000 "litellm --config '$CONFIG' --host 127.0.0.1 --port 4000"
start_service api 8000 "uvicorn app.main:app --host 127.0.0.1 --port 8000"
start_service streamlit 8501 "streamlit run ui/streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true"

for attempt in {1..60}; do
  if curl -fsS http://127.0.0.1:4000/health/liveliness >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 \
    && curl -fsS http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then
    echo "All services are ready. Open http://127.0.0.1:8501"
    exit 0
  fi
  sleep 2
done

echo "A service did not become ready. Check logs/*.log" >&2
exit 1
