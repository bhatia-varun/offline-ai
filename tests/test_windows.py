import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np

from app import stt
from scripts import windows


def wav_bytes(channels=1, rate=16_000, seconds=1):
    output = io.BytesIO()
    with wave.open(output, "wb") as clip:
        clip.setnchannels(channels)
        clip.setsampwidth(2)
        clip.setframerate(rate)
        clip.writeframes(b"\0\0" * channels * rate * seconds)
    return output.getvalue()


class SpeechTests(unittest.TestCase):
    def test_valid_wav_keeps_existing_contract(self):
        samples, duration = stt._decode_wav(wav_bytes())
        self.assertEqual(samples.shape, (16_000,))
        self.assertEqual(samples.dtype, np.float32)
        self.assertEqual(duration, 1)

    def test_invalid_audio_never_reaches_inference(self):
        invalid = [b"invalid", wav_bytes(channels=2), wav_bytes(rate=8_000), wav_bytes(seconds=16),
                   wav_bytes()[:-2], b"\0" * (stt.MAX_BYTES + 1)]
        for data in invalid:
            with self.subTest(size=len(data)), patch.object(stt, "_transcribe") as inference:
                with self.assertRaises(stt.AudioInputError):
                    stt.transcribe_wav(data)
                inference.assert_not_called()

    def test_windows_backend_uses_only_cached_cpu_model(self):
        engine = Mock()
        engine.transcribe.return_value = (iter([SimpleNamespace(text=" Hello "), SimpleNamespace(text="world. ")]), None)
        with tempfile.TemporaryDirectory() as directory:
            for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
                (Path(directory) / name).touch()
            with patch.object(stt, "USE_MLX", False), patch.object(stt, "snapshot_download", return_value=directory) as download, \
                    patch("faster_whisper.WhisperModel", return_value=engine) as model:
                self.assertEqual(stt._transcribe(np.zeros(16_000, dtype=np.float32)), "Hello world.")
                self.assertTrue(download.call_args.kwargs["local_files_only"])
                model.assert_called_once_with(directory, device="cpu", compute_type="int8", local_files_only=True)

    def test_missing_weights_fail_before_engine_creation(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(stt, "USE_MLX", False), \
                patch.object(stt, "snapshot_download", return_value=directory), patch("faster_whisper.WhisperModel") as model:
            with self.assertRaises(FileNotFoundError):
                stt._transcribe(np.zeros(16_000, dtype=np.float32))
            model.assert_not_called()


class McpTests(unittest.TestCase):
    def test_installed_sdk_supports_the_server_api(self):
        from mcp.server.fastmcp import FastMCP
        from mcp_servers.demo import server

        self.assertIsInstance(server, FastMCP)


class LifecycleTests(unittest.TestCase):
    def test_n8n_readiness_requires_editor_routes(self):
        with patch.object(windows.requests, "get", return_value=SimpleNamespace(ok=False)) as get:
            self.assertFalse(windows.healthy("n8n"))
            get.assert_called_once_with("http://127.0.0.1:5678/rest/settings", timeout=2)

    def test_n8n_can_become_ready_after_three_minutes(self):
        process = Mock()
        process.create_time.return_value = 100
        process.cmdline.return_value = ["node.exe", "n8n", "start"]
        with tempfile.TemporaryDirectory() as directory, patch.object(windows, "LOGS", Path(directory)), \
                patch.object(windows, "dotenv_values", return_value={}), \
                patch.object(windows.shutil, "which", side_effect=lambda name: name), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(windows, "tracked_process", side_effect=[None, None, process, process]), \
                patch.object(windows, "listening", return_value=False), \
                patch.object(windows, "healthy", side_effect=[True, False, True]) as health, \
                patch.object(windows.subprocess, "Popen", return_value=SimpleNamespace(pid=123)), \
                patch.object(windows.psutil, "Process", return_value=process), \
                patch.object(windows.time, "monotonic", side_effect=[0, 0, 181, 181, 181, 182]), \
                patch.object(windows.threading, "Event"), patch.object(windows, "stop") as stop:
            windows.start(["n8n"])
            self.assertEqual(health.call_count, 3)
            stop.assert_not_called()

    def test_webui_launcher_uses_isolated_environment(self):
        executable = Path(windows.SERVICES["webui"][2][0])
        self.assertEqual(executable, windows.ROOT / ".venv-webui" / "Scripts" / "open-webui.exe")
        self.assertNotEqual(executable.parent, windows.PYTHON.parent)

    def test_pid_reuse_and_command_mismatch_are_not_owned(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(windows, "LOGS", Path(directory)):
            (Path(directory) / "api.process.json").write_text(json.dumps({"pid": 123, "created": 100, "command": ["owned"]}))
            process = Mock()
            with patch.object(windows.psutil, "Process", return_value=process):
                process.create_time.return_value = 101
                self.assertIsNone(windows.tracked_process("api"))
                process.create_time.return_value = 100
                process.cmdline.return_value = ["unrelated"]
                self.assertIsNone(windows.tracked_process("api"))
                process.cmdline.return_value = ["owned"]
                self.assertIs(windows.tracked_process("api"), process)

    def test_stop_does_not_kill_untracked_listener(self):
        with patch.object(windows, "tracked_process", return_value=None), patch.object(windows.psutil, "Process") as process:
            windows.stop("api")
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()