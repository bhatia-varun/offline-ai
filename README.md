# Local-First AI Application

Configure and run a private, local AI stack, then explore how its application
features fit together. The core runs on your machine: local models through
Ollama, a model gateway through LiteLLM, application APIs through FastAPI, and
a working interface through Streamlit. Docker is not required.

## Repository capabilities

Chat, private RAG, agent workflows, tool/function calling, MCP, audio-to-text,
an Open WebUI chat interface, and optional image generation are all part of
this repository's demo story.

| Capability | What it demonstrates | Where it lives / how it is used |
| --- | --- | --- |
| Chat | Ask a local model questions from the Streamlit app. | `ui/streamlit_app.py` → `app/main.py` → `app/llm.py` → LiteLLM logical model `general` → Ollama. |
| Private RAG | Ingest local documents, retrieve relevant passages, and answer with source citations. | `app/rag.py`, `rag/documents/`, and persistent Chroma. Embeddings call Ollama; answer generation uses LiteLLM. |
| Agents and tool/function calling | Let the model request a tool, while application code validates and executes only declared tools. | Bounded loop in `app/agent.py`; safe calculator and deterministic demo weather in `app/tools/`. |
| MCP integration | Expose read-only demo tools through the Model Context Protocol. | `app/mcp_tools.py` starts `mcp_servers/demo.py` over stdio on demand; MCP calls appear in the agent trace. |
| Audio-to-text | Transcribe English audio locally, including recorded/uploaded audio and experimental live chunks. | `app/stt.py` and `ui/live_audio.py`; MLX Whisper on Apple Silicon, faster-whisper CPU/int8 on Windows. This is transcription, not TTS. |
| Open WebUI | Use an additional browser chat interface with the same model gateway. | This repo provides the launchers/configuration; the optional Open WebUI package runs locally at `127.0.0.1:3000` and talks directly to LiteLLM. It does not provide this app's RAG, agent, MCP, or audio features. |
| Image generation | Run a local ComfyUI + Stable Diffusion workflow as a separate visual demo. | This repo provides `scripts/comfyui-*.sh` and `image/workflow-api.json`; the optional ComfyUI runtime and model weights are local dependencies, not bridged into FastAPI/Streamlit. |
| Workflow automation | Send a local webhook to LiteLLM and return a generated summary. | Optional n8n workflow in `n8n/workflows/`; n8n calls LiteLLM directly. |

## How the stack fits together

```text
Browser -> Streamlit -> FastAPI -> LiteLLM -> Ollama
                           |          |          `-> local text models
                           |          `-> logical models: general / agent
                           |-> Ollama embeddings -> Chroma (local RAG)
                           |-> calculator / weather / on-demand stdio MCP
                           `-> local Whisper speech-to-text

Open WebUI ---------------------> LiteLLM
n8n webhook --------------------> LiteLLM
ComfyUI + Stable Diffusion ------> separate optional image workflow
```

FastAPI owns retrieval, agent orchestration, and tool execution. LiteLLM
provides a stable text-generation API; Ollama runs local models. Open WebUI,
n8n, and ComfyUI are optional independent clients/workflows. See
[architecture.md](architecture.md) for component boundaries and request flows.

## Platform setup

The core application runs natively on **Windows x64** and **Apple Silicon
macOS**. Both use Python 3.11, Ollama, LiteLLM, FastAPI, Streamlit, and Chroma.
Speech transcription uses a platform-specific local Whisper backend. Expand
the setup for your machine:

Open WebUI and ComfyUI are integrated into this project through its launchers,
configuration, and workflow. Their installed upstream application code,
virtual environments, model weights, and user/runtime data stay local and are
excluded from this repository; they are not nested Git repositories or
submodules.

<details>
<summary>Windows setup and operation</summary>

### Windows setup and operation

The core stack runs natively on Windows: Streamlit, FastAPI, LiteLLM, Ollama,
Chroma, calculator/weather and the on-demand MCP server. Windows uses
**faster-whisper tiny.en on CPU (int8)** instead of Apple-only MLX Whisper.
The Mac setup below remains available; do not use its `.sh` scripts or copy a
Mac virtual environment on Windows. No WSL, CUDA or image-generation folder is
required for the core features.

Use **Python 3.11 x64** and run these commands in PowerShell from this folder.
For a fresh setup (do not overwrite an existing environment you need):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
ollama pull llama3.2:3b
ollama pull nomic-embed-text
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-tiny.en', allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.txt'], token=False)"
```

The speech model download requires internet once (about 75 MB of weights).
Requests subsequently load only those cached files; missing weights produce
503, not a download. Use a short English clip; the existing mono 16 kHz,
16-bit PCM WAV, 15-second/1 MB limits and 90-second inference deadline still
apply. Apple Silicon continues to use MLX. Browser microphone and tab-audio
permissions must still be tested with a human speaking on the target laptop.

