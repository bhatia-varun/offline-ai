import requests
from starlette.concurrency import run_in_threadpool
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent import run_agent
from app.llm import complete
from app.rag import answer_question, ingest_documents
from app.settings import GENERAL_MODEL, LITELLM_BASE_URL, OLLAMA_BASE_URL
from app.stt import AudioInputError, MAX_BYTES, transcribe_wav

app = FastAPI(title="Offline AI Stack Demo", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10_000)


class RagRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10_000)
    top_k: int = Field(default=4, ge=1, le=10)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "Offline AI Stack Demo", "docs": "/docs"}


@app.get("/health")
def health() -> dict[str, str]:
    status = {"api": "ok", "ollama": "down", "litellm": "down"}
    checks = {
        "ollama": f"{OLLAMA_BASE_URL}/api/version",
        "litellm": f"{LITELLM_BASE_URL.removesuffix('/v1')}/health/liveliness",
    }
    for name, url in checks.items():
        try:
            if requests.get(url, timeout=3).ok:
                status[name] = "ok"
        except requests.RequestException:
            pass
    return status


@app.post("/chat")
def chat(request: PromptRequest) -> dict[str, str]:
    try:
        answer = complete(
            GENERAL_MODEL,
            [{"role": "system", "content": "You are a concise, helpful assistant."}, {"role": "user", "content": request.prompt}],
            temperature=0.2,
        )
        return {"answer": answer, "logical_model": GENERAL_MODEL}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/rag/ingest")
def rag_ingest() -> dict[str, int]:
    try:
        return ingest_documents()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/rag/query")
def rag_query(request: RagRequest) -> dict[str, object]:
    try:
        return answer_question(request.question, request.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/audio/transcribe")
async def audio_transcribe(request: Request) -> dict[str, str | float]:
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "audio/wav":
        raise HTTPException(status_code=415, detail="Send a 16 kHz mono PCM WAV as audio/wav")
    try:
        declared_size = int(request.headers.get("content-length", "0") or "0")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid content length") from exc
    if declared_size > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Audio exceeds 1 MB")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Audio exceeds 1 MB")
    try:
        return await run_in_threadpool(transcribe_wav, bytes(data))
    except AudioInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Offline speech transcription unavailable") from exc


@app.post("/agent")
def agent(request: PromptRequest) -> dict[str, object]:
    try:
        return run_agent(request.prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
