"""Locate packaged Whisper weights without consulting the network."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")


def bundled_model(model):
    if model != "base.en":
        return None
    for folder in (ROOT / "whisper-models" / model, ROOT / "vendor" / "whisper" / model):
        if all((folder / name).is_file() and (folder / name).stat().st_size > 0
               for name in REQUIRED_FILES):
            return folder
    return None


def load_whisper(model):
    from faster_whisper import WhisperModel
    folder = bundled_model(model)
    if folder:
        return WhisperModel(str(folder), device="cpu", compute_type="int8", local_files_only=True)
    if model == "base.en" and getattr(sys, "frozen", False):
        raise ValueError("Bundled Whisper files are missing. Extract the entire app ZIP, including the _internal folder.")
    return WhisperModel(model, device="cpu", compute_type="int8")
