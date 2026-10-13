"""Native Windows lifecycle commands for the localhost-only demo."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time

import psutil
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
LOGS = ROOT / "logs"
STARTUP_TIMEOUT_SECONDS = {"n8n": 360}
SERVICES = {
    "litellm": (4000, "/health/liveliness", [str(PYTHON.parent / "litellm.exe"), "--config", "config/litellm.local.yaml", "--host", "127.0.0.1", "--port", "4000"]),
    "api": (8000, "/health", [str(PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]),
    "streamlit": (8501, "/_stcore/health", [str(PYTHON), "-m", "streamlit", "run", "ui/streamlit_app.py", "--server.address", "127.0.0.1", "--server.port", "8501", "--server.headless", "true"]),
    "hub": (8766, "/", [str(PYTHON), "ui/demo_hub.py"]),
    "webui": (3000, "/health", [str(ROOT / ".venv-webui" / "Scripts" / "open-webui.exe"), "serve", "--host", "127.0.0.1", "--port", "3000"]),
    "n8n": (5678, "/rest/settings", []),
}


def listening(port: int) -> bool:
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def healthy(name: str) -> bool:
    port, path, _ = SERVICES[name]
    try:
        return requests.get(f"http://127.0.0.1:{port}{path}", timeout=2).ok
    except requests.RequestException:
        return False


def tracked_process(name: str):
    record = LOGS / f"{name}.process.json"
    if not record.exists():
        return None
    try:
        info = json.loads(record.read_text())
        process = psutil.Process(info["pid"])
        if abs(process.create_time() - info["created"]) < 0.01 and process.cmdline() == info["command"]:
            return process
    except (OSError, ValueError, KeyError, psutil.Error):
        pass
    return None


def stop(name: str) -> None:
    process = tracked_process(name)
    if process is None:
        print(f"{name}: no matching tracked process; no listener was stopped")
        return
    processes = process.children(recursive=True) + [process]
    for child in reversed(processes):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=5)
    for child in alive:
        child.kill()
    psutil.wait_procs(alive, timeout=3)
    (LOGS / f"{name}.process.json").unlink(missing_ok=True)
    print(f"{name}: stopped")


def start(names: list[str]) -> None:
    environment = os.environ.copy()
    for key, value in dotenv_values(ROOT / ".env").items():
        if value is not None:
            environment.setdefault(key, value)
    if environment.get("CHROMA_PATH", "rag/chroma") == "rag/chroma":
        environment["CHROMA_PATH"] = "rag/chroma-windows"
    environment["DEMO_HUB_PORT"] = "8766"
    environment["ANONYMIZED_TELEMETRY"] = "False"
    environment["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    environment["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"
    if "webui" in names:
        if not Path(SERVICES["webui"][2][0]).is_file():
            raise RuntimeError("Open WebUI is optional and not installed; see the Windows README section")
        data = ROOT / "open-webui" / "data"
        data.mkdir(parents=True, exist_ok=True)
        secret = data / "secret_key"
        if not secret.exists():
            secret.write_text(secrets.token_hex(32))
        environment.update(DATA_DIR=str(data), OFFLINE_MODE="true", DO_NOT_TRACK="true",
                           ENABLE_OLLAMA_API="false", ENABLE_OPENAI_API="true", ENABLE_CALENDAR="false",
                           OPENAI_API_BASE_URL="http://127.0.0.1:4000/v1",
                           OPENAI_API_KEY=environment.get("LITELLM_API_KEY", "local-demo-key"),
                           WEBUI_SECRET_KEY=secret.read_text().strip())
    if "n8n" in names:
        node = shutil.which("node.exe")
        executable = shutil.which("n8n.cmd")
        if not node or not executable:
            raise RuntimeError("n8n is optional and not installed; install with npm.cmd install -g n8n@2.10.4")
        entry = Path(executable).parent / "node_modules" / "n8n" / "bin" / "n8n"
        if not entry.is_file():
            raise RuntimeError("Cannot locate the native npm n8n entry point")
        SERVICES["n8n"] = (5678, "/rest/settings", [node, str(entry), "start"])
        environment.update(N8N_USER_FOLDER=str(ROOT / "n8n" / "data"), N8N_HOST="127.0.0.1",
                           N8N_LISTEN_ADDRESS="127.0.0.1", N8N_PORT="5678",
                           N8N_BLOCK_ENV_ACCESS_IN_NODE="false", N8N_DIAGNOSTICS_ENABLED="false",
                           N8N_VERSION_NOTIFICATIONS_ENABLED="false",
                           LITELLM_API_KEY=environment.get("LITELLM_API_KEY", "local-demo-key"))
    if any(name in names for name in ("webui", "n8n")) and not healthy("litellm"):
        raise RuntimeError("Start the core stack before optional gateway clients")
    LOGS.mkdir(exist_ok=True)
    if "litellm" in names:
        response = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        response.raise_for_status()
        models = {model["name"] for model in response.json()["models"]}
        if "llama3.2:3b" not in models:
            raise RuntimeError("Pull llama3.2:3b in Ollama before starting")
        if "nomic-embed-text:latest" not in models:
            print("RAG needs: ollama pull nomic-embed-text")
    pending = []
    for name in names:
        port, _, command = SERVICES[name]
        if tracked_process(name) is not None and healthy(name):
            print(f"{name}: already running (tracked)")
            continue
        if listening(port) or tracked_process(name) is not None:
            raise RuntimeError(f"{name}: port {port} or tracked process already in use; inspect before restarting")
        pending.append(name)
    started = []
    try:
        for name in pending:
            command = SERVICES[name][2]
            with (LOGS / f"{name}.log").open("ab") as output:
                worker = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                          stdout=output, stderr=subprocess.STDOUT,
                                          creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            process = psutil.Process(worker.pid)
            record = {"pid": worker.pid, "created": process.create_time(), "command": process.cmdline()}
            (LOGS / f"{name}.process.json").write_text(json.dumps(record))
            started.append(name)
            print(f"{name}: started PID {worker.pid}", flush=True)
        deadline = time.monotonic() + max((STARTUP_TIMEOUT_SECONDS.get(name, 180) for name in started), default=180)
        progress_at = time.monotonic() + 15
        remaining = set(started)
        readiness_wait = threading.Event()
        while remaining and time.monotonic() < deadline:
            for name in list(remaining):
                if tracked_process(name) is None:
                    raise RuntimeError(f"{name} exited; inspect logs/{name}.log")
                if healthy(name):
                    remaining.remove(name)
                    print(f"{name}: ready at http://127.0.0.1:{SERVICES[name][0]}", flush=True)
            if remaining and time.monotonic() >= progress_at:
                for name in sorted(remaining):
                    print(f"{name}: still starting; progress log: logs/{name}.log", flush=True)
                progress_at = time.monotonic() + 15
            if remaining:
                readiness_wait.wait(1)
        if remaining:
            raise TimeoutError(f"Startup timed out: {', '.join(sorted(remaining))}; inspect logs")
    except Exception:
        for name in reversed(started):
            stop(name)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--service", choices=["core", *SERVICES], default="core")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("Use the existing .sh launchers on macOS")
    names = ["litellm", "api", "streamlit"] if args.service == "core" else [args.service]
    if args.action == "start":
        start(names)
    elif args.action == "stop":
        for name in reversed(names):
            stop(name)
    else:
        for name in names:
            print(f"{name}: healthy={healthy(name)}, tracked={tracked_process(name) is not None}, port={SERVICES[name][0]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)