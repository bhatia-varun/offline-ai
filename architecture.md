# Repository architecture

## Purpose and system boundary

This repository is a localhost-first AI stack demo for Apple Silicon Macs and Windows x64 laptops. Streamlit presents application features; FastAPI owns orchestration; LiteLLM supplies an OpenAI-compatible **text-generation** gateway; Ollama runs local generation and embedding models. Optional Open WebUI and n8n are independent consumers of that same gateway. Speech transcription and the MCP tool server are separate local capabilities, not LiteLLM providers.

```text
Browser -> Streamlit :8501 -> FastAPI :8000 -> LiteLLM :4000 -> Ollama :11434
                                   |                `-> optional Azure (hybrid config)
                                   |-> Ollama /api/embed -> Chroma (local disk)
                                   |-> local calculator/weather or on-demand stdio MCP
                                   `-> local platform-specific Whisper worker (speech to text)
Browser -> optional Open WebUI :3000 ------> LiteLLM :4000
Webhook -> optional n8n :5678 ------------> LiteLLM :4000
```

The arrows distinguish ownership: **all application text generation goes through LiteLLM** using logical model names `general` and `agent`. RAG embeddings deliberately call Ollama directly; the platform-specific Whisper implementation does not use either Ollama or LiteLLM. Unless the optional hybrid configuration is selected, the supported stack runs without an external inference service after dependencies and models are installed.

## Windows runtime

Use Python 3.11 x64 in `.venv\Scripts\python.exe`. The core Python application,
Chroma, Ollama and stdio MCP run natively without WSL. `scripts/windows.py`
provides `start`, `status` and `stop` for the core; `--service hub` manages the
presentation dashboard on **8766**, avoiding the existing listener on 8765.
The launcher selects only `config/litellm.local.yaml` (`llama3.2:3b`), requires
Ollama to be running and binds its services to localhost. It verifies process
identity with PID, creation time and command before stopping tracked trees;
it never stops Ollama or untracked port owners. Failed startup rolls back only
processes created in that invocation.

On Windows, `app/stt.py` selects **faster-whisper** with
`Systran/faster-whisper-tiny.en`, CPU/int8 inference and pre-cached files only.
Apple Silicon retains MLX; imports are deferred so Windows never imports MLX.
Both paths retain the same WAV API, input bounds, spawned worker and deadline.
The MCP SDK is constrained to `>=1.26,<2` because the server uses the v1
`FastMCP` API. The launcher maps the copied default Chroma location to
`rag/chroma-windows/` and requires a fresh ingest, preserving the Mac index and
all copied optional-client data. Custom Chroma locations remain configurable.

Optional `--service webui` and `--service n8n` use native entry points after
their separate installations. Open WebUI 0.11.4 is installed in isolated
`.venv-webui` (not the core `.venv`); n8n 2.10.4 uses global npm and Node 24.
Both clients passed health/browser sign-in checks. The configured Open WebUI
gateway connection and preserved n8n production summary workflow were tested;
authenticated browser use requires signing in to the copied local accounts.
Both data directories were backed up before startup. Calendar is disabled in
Open WebUI's persisted settings. The hub reports missing optional clients and
skips unconfigured ComfyUI rather than attempting Bash on Windows. No image installation,
checkpoint or image API was added. The Windows launcher does not select
hybrid mode. See `README.md` for platform-specific commands and verification.

## Components and services

| Component | Code/configuration | Role and dependencies |
| --- | --- | --- |
| Streamlit UI | `ui/streamlit_app.py`, `ui/live_audio.py` | Browser tabs for chat, private RAG, tools/agent and speech-to-text. Calls FastAPI at `DEMO_API_URL` (default `http://127.0.0.1:8000`). Live audio is a browser-side Streamlit component that calls the audio endpoint directly. |
| FastAPI | `app/main.py`, `app/settings.py` | HTTP API, input bounds, response/error mapping and feature orchestration. `GET /health` probes Ollama and LiteLLM; the health response does not test all models or optional services. CORS permits the localhost Streamlit origin. |
| Text gateway | `app/llm.py`, `config/litellm.local.yaml`, `config/litellm.hybrid.yaml` | OpenAI Python client calls LiteLLM at `LITELLM_BASE_URL` (default `http://127.0.0.1:4000/v1`). The local config maps both `general` and `agent` to `ollama_chat/llama3.2:3b` on Ollama. The hybrid config instead puts `ollama_chat/qwen3:14b` first and `azure/gpt-6-sol` second for each logical name; Azure fallback is configured but not verified. |
| Local model runtime | Ollama, separately managed | Serves chat models on `127.0.0.1:11434` via LiteLLM and `nomic-embed-text` through Ollama's `/api/embed` for RAG. The scripts check Ollama but do not start or stop it. |
| Retrieval store | `app/rag.py`, `rag/documents/`, `rag/chroma/` | Embedded persistent Chroma collection on local disk; no vector-database daemon. Source documents are local `.md`, `.txt` or `.pdf` files. |
| Agent and tools | `app/agent.py`, `app/tools/`, `app/mcp_tools.py`, `mcp_servers/demo.py` | Application-controlled, bounded model/tool loop. Calculator and demo weather execute in process. A read-only MCP server is spawned over stdio on demand for two declared tools; it has no listening port. |
| Local transcription | `app/stt.py`, `ui/live_audio.py` | English-only Whisper tiny.en: MLX `mlx-community/whisper-tiny.en-mlx` on Apple Silicon; faster-whisper `Systran/faster-whisper-tiny.en` on Windows/other platforms. Uses pre-cached Hugging Face files only. Validation and a killable, time-limited subprocess keep inference independent of the generation gateway. No audio is stored by the API. |
| Optional Open WebUI | `scripts/open-webui-*.sh`, `open-webui/data/` | Separate plain-chat browser client on `127.0.0.1:3000`, configured to use LiteLLM's `general` model; does **not** call FastAPI, so it does not expose application RAG/agent/STT. Installed separately from core requirements. |
| Optional n8n | `scripts/n8n-*.sh`, `n8n/workflows/summarize.json`, `n8n/data/` | Local webhook automation on `127.0.0.1:5678`. Its HTTP Request node calls LiteLLM `/v1/chat/completions` with `general`, not FastAPI or Ollama directly. Requires an existing compatible Node/n8n installation and an imported/published workflow. |