The commands below use the environment's Python executable directly, so
activating the virtual environment is optional.

```powershell
.\.venv\Scripts\python.exe scripts/windows.py start
.\.venv\Scripts\python.exe scripts/windows.py status
```

Open Streamlit at <http://127.0.0.1:8501> or API docs at
<http://127.0.0.1:8000/docs>. This launcher always selects the **local-only**
LiteLLM YAML, which uses your `llama3.2:3b` for `general` and `agent`.
Ollama must already be running. Click **Ingest local documents** before RAG.
The launcher redirects the copied default Chroma path to
`rag/chroma-windows/`, preserving `rag/chroma/`; a custom `CHROMA_PATH` is
honored. Re-ingest to build the Windows index rather than relying on copied
binary index files. Existing Open WebUI and n8n data are not deleted.

The presentation hub uses **8766 on Windows**, leaving 8765 available for
other applications:

```powershell
.\.venv\Scripts\python.exe scripts/windows.py start --service hub
```

Open <http://127.0.0.1:8766>. **Start all & present** uses the native Windows
launcher, reuses healthy tracked core services, and reports missing optional
clients without aborting. ComfyUI/image generation is not configured on this
laptop because its installation and checkpoint were not copied.

Stop only services started by this launcher:

```powershell
.\.venv\Scripts\python.exe scripts/windows.py stop --service hub
.\.venv\Scripts\python.exe scripts/windows.py stop
```

Logs are under `logs/`. Windows ownership records use `*.process.json`,
checking PID, creation time and command before stopping a process tree.
Occupied ports belonging to other processes are refused, not killed.
Startup failures roll back only services started by that invocation.
Ollama is never stopped. `--service api`, `litellm`, or `streamlit` can also
start, stop or check one core service. The Windows launcher does not enable
hybrid/Azure mode; the existing Mac hybrid instructions do not verify it here.

### Optional Windows clients

Open WebUI and n8n are separate clients, not needed for the core application.
They are optional installs outside the core requirements. Open WebUI has
different dependency requirements; install it in its own Python 3.11
environment, not the core `.venv`. Keep both services bound to localhost and
do not commit their local account, chat, workflow, or execution data.

For a fresh Open WebUI installation, while online:

```powershell
py -3.11 -m venv .venv-webui
.\.venv-webui\Scripts\python.exe -m pip install open-webui==0.11.4
.\.venv\Scripts\python.exe scripts/windows.py start --service webui
# http://127.0.0.1:3000; stop with the same command using "stop".
```

On first launch, create a local account and choose **general** in a new chat.
Open WebUI calls LiteLLM directly; it does not expose this application's RAG,
agent, MCP, or audio endpoints. Preserve its data directory if you need to
keep local accounts or chat history.

n8n needs a compatible Node.js installation and a published workflow. Start it
with:

```powershell
.\.venv\Scripts\python.exe scripts/windows.py start --service n8n
```

For a fresh n8n installation only, install the documented version and
import/publish **while stopped**. Do not overwrite saved workflow changes:

```powershell
npm.cmd install -g n8n@2.10.4
$env:N8N_USER_FOLDER = Join-Path $PWD 'n8n/data'
n8n.cmd import:workflow --input=n8n/workflows/summarize.json
n8n.cmd publish:workflow --id=offlineDemoSummarizeV1
.\.venv\Scripts\python.exe scripts/windows.py start --service n8n
# http://127.0.0.1:5678; stop with the same command using "stop".
```

To trigger the published workflow from **Windows PowerShell**, use
`Invoke-RestMethod` and `ConvertTo-Json`, not the Bash `curl` example below:

```powershell
$text = 'The support team reviewed customer search reports on Monday. Users said the results were relevant, but pages loaded slowly during busy hours. Engineers traced the delay to repeated database queries. They added a cache for frequent searches and measured load times before and after the change. In the next test, search pages loaded faster during peak traffic, while the team continued monitoring relevance and errors.'
$body = @{ text = $text } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri 'http://127.0.0.1:5678/webhook/summarize-demo' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 180 | ConvertTo-Json
```

In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest`; it does
not accept curl's header syntax. `curl.exe` selects the real executable, but
inline JSON quoting also varies by Windows shell. The PowerShell-native
example avoids both issues. Visual terminal wrapping does not truncate the
request. This sample is 416 characters, below the workflow's 1,200-character
input cap; `max_tokens` limits the generated summary, not the input passage.
For an editor run waiting on **Listen for test event**, change the URL to
`http://127.0.0.1:5678/webhook-test/summarize-demo` and send it while listening.

