"""Fetch the pinned, checksum-verified Whisper base.en model for packaging."""
import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import urlopen
from huggingface_hub import snapshot_download
from faster_whisper import WhisperModel

REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"
CHECKSUMS = {'vocabulary.txt': 'ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf', 'config.json': 'f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb', 'model.bin': '2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef', 'tokenizer.json': '929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df'}
root = Path(__file__).resolve().parents[1]
destination = root / "vendor" / "whisper" / "base.en"
snapshot_download("Systran/faster-whisper-base.en", revision=REVISION,
                  allow_patterns=list(CHECKSUMS), local_dir=destination)
for name, expected in CHECKSUMS.items():
    if hashlib.sha256((destination / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError("Whisper checksum mismatch: " + name)
shutil.rmtree(destination / ".cache", ignore_errors=True)
WhisperModel(str(destination), device="cpu", compute_type="int8", local_files_only=True)
with urlopen("https://raw.githubusercontent.com/openai/whisper/main/LICENSE", timeout=30) as response:
    (destination / "LICENSE.txt").write_bytes(response.read())
(destination / "SOURCE.json").write_text(json.dumps({
    "repository": "https://huggingface.co/Systran/faster-whisper-base.en",
    "revision": REVISION, "sha256": CHECKSUMS}, indent=2), encoding="utf-8")
print("Whisper base.en verified and ready to bundle.")
