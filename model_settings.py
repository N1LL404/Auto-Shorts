"""Local provider settings and asynchronous Whisper preparation."""
import json
import os
from pathlib import Path
import threading

from deepseek import DEFAULT_MODEL, WHISPER_MODELS, api_request, completion, load_settings


class ModelSettings:
    def __init__(self, directory, lock):
        self.path = directory / "ai-settings.json"
        self.lock = lock
        self.values = load_settings(self.path)
        self.download = {"status": "idle", "model": None, "message": ""}
        self.ready_file = directory / "whisper-ready.json"
        try:
            self.ready = json.loads(self.ready_file.read_text())
        except (OSError, ValueError):
            self.ready = []

    def public(self):
        with self.lock:
            return {"has_key": bool(self.values.get("api_key")),
                    "model": self.values.get("model", DEFAULT_MODEL),
                    "whisper": self.values.get("whisper", "base.en"),
                    "whisper_choices": WHISPER_MODELS, "ready": list(self.ready),
                    "download": self.download.copy()}

    def save(self, data):
        with self.lock:
            model = data.get("model", self.values["model"])
            whisper = data.get("whisper", self.values["whisper"])
            key = data.get("api_key", "")
            if not isinstance(model, str) or not model.strip() or len(model) > 100:
                raise ValueError("Choose a DeepSeek model.")
            if whisper not in WHISPER_MODELS:
                raise ValueError("Choose a supported Whisper model.")
            if not isinstance(key, str) or len(key) > 512 or any(ord(c) < 32 or ord(c) > 126 for c in key):
                raise ValueError("Invalid API key.")
            values = {"model": model.strip(), "whisper": whisper,
                      "api_key": key.strip() or self.values.get("api_key", "")}
            if data.get("remove_key") is True:
                values["api_key"] = ""
            pending = self.path.with_suffix(".tmp")
            fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(values, f)
            os.chmod(pending, 0o600)
            pending.replace(self.path)
            self.values = values
            return self.public()

    def discover(self):
        with self.lock:
            key = self.values.get("api_key", "")
        result = api_request(key, "/models")
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ValueError("DeepSeek returned an invalid model list. Please retry.")
        return {"models": [r["id"] for r in result["data"]
                           if isinstance(r, dict) and isinstance(r.get("id"), str)]}

    def test(self):
        with self.lock:
            values = self.values.copy()
        result = completion(values.get("api_key", ""), values["model"],
                            'Return JSON only: {"ok":true}.', {"test": "connection"})
        if result.get("ok") is not True:
            raise ValueError("The selected model did not return the expected response.")
        return {"message": "DeepSeek connection successful."}

    def prepare(self):
        with self.lock:
            if self.download["status"] == "downloading":
                return self.public()
            model = self.values["whisper"]
            self.download = {"status": "downloading", "model": model,
                             "message": f"Downloading and checking {model}…"}
            threading.Thread(target=self._prepare, args=(model,), daemon=True).start()
            return self.public()

    def _prepare(self, model):
        try:
            from faster_whisper import WhisperModel
            instance = WhisperModel(model, device="cpu", compute_type="int8")
            del instance
            with self.lock:
                self.ready = sorted(set(self.ready + [model]))
                pending = self.ready_file.with_suffix(".tmp")
                pending.write_text(json.dumps(self.ready))
                pending.replace(self.ready_file)
                self.download = {"status": "ready", "model": model, "message": f"{model} is ready."}
        except Exception as exc:
            detail = str(exc).lower()
            if isinstance(exc, ImportError) and "socks" in detail:
                message = "Your network uses a SOCKS proxy. Install socksio, then retry Whisper download."
            elif isinstance(exc, ImportError):
                message = "Whisper dependencies are missing or incompatible. Run python -m pip install --upgrade -r requirements.txt, restart the studio, and retry."
            elif "certificate" in detail or "ssl" in detail:
                message = "The model download failed certificate verification. Configure your network's trusted CA certificate and retry."
            elif isinstance(exc, PermissionError):
                message = "Whisper cannot write to its model cache. Check the cache directory permissions."
            elif isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
                message = "There is not enough disk space for the Whisper model. Free space and retry."
            else:
                message = ("Whisper model download or loading failed (" + type(exc).__name__ +
                           "). Check Hugging Face access and reinstall the current requirements.txt. Retry the download.")
            with self.lock:
                self.download = {"status": "error", "model": model,
                                 "message": message}