The native n8n launcher expects a standard global npm installation and uses
the existing data directory. It enables environment-variable expressions for
the workflow's gateway key; do not import untrusted workflows. Neither
optional client exposes this application's FastAPI RAG/MCP/audio features.
The launcher prints a progress message every 15 seconds during startup.
Windows n8n startup allows up to six minutes; other services allow three.
The hub allows seven minutes for the n8n launcher to finish. n8n readiness
checks the editor settings route because its health endpoint can respond
before the application routes are initialized. Startup can take several
minutes; if it fails, inspect the named service log before retrying or
changing its data.

### Windows verification

Windows verification covered core health/startup, chat, document ingest/query
with a `company-policy.md` citation, calculator (391), offline Delhi weather,
direct and agent-selected MCP calls, and FastAPI speech transcription returning
"The blue robot reads a short sentence." from an in-memory Windows SAPI
sample. Native stop/restart preserved Ollama and the unrelated listener on
8765. Streamlit chat/speech views rendered in the browser (speech selected
with keyboard navigation); the hub accepted its own origin, rejected a
foreign origin and reported missing optional stations without aborting.
No TTS feature or audio file was added. Focused regression tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Open WebUI and n8n also passed health/browser sign-in checks; the n8n production
workflow and configured Open WebUI gateway connection passed. Authenticated
browser chat/editor interaction, real microphone/tab capture, Azure fallback
and image generation are not established by these checks.

</details>

<details>
<summary>macOS setup (Apple Silicon)</summary>

### macOS setup (Apple Silicon)

Install Python 3.11 and Ollama, then run these commands from the repository
root. This uses the checked-in local model configuration and caches the
Apple-Silicon Whisper model before offline use:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
ollama pull llama3.2:3b
ollama pull nomic-embed-text
python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/whisper-tiny.en-mlx', allow_patterns=['config.json','weights.npz'], token=False)"
bash scripts/start.sh
```

The Whisper cache step needs internet once. `scripts/start.sh` runs LiteLLM,
FastAPI, and Streamlit; open <http://127.0.0.1:8501>. Use
`bash scripts/status.sh` and `bash scripts/stop.sh` to inspect and stop them.
Ollama is managed separately and must be running first.

</details>

## Unified demo command center

Run the local presentation hub from the project root:

```bash README.md
bash scripts/demo-hub.sh
```

Open <http://127.0.0.1:8765>. Click **Start all & present** to start the existing core, Open WebUI, n8n and ComfyUI launch scripts in that order. The tour begins as soon as the first UI is healthy; remaining UIs join as they become ready. Or click the microphone and say **“Jarvis start demo”** (browser speech recognition and microphone permission required; some browsers may use a remote speech service, so use the button for a strictly offline presentation). The hub does not upload or save audio itself. Click **Pause tour** to freeze the slideshow timer, **Resume tour**, **Next**, **Previous**, or a station to jump directly. Set the interval from **10–20 seconds**. Services continue running while the tour is paused. If a site refuses to display in the embedded stage, use **Open in new tab**.

Prepare Ollama, the optional Open WebUI installation and ComfyUI checkpoint before presenting. Import/publish the n8n workflow separately as described below. The launcher reports individual startup failures and skips unavailable stations; it does not install dependencies, run prompts, or generate images automatically. All services and the hub bind to localhost. To finish, stop the hub process using its PID from another terminal, then stop the services in dependency order:

```bash README.md
./scripts/comfyui-stop.sh
bash scripts/open-webui-stop.sh
./scripts/n8n-stop.sh
./scripts/stop.sh
```

Only use stop scripts for services started by this project. The hub is also safe to use when services are already running, but health checks do not prove that a listener belongs to this project.

## Start the fully local stack

```bash README.md
cd /Users/varunbhatia/offline-ai-demo
./scripts/start.sh
```

Open:

- UI: <http://127.0.0.1:8501>
- FastAPI docs: <http://127.0.0.1:8000/docs>
- LiteLLM: <http://127.0.0.1:4000>

Check status or logs:

```bash README.md
./scripts/status.sh
tail -f logs/litellm.log logs/api.log logs/streamlit.log
```

Stop all demo services with:

```bash README.md
./scripts/stop.sh
```

## API smoke tests

```bash README.md
curl -s http://127.0.0.1:8000/health | python -m json.tool

curl -s http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explain Kubernetes in one sentence."}' | python -m json.tool

curl -s -X POST http://127.0.0.1:8000/rag/ingest | python -m json.tool

curl -s http://127.0.0.1:8000/rag/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the policy for working from another location?"}' | python -m json.tool

