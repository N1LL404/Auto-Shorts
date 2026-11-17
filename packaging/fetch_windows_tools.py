"""Fetch and verify the Windows command-line tools included with the desktop app."""
import hashlib
from pathlib import Path
import re
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "vendor"
BIN = DEST / "bin"
BIN.mkdir(parents=True, exist_ok=True)


def get(url):
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.read()


def verified(url, checksum):
    data = get(url)
    if hashlib.sha256(data).hexdigest().lower() != checksum.lower():
        raise RuntimeError("Checksum mismatch for " + url)
    return data


ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
checksum = re.search(r"\b[0-9a-fA-F]{64}\b", get(ffmpeg_url + ".sha256").decode()).group()
archive = DEST / "ffmpeg.zip"
archive.write_bytes(verified(ffmpeg_url, checksum))
with zipfile.ZipFile(archive) as bundle:
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        member = next(n for n in bundle.namelist() if n.endswith("/bin/" + name))
        (BIN / name).write_bytes(bundle.read(member))
    license_member = next(n for n in bundle.namelist() if n.endswith("/LICENSE"))
    (DEST / "FFmpeg-LICENSE.txt").write_bytes(bundle.read(license_member))
archive.unlink()

yt_base = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
checks = get(yt_base + "SHA2-256SUMS").decode()
checksum = next(line.split()[0] for line in checks.splitlines() if line.split()[-1] == "yt-dlp.exe")
(BIN / "yt-dlp.exe").write_bytes(verified(yt_base + "yt-dlp.exe", checksum))
(DEST / "yt-dlp-LICENSE.txt").write_bytes(get("https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/LICENSE"))

node_base = "https://nodejs.org/dist/latest-v24.x/"
checks = get(node_base + "SHASUMS256.txt").decode()
checksum = next(line.split()[0] for line in checks.splitlines() if line.split()[-1] == "win-x64/node.exe")
(BIN / "node.exe").write_bytes(verified(node_base + "win-x64/node.exe", checksum))
(DEST / "Node-LICENSE.txt").write_bytes(get("https://raw.githubusercontent.com/nodejs/node/v24.x/LICENSE"))
(DEST / "NOTICE.txt").write_text(
    "Auto-Shorts bundles separate FFmpeg/FFprobe, yt-dlp and Node executables.\n"
    "FFmpeg build and corresponding source information: https://www.gyan.dev/ffmpeg/builds/\n"
    "FFmpeg source: https://github.com/FFmpeg/FFmpeg\n"
    "yt-dlp source: https://github.com/yt-dlp/yt-dlp\n"
    "Node source: https://github.com/nodejs/node/tree/v24.x\n"
    "See the accompanying upstream license files.\n", encoding="utf-8")
print("Verified Windows tools prepared.")
