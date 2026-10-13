#!/bin/bash
set -u

check() {
  local name="$1" url="$2"
  if curl -fsS --max-time 4 "$url" >/dev/null 2>&1; then
    echo "$name: UP ($url)"
  else
    echo "$name: DOWN ($url)"
  fi
}

check Ollama http://127.0.0.1:11434/api/version
check LiteLLM http://127.0.0.1:4000/health/liveliness
check FastAPI http://127.0.0.1:8000/health
check Streamlit http://127.0.0.1:8501/_stcore/health