curl -s http://127.0.0.1:8000/agent \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is the weather in Delhi and what is 17 * 23?"}' | python -m json.tool
```

## Switch to hybrid mode

The hybrid config uses Ollama first (`order: 1`) for both `general` and `agent`, with Azure second (`order: 2`). Set `AZURE_API_BASE` (the resource root, without `/openai`), `AZURE_API_KEY`, and `AZURE_API_VERSION=v1` privately in `.env` or your shell. The start script loads only these variables for hybrid mode; never print or commit their values. Azure requests may incur charges **if Ollama fails**.

```bash README.md
cd /Users/varunbhatia/offline-ai-demo
./scripts/stop.sh
LITELLM_CONFIG=config/litellm.hybrid.yaml ./scripts/start.sh
./scripts/status.sh
```

The application still requests only `general` and `agent`. Return to fully offline mode with:

```bash README.md
./scripts/stop.sh
./scripts/start.sh
./scripts/status.sh
```

If startup says a port is occupied, investigate that listener before switching modes; a health check alone does not prove which configuration is running. Verified: hybrid startup, logical model listing, ordinary gateway requests selecting Ollama, FastAPI chat, RAG, agent calculator tool, and Streamlit health. **Azure fallback and Azure agent tool calling have not been tested.** Do not treat hybrid mode as guaranteed offline; use local mode when cloud access is prohibited.

## Optional second client: Open WebUI

Open WebUI is an **additional chat client**, not a replacement for Streamlit. It calls LiteLLM's OpenAI-compatible API at `http://127.0.0.1:4000/v1` and uses the logical model `general`. It does **not** call FastAPI or expose this application's RAG, MCP, or agent traces; keep Streamlit for those portions of the demo.

For the Mac demo, install the native Open WebUI package into the existing Python 3.11 environment **while online**, ahead of the offline presentation (pin and test your chosen version; it is intentionally not part of core `requirements.txt`):

```bash README.md
.venv/bin/python -m pip install open-webui
```

Start the **local-only** core stack with `./scripts/start.sh`, then run the optional client:

```bash README.md
bash scripts/open-webui-start.sh
```

Open <http://127.0.0.1:3000>, create the first local admin account, choose **general**, and ask a simple chat question in a **new chat**. This exercises Open WebUI → LiteLLM → Ollama. Confirm the model list and try a response before presenting. Open WebUI binds only to `127.0.0.1`, disables its direct Ollama connection, points its OpenAI connection at LiteLLM, and disables its unrelated built-in calendar integration. On an existing installation, Open WebUI may have persisted `calendar.enable=true` in `open-webui/data/`; if `search_calendar_events` still appears, turn off Calendar under Open WebUI admin settings and disable its built-in tools for `general` in the model settings. Start a new chat after changing tool settings. The application's own FastAPI tools and MCP server are separate and are not used by this client. The key defaults to this demo's `local-demo-key`; if you changed LiteLLM's master key, set `LITELLM_API_KEY` privately before starting. Do not show credentials or user data on screen. `OFFLINE_MODE=true` limits optional external requests; preinstall all packages/models before disconnecting. Do not switch to hybrid mode for a guaranteed offline demo.

After updating the launcher, restart the optional UI to apply the new environment setting:

```bash README.md
bash scripts/open-webui-stop.sh
bash scripts/open-webui-start.sh
```

Stop just the optional UI before stopping the core stack:

```bash README.md
bash scripts/open-webui-stop.sh
```

Open WebUI account and chat data, including its locally generated secret, live in ignored `open-webui/data/`. Do not delete that directory unless you intend to reset the Open WebUI account and history. Open WebUI may use substantial RAM on a 16 GB Mac; test performance before the live demo.

## MCP tools (Phase B)

The `mcp_servers.demo` server uses **stdio**, started on demand by `app/mcp_tools.py` with a 10-second timeout; it needs no port or separate persistent process. The unified demo hub starts FastAPI (which invokes MCP on agent tool calls), not an independent always-running MCP service. Open WebUI and n8n do not call this MCP server. The agent still owns the tool loop and preserves calculator/weather tools. The server advertises only `list_demo_documents` (document names, not contents) and `get_demo_stack_status` (static configuration, not live health). MCP calls and results appear in the existing Streamlit agent trace. Python dependency: `mcp>=1.26,<2`, matching the existing `FastMCP` API (SDK v2 renamed that API).

Try: ask the **Tools / Agent** tab in Streamlit, “Use the list_demo_documents MCP tool to list available document names; do not guess.” To check MCP independently of the model and FastAPI, from the project root run:

```bash README.md
.venv/bin/python - <<'PY'
from app.mcp_tools import call_mcp_tool
print(call_mcp_tool('list_demo_documents', {}))
PY
```

