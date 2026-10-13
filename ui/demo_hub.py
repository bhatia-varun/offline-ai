"""Local-only demo launcher and presentation dashboard (Python standard library)."""
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = int(os.getenv("DEMO_HUB_PORT", "8766" if os.name == "nt" else "8765"))
SERVICES = {
    "streamlit": ("Streamlit · Chat, RAG & Tools", 8501, "/_stcore/health", "scripts/start.sh", 240),
    "webui": ("Open WebUI · Chat client", 3000, "/health", "scripts/open-webui-start.sh", 180),
    "n8n": ("n8n · Workflow automation", 5678, "/rest/settings" if os.name == "nt" else "/healthz", "scripts/n8n-start.sh", 420 if os.name == "nt" else 240),
    "comfy": ("ComfyUI · Image generation", 8188, "/system_stats", "scripts/comfyui-start.sh", 180),
}
lock = threading.Lock()
state = {key: {"phase": "idle", "message": ""} for key in SERVICES}


def healthy(key):
    _, port, path, _, _ = SERVICES[key]
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}{path}", timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def launch():
    try:
        for key, (_, _, _, script, timeout) in SERVICES.items():
            if healthy(key):
                with lock:
                    state[key] = {"phase": "ready", "message": "Already available"}
                continue
            with lock:
                state[key] = {"phase": "starting", "message": "Starting service…"}
            try:
                if os.name == "nt" and key == "comfy":
                    with lock:
                        state[key] = {"phase": "error", "message": "ComfyUI is not installed or configured on Windows"}
                    continue
                command = ([sys.executable, str(ROOT / "scripts/windows.py"), "start", "--service",
                            "core" if key == "streamlit" else key] if os.name == "nt" else ["bash", str(ROOT / script)])
                result = subprocess.run(command, cwd=ROOT,
                                        capture_output=True, text=True, timeout=timeout)
                if result.returncode != 0 and not healthy(key):
                    message = (result.stderr or result.stdout).strip().splitlines()
                    with lock:
                        state[key] = {"phase": "error", "message": (message[-1] if message else "Startup failed")[:250]}
                    continue
            except subprocess.TimeoutExpired:
                with lock:
                    state[key] = {"phase": "error", "message": "Startup timed out; check service logs"}
                continue
            except OSError:
                with lock:
                    state[key] = {"phase": "error", "message": "Launcher unavailable; check platform setup"}
                continue
            with lock:
                state[key] = {"phase": "ready" if healthy(key) else "error",
                              "message": "Ready" if healthy(key) else "Health check failed; check service logs"}
    finally:
        with lock:
            state["launching"] = False


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; frame-src http://127.0.0.1:8501 http://127.0.0.1:3000 http://127.0.0.1:5678 http://127.0.0.1:8188; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self.send(200, (ROOT / "ui/demo_hub.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/demo_hub.js":
            self.send(200, (ROOT / "ui/demo_hub.js").read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/api/status":
            with lock:
                snapshot = {key: dict(state[key]) for key in SERVICES}
                launching = state.get("launching", False)
            for key in SERVICES:
                if healthy(key):
                    snapshot[key] = {"phase": "ready", "message": "Online"}
                elif snapshot[key]["phase"] == "ready":
                    snapshot[key] = {"phase": "offline", "message": "Health check unavailable"}
            self.send(200, {"services": snapshot, "launching": launching})
        else:
            self.send(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/api/start":
            self.send(404, {"error": "Not found"})
            return
        # Only accept same-origin requests: never let another site launch local processes.
        if self.headers.get("Origin") != f"http://127.0.0.1:{PORT}":
            self.send(403, {"error": f"Open the dashboard at http://127.0.0.1:{PORT}"})
            return
        with lock:
            already_running = state.get("launching", False)
            if not already_running:
                state["launching"] = True
                for key in SERVICES:
                    if state[key]["phase"] != "ready":
                        state[key] = {"phase": "queued", "message": "Waiting for launcher"}
        if already_running:
            self.send(200, {"started": False, "message": "Startup already in progress"})
            return
        threading.Thread(target=launch, daemon=True).start()
        self.send(202, {"started": True})


if __name__ == "__main__":
    print(f"Demo hub: http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
