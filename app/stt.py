"""Offline English speech-to-text for short 16 kHz mono PCM WAV clips."""

from pathlib import Path
import io
import multiprocessing as mp
import platform
import wave

import numpy as np
from huggingface_hub import snapshot_download

USE_MLX = platform.system() == "Darwin" and platform.machine() == "arm64"
MODEL_ID = "mlx-community/whisper-tiny.en-mlx" if USE_MLX else "Systran/faster-whisper-tiny.en"
MAX_BYTES = 1_000_000
MAX_SECONDS = 15
TIMEOUT_SECONDS = 90


class AudioInputError(ValueError):
    pass


def _decode_wav(data: bytes) -> tuple[np.ndarray, float]:
    if len(data) > MAX_BYTES:
        raise AudioInputError("Audio exceeds 1 MB")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels, width, rate, frames = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes())
            if channels != 1 or width != 2 or rate != 16_000 or not 0 < frames <= MAX_SECONDS * rate:
                raise AudioInputError("Use mono 16 kHz 16-bit PCM WAV, at most 15 seconds")
            pcm = wav.readframes(frames)
            if len(pcm) != frames * width or wav.readframes(1):
                raise AudioInputError("WAV length is invalid")
    except (wave.Error, EOFError, OSError) as exc:
        raise AudioInputError("Invalid PCM WAV file") from exc
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768, frames / rate


def _transcribe(samples: np.ndarray) -> str:
    filenames = ["config.json", "weights.npz"] if USE_MLX else ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
    model = snapshot_download(MODEL_ID, allow_patterns=filenames, local_files_only=True, token=False)
    if not all((Path(model) / name).is_file() for name in filenames):
        raise FileNotFoundError("Whisper tiny.en weights are missing")
    if USE_MLX:
        from mlx_whisper import transcribe

        return transcribe(samples, path_or_hf_repo=model, language="en", verbose=False)["text"].strip()
    from faster_whisper import WhisperModel

    engine = WhisperModel(model, device="cpu", compute_type="int8", local_files_only=True)
    segments, _ = engine.transcribe(samples, language="en", beam_size=1)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_wav(data: bytes) -> dict[str, str | float]:
    samples, duration = _decode_wav(data)
    # A spawned worker can be terminated if inference stalls; no input/output files persist.
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    worker = ctx.Process(target=_worker, args=(child, samples))
    try:
        worker.start()
    except Exception:
        child.close()
        parent.close()
        raise
    child.close()
    try:
        if not parent.poll(TIMEOUT_SECONDS):
            raise TimeoutError("Speech transcription timed out")
        try:
            status, value = parent.recv()
        except EOFError as exc:
            raise RuntimeError("Speech transcription worker exited early") from exc
        if status != "ok":
            raise RuntimeError(value)
        return {"text": value, "duration_seconds": round(duration, 2), "model": MODEL_ID}
    finally:
        parent.close()
        if worker.is_alive():
            worker.terminate()
        worker.join(timeout=3)
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=3)


def _worker(connection, samples: np.ndarray) -> None:
    try:
        connection.send(("ok", _transcribe(samples)))
    except Exception:
        connection.send(("error", "Local Whisper model is missing or transcription failed"))
    finally:
        connection.close()