This should list `company-policy.md` and exit automatically. Do **not** start `python -m mcp_servers.demo` manually for the regular demo; its stdio transport waits for protocol messages from a client and prints no interactive response. If the direct check works but the Agent tab fails, inspect its tool execution trace: no `list_demo_documents` entry means the model did not select the tool, while an error entry indicates a failed MCP call. If FastAPI was already running before an MCP code change, restart the project's core stack using `./scripts/stop.sh` followed by `./scripts/start.sh` before retrying. The MCP server only starts when a tool is called and exits after the call.

## n8n workflow (Phase C)

Native n8n 2.10.4 runs with the **existing** Node 24 at `~/.nvm/versions/node/v24.16.0/bin` (the default Node 18 is unsupported). `scripts/n8n-start.sh` binds port 5678 to localhost and uses ignored `n8n/data/`; it passes only the LiteLLM gateway key via `LITELLM_API_KEY` (defaults to this demo's `local-demo-key`). The exported `n8n/workflows/summarize.json` contains no key and calls only `http://127.0.0.1:4000/v1/chat/completions` with model `general`. This local demo uses n8n environment-variable access in expressions; keep port 5678 private and do not import untrusted workflows.

Import and publish the workflow **while n8n is stopped**, then start it (allow a few seconds for the webhook to register after health is ready):

```bash README.md
cd /Users/varunbhatia/offline-ai-demo
export PATH="$HOME/.nvm/versions/node/v24.16.0/bin:$PATH"
export N8N_USER_FOLDER="$PWD/n8n/data"
n8n import:workflow --input=n8n/workflows/summarize.json
n8n publish:workflow --id=offlineDemoSummarizeV1
./scripts/n8n-start.sh
curl -sS --max-time 180 http://127.0.0.1:5678/webhook/summarize-demo \
  -H 'Content-Type: application/json' \
  -d '{"text":"The support team reviewed customer search reports on Monday. Users said the results were relevant, but pages loaded slowly during busy hours. Engineers traced the delay to repeated database queries. They added a cache for frequent searches and measured load times before and after the change. In the next test, search pages loaded faster during peak traffic, while the team continued monitoring relevance and errors."}'
```

### Demonstrate it in the n8n editor

This workflow starts with a **POST Webhook** node. **Execute workflow** does not generate sample input: it puts the webhook into a temporary listening state. The terminal request above goes to the **production** URL (`/webhook/summarize-demo`), whereas the editor's listening run requires the **test** URL (`/webhook-test/summarize-demo`). Opening either URL in a browser address bar sends a GET, not the required POST.

For a UI-only walkthrough, open **Summarize via LiteLLM general** in the n8n editor, select **Local Webhook**, and click **Listen for test event** (or **Execute workflow** to start waiting for the trigger). In a separate tab, open a browser-based HTTP client such as your browser's developer-tools console **on the n8n page itself** and run:

```javascript README.md
fetch('http://127.0.0.1:5678/webhook-test/summarize-demo', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({text: 'The support team reviewed customer search reports on Monday. Users said the results were relevant, but pages loaded slowly during busy hours. Engineers traced the delay to repeated database queries. They added a cache for frequent searches and measured load times before and after the change. In the next test, search pages loaded faster during peak traffic, while the team continued monitoring relevance and errors.'})
}).then(async response => console.log(response.status, await response.text()))
```

The sample has several sentences so a short summary is visibly different from its input. The updated workflow requests one sentence of at most 20 words, but this is an instruction to the model, not a guaranteed word-count limit. The request must arrive while the editor is listening; test webhooks are temporary and typically accept one event per listening run. The n8n canvas should highlight **Local Webhook → LiteLLM general → Reply with summary**; click the last node to inspect its JSON output. The console also prints the returned summary. If the browser refuses the request, check that the console belongs to the n8n origin (`http://127.0.0.1:5678`), and start listening again before retrying. Do not paste untrusted code into developer tools.

For a **published** workflow demo, use the existing production `curl` request instead, then open the workflow's **Executions** tab in n8n and select the latest execution to show the nodes and their inputs/outputs. A production webhook call does not populate an editor run waiting on the test URL. If an execution does not appear, check the workflow's saved-execution settings and whether the run finished; do not re-import the workflow during the presentation.

To stop n8n without stopping the text stack:

```bash README.md
./scripts/n8n-stop.sh
```

Changes to `n8n/workflows/summarize.json` do not update an already imported workflow. To use the revised concise prompt, stop n8n and follow the import/publish/start steps above before presenting; first confirm there are no unsaved changes you need to keep in the n8n UI. Re-importing deactivates the workflow: stop n8n, import, publish, then start it again. The workflow was tested end-to-end with **non-empty summaries** in local mode and in Ollama-first hybrid mode without changing the workflow. It does not establish that Azure fallback works. n8n data, encryption keys, and execution history stay in ignored `n8n/data/`; do not publish exports from that directory.

## Local speech to text (D1)

**Experimental live transcription:** The Speech to text tab now includes a browser-side live control (`ui/live_audio.py`). Choose **Microphone / selected input device**, click **Start live transcription**, grant browser permission, speak English, and click **Stop**. The browser sends bounded ~4-second mono 16 kHz PCM WAV chunks to the existing localhost FastAPI `/audio/transcribe` endpoint; the transcript grows after each model response, **not word-by-word**. Latency depends on local MLX inference; chunks may be skipped when inference cannot keep up. Capture stops after two minutes, when sharing ends, on component unmount, or on Stop. Browser capture and display require a real-browser test; Python AppTest, JS syntax, direct short-chunk API inference and core regressions passed, but do not establish that browser capture works on your machine. A custom Streamlit v2 component is used; no external audio service or new model is installed.

**Audio from another browser tab:** A microphone cannot directly intercept macOS playback. Select **Share browser tab with audio** in the live source menu; when prompted, select the **specific tab playing English audio** (even in another window, if the browser offers it) and enable **Share tab audio**. Browser/macOS support varies; sharing a tab from a different browser application may not be supported. If no audio track is shared, the UI reports an error. System-wide output from other apps requires a separately configured loopback input device (e.g. BlackHole), which is **not installed or verified**; after a user-managed installation/routing, the microphone source could select that input as the OS default. Do not assume the mic icon captures other apps unless speakers are audibly picked up by the physical microphone. Obtain permission from participants before transcribing playback. This is English **speech-to-text**, not translation to another language.

**Record, then transcribe (existing verified option):** The **Speech to text** Streamlit tab also offers **Record English speech** (microphone) as the primary input. Grant the browser microphone permission at <http://127.0.0.1:8501>, record a short phrase, stop, then click **Transcribe locally**. This is record-then-transcribe, **not** continuously updating text or translation. If permission is denied, allow the microphone for the site in browser/macOS settings and reload. A prepared WAV upload remains available under the expander; a recording takes precedence if both are selected. The Streamlit widget requests 16 kHz audio and returns a WAV; the backend validates its actual format. A real-browser microphone test still requires a human to speak and confirm the result.

The tab and `POST /audio/transcribe` accept only **mono 16 kHz 16-bit PCM WAV**, at most **15 seconds and 1 MB**. Send raw WAV bytes with `Content-Type: audio/wav`, not multipart; the API returns `text`, `duration_seconds`, and `model`. Inference uses a killable local worker with a 90-second deadline; invalid input is rejected before inference. No input files are retained. It runs independently of LiteLLM and Ollama. Longer microphone recordings are rejected (recordings over 1 MB are also rejected); use a short non-sensitive phrase.

Preparation **while online**, after checking `df -h ~` and available memory: `requirements.txt` includes `mlx-whisper==0.4.3` (~0.9 MB wheel), MLX/Metal (~68 MB Metal wheel), numba/llvmlite (~41 MB llvmlite wheel), and existing dependencies. MLX-community `whisper-tiny.en-mlx` weights are ~74.4 MB (`weights.npz`, not the incompatible `model.safetensors` from the other tiny.en variants). Pre-cache exactly the two required files; the API refuses network downloads:

```bash README.md
cd /Users/varunbhatia/offline-ai-demo
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/whisper-tiny.en-mlx', allow_patterns=['config.json', 'weights.npz'], token=False)
print('Tiny English MLX model cached')
PY
```

For a reproducible **D1-only** demo clip, the built-in macOS `say` command generates a throwaway sample; this is **not** a TTS service/integration. Generate in an automatically cleaned temporary folder and send it to FastAPI after starting the stack:

```bash README.md
.venv/bin/python - <<'PY'
import subprocess, tempfile, requests
with tempfile.TemporaryDirectory(prefix='stt-demo-') as tmp:
    aiff, wav = tmp + '/sample.aiff', tmp + '/sample.wav'
    subprocess.run(['/usr/bin/say', '-o', aiff, 'The blue robot reads a short sentence.'], check=True, timeout=15)
    subprocess.run(['/usr/bin/afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', aiff, wav], check=True, timeout=15)
    with open(wav, 'rb') as clip:
        response = requests.post('http://127.0.0.1:8000/audio/transcribe', data=clip,
                                 headers={'Content-Type': 'audio/wav'}, timeout=105)
    print(response.status_code, response.json())
    response.raise_for_status()
PY
```

Direct library transcription and FastAPI end-to-end both returned **“The blue robot reads a short sentence.”**; API invalid type, invalid WAV and oversize checks passed. Streamlit's widget render was verified with `AppTest`, but microphone capture through a real browser has not yet been tested. Regression passed for local-only health, chat, RAG, calculator agent and Streamlit health. No generated media, model weights or caches should be committed (`audio/tmp/`, `audio/models/`, `audio/samples/` are ignored; downloaded weights live in the user's Hugging Face cache). First inference loads MLX and may be slower; tiny.en supports English only and can mishear speech. `mlx-whisper` is MIT licensed, MLX is MIT licensed; the model is an MLX conversion of OpenAI Whisper tiny.en (OpenAI Whisper MIT). Confirm model-card terms before redistribution. Without its pre-cached files, the endpoint returns a 503 rather than downloading.