## Feature request flows

1. **Chat — `POST /chat`:** Streamlit sends a prompt to FastAPI. `app.llm.complete` sends system/user messages to LiteLLM using `general`; LiteLLM chooses the configured generation backend and FastAPI returns the answer and logical model name.
2. **Private document RAG — `POST /rag/ingest`, `POST /rag/query`:** Ingestion scans `rag/documents/`, extracts Markdown/text or PDF text, normalizes and splits it into overlapping chunks, obtains `nomic-embed-text` vectors directly from Ollama, and upserts chunk IDs, source metadata and embeddings into the persistent Chroma collection. A query embeds the question with Ollama, retrieves up to `top_k` chunks from Chroma, constructs a source-labelled context and asks `general` via LiteLLM to answer from that context and cite file names. Ingest before querying; it is explicitly triggered rather than automatically indexing every request. Indexed data persists across restarts.
3. **Tools/agent — `POST /agent`:** FastAPI asks `agent` through LiteLLM for a response or tool calls. For each proposed call, the application parses arguments, dispatches only declared tools, appends the result to the conversation and returns an answer plus an execution trace. The loop is capped at four model steps. The calculator evaluates a restricted arithmetic AST (not arbitrary Python); weather uses fixed offline city data, not a weather API. MCP exposes `list_demo_documents` (names only) and `get_demo_stack_status` (static description, **not** live health). `app/mcp_tools.py` starts `mcp_servers.demo` with the MCP SDK via stdio per call and enforces a 10-second timeout. Tool errors are returned in the trace rather than granting shell or arbitrary file access to the model.
4. **Speech-to-text — `POST /audio/transcribe`:** The UI can record then submit audio, upload a WAV, or experimentally capture microphone/explicitly shared browser-tab audio in ~4-second chunks. The live browser component converts audio to mono 16 kHz PCM WAV and posts chunks directly to the API; updates arrive per completed chunk, not word by word, and capture ends by stop/unmount/share end or after two minutes. FastAPI accepts raw `audio/wav` (not multipart), enforces a 1 MB request bound, and validates mono 16 kHz 16-bit PCM and a maximum 15-second clip. `app/stt.py` runs platform-selected Whisper in a spawned worker with a 90-second deadline, uses only locally cached model files and returns text, duration and model ID. Missing weights fail rather than downloading during a request. This is transcription, not translation or TTS; no TTS or image generation endpoint is implemented.
5. **Additional gateway consumers:** Open WebUI chat uses `general` directly through LiteLLM. Separately, the published n8n workflow accepts `POST /webhook/summarize-demo`, truncates input text to 1,200 characters, asks `general` for a one-sentence summary via LiteLLM and responds with JSON `summary`. Neither consumer uses the FastAPI feature endpoints.

## Configuration, persistence and operations

- `app/settings.py` reads `.env` via `python-dotenv`: LiteLLM URL/key, logical model names, Ollama URL, embedding model and Chroma location are configurable. The Streamlit API URL uses `DEMO_API_URL`. The gateway's concrete backends live in the selected LiteLLM YAML, not in the application. `scripts/start.sh` defaults to `config/litellm.local.yaml`; `LITELLM_CONFIG=config/litellm.hybrid.yaml` selects the Ollama-first Azure-capable configuration and loads required Azure settings from the shell or private `.env`. Hybrid mode can contact Azure and incur charges if routed there; do not treat it as an offline guarantee.
- `scripts/start.sh`, `scripts/status.sh` and `scripts/stop.sh` manage/check LiteLLM (:4000), FastAPI (:8000) and Streamlit (:8501) on `127.0.0.1`. The startup script refuses occupied ports, stores PIDs under `logs/` and checks service readiness; `stop.sh` stops tracked processes only. Ollama remains separately managed. The optional n8n and Open WebUI launchers have independent start/stop scripts, PID files and data directories.
- `rag/chroma/` holds the persistent index; `rag/documents/` holds source files including `company-policy.md`. `n8n/data/` contains n8n state/execution history, and `open-webui/data/` contains accounts, chats and its local secret. `logs/`, runtime data, `.env`, downloaded model weights and generated audio are not intended for version control. The exported n8n workflow obtains its gateway key from the n8n process environment, not the JSON export; keep localhost services and credentials private.
- The core dependency list is `requirements.txt`; optional Open WebUI and n8n are installed separately. Speech inference needs pre-cached platform-specific Whisper weights; RAG requires the Ollama embedding model and an initial ingest. See `README.md` for platform setup and startup. Runtime configuration and code are authoritative if documentation differs.

## Limits and intentional exclusions

The MCP status tool is static, weather is fixture data, and Chroma is an embedded local store rather than a network service. Open WebUI is plain chat; only Streamlit/FastAPI provide this repository's RAG, tools and audio features. Browser tab-audio sharing depends on browser permissions/support and does not imply system-wide capture. Azure fallback and Azure agent tool calling are not established by the checked-in configuration alone. TTS, ComfyUI/image generation and a standalone weather provider are not implemented in this repository.