**D2 validated details only:** `/usr/bin/say` exists and generated a temporary AIFF sample on this Mac, without extra downloads. A future TTS endpoint should bound text, write to a fixed ignored directory, use argument-list subprocess execution and timeouts, and clean output. Piper compatibility, playable output, endpoint, and UI have **not** been tested or implemented.

## Local image generation (Phase E: verified direct ComfyUI workflow)

The user approved the disk use. [ComfyUI](https://docs.comfy.org/installation/manual_install) 0.38.0 (checkout `65787d6`) was installed under ignored `image/comfyui/` with **separate native arm64 Python 3.11** `image/venv/` and PyTorch 2.14.1 (MPS available). The **single** checkpoint is [Stable Diffusion v1.5 inference-only safetensors](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/tree/main), `image/models/v1-5-pruned-emaonly.safetensors` (4,265,146,304 bytes, SHA-256 `6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa`); ComfyUI's checkpoint folder contains a symlink to that file, **not another copy**. No checkpoint or generated image is committed. Checkpoint license: [CreativeML OpenRAIL-M and model-card restrictions](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/raw/main/README.md); ComfyUI repository reports GPL-3.0. Review licenses before redistribution. This optional service does not call LiteLLM/Ollama and does not change the core `.venv`, FastAPI, Streamlit, or `scripts/start.sh`.

Start independently from the project root, then open <http://127.0.0.1:8188> (localhost only). The launcher checks for an occupied port, starts in offline mode without custom nodes, and waits for its health endpoint:

```bash README.md
./scripts/comfyui-start.sh
```

For the **verified, repeatable fixed-seed test**, submit the sanitized ComfyUI API-format workflow at `image/workflow-api.json` directly to ComfyUI and poll its history. It uses seed 42, 512×512, 12 Euler steps, and writes an output PNG under ignored `image/output/`:

```bash README.md
image/venv/bin/python - <<'PY'
import json, time, urllib.request
from pathlib import Path
base = 'http://127.0.0.1:8188'
workflow = json.loads(Path('image/workflow-api.json').read_text())
request = urllib.request.Request(base + '/prompt', method='POST',
    data=json.dumps({'prompt': workflow}).encode(), headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=15) as response:
    submitted = json.load(response)
assert not submitted.get('node_errors'), submitted.get('node_errors')
for _ in range(60):
    with urllib.request.urlopen(base + '/history/' + submitted['prompt_id'], timeout=5) as response:
        result = json.load(response).get(submitted['prompt_id'])
    if result and result.get('status', {}).get('completed'):
        assert result['status']['status_str'] == 'success', result['status']
        print('Generated:', result['outputs']['7']['images'])
        break
    time.sleep(5)
else:
    raise TimeoutError('ComfyUI generation exceeded five minutes; inspect image/logs/comfyui.log')
PY
```

Direct API test succeeded: ComfyUI reported **23.32 seconds** of execution (cold model load included) and wrote `image/output/offline-demo-robot_00001_.png`; Pillow validated it as 512×512 RGB PNG. Exact timings and pixels can vary across hardware/software versions; fixed seed and unchanged workflow are the reproducibility settings. Startup was verified by a successful health request, but precise startup duration was **not measured**. ComfyUI UI import/display was not separately browser-tested: `workflow-api.json` is **API format**, not a drag-and-drop UI graph. New runs produce additional numbered PNGs. SD 1.5 can struggle with text, anatomy and complex composition; 12 steps prioritize demo speed, not quality. On a 16 GiB unified-memory Mac, avoid simultaneous heavy Qwen and image inference.

Stop the independent image service without affecting the text stack:

```bash README.md
./scripts/comfyui-stop.sh
```

The stop script was verified after first generation and again after restart. Inspect `image/logs/comfyui.log` if startup or inference fails. Files in ignored `image/output/` are **not removed automatically**: review and remove only unwanted generated PNGs yourself; keep the checkpoint unless you explicitly choose to delete it. Ignored runtime paths also include `image/venv/`, `image/comfyui/`, `image/models/`, `image/input/`, `image/temp/`, `image/user/`, and `image/logs/`. Before setup, 24 GiB was available; afterward `df -h ~` fluctuated between 14–16 GiB (APFS fluctuations). Observed storage: ~75 MiB ComfyUI clone, ~1.8 GiB separate venv, ~4.0 GiB checkpoint. `image/venv/bin/python -m pip check` passed. After generating and stopping ComfyUI, FastAPI health/chat/RAG/calculator tool trace and Streamlit health passed. **No FastAPI/Streamlit image trigger exists yet**; use ComfyUI directly for this optional supporting demo.

## Model configuration

The checked-in local LiteLLM config uses `llama3.2:3b` for both logical models
to keep the default demo lightweight. The optional hybrid config has a
different model and may route requests to Azure if Ollama fails; it is not a
guaranteed-offline mode. Select and download the models required by the config
you plan to run. Do not expose Azure credentials or `.env` during a demo.

The weather tool intentionally uses fixed demo data so the complete local scenario works without internet access.

## Run and present the demos

### Before the audience arrives

Use **local-only mode** for a guaranteed offline presentation. Hybrid mode is Ollama-first but can contact Azure if local generation fails; Azure fallback has not been tested. From the project root, check that Ollama is running and start or verify the core stack:

```bash README.md
cd /Users/varunbhatia/offline-ai-demo
./scripts/status.sh
./scripts/start.sh
./scripts/status.sh
```

If `start.sh` reports an occupied port, check which process owns it rather than assuming the requested config started. Open <http://127.0.0.1:8501> and keep <http://127.0.0.1:8000/docs> available as an API reference. Allow extra time for Qwen's first response on an M1 Mac.

For the n8n segment, first check <http://127.0.0.1:5678>. If the workflow has not yet been imported and published, follow **n8n workflow (Phase C)** above while n8n is stopped. Otherwise start the already-imported instance:

```bash README.md
./scripts/n8n-start.sh
```

Do not re-import during the presentation: importing deactivates the workflow until it is published again. Wait a few seconds after n8n reports healthy for its webhook to register. If n8n is already running, leave it running rather than starting another instance.

### Suggested live walkthrough

1. **Architecture (1 minute):** Point to Streamlit → FastAPI → LiteLLM → Ollama. Explain that applications request logical models (`general`/`agent`); local embeddings and Chroma belong to the application, while generation uses the gateway. Show `config/litellm.local.yaml` only if useful—never show `.env` or logs containing credentials.
2. **Chat:** In Streamlit’s **Chat** tab, ask “Explain this architecture in two sentences.” Explain that FastAPI uses `general` through LiteLLM; it does not address Qwen directly.
3. **Private RAG:** In **Private RAG**, click **Ingest local documents** if needed, then ask “What is the policy for working from another location?” Point out the cited `company-policy.md` source and the separation between local retrieval and gateway-based generation.
4. **Ordinary tools:** In **Tools / Agent**, ask “What is the weather in Delhi and what is 17 * 23?” Expand the tool execution trace. The model proposes calls; FastAPI executes the deterministic weather tool and safe calculator.
5. **MCP comparison:** In the same tab, ask “Use the list_demo_documents MCP tool to list available document names; do not guess.” Show `list_demo_documents` and its result in the trace. The application still owns the agent loop; an on-demand stdio MCP server exposes this read-only operation.
6. **n8n consumer:** Show the imported **Summarize via LiteLLM general** workflow in <http://127.0.0.1:5678>, then trigger its production webhook from a terminal:

   ```bash README.md
   curl -sS --max-time 180 http://127.0.0.1:5678/webhook/summarize-demo \
     -H 'Content-Type: application/json' \
     -d '{"text":"The support team reviewed customer search reports on Monday. Users said the results were relevant, but pages loaded slowly during busy hours. Engineers traced the delay to repeated database queries. They added a cache for frequent searches and measured load times before and after the change. In the next test, search pages loaded faster during peak traffic, while the team continued monitoring relevance and errors."}'
   ```

   Show the non-empty `summary`. The HTTP Request node calls LiteLLM’s `/v1/chat/completions` with `model: general`, not Ollama. If the webhook initially returns 404, allow n8n a few seconds to finish registering it and retry.

**Optional routing illustration:** If cloud access is permitted, stop the core stack and start the Ollama-first hybrid config using the commands in **Switch to hybrid mode**. Repeat Chat or the same n8n webhook without modifying FastAPI, Streamlit, or the workflow. Describe this only as a **configuration switch with Ollama still first**; do not claim an Azure request or fallback was demonstrated. Return to local-only mode using the documented rollback commands.

### Reset and finish

For another run, leave ingested Chroma data in place or click **Ingest local documents** again; avoid exposing private documents or credentials on screen. The MCP server exits after each call. When finished, stop n8n separately, then the core services:

```bash README.md
./scripts/n8n-stop.sh
./scripts/stop.sh
```

Only run `n8n-stop.sh` if n8n was started with this project's script and has a tracked PID. These commands do not stop the separately managed Ollama runtime.
