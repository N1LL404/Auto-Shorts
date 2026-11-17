"""Serve the Auto-Shorts studio on the local computer."""
import argparse
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
from uuid import uuid4
from urllib.parse import urlsplit, unquote

from autoshorts import stream_url, yt_dlp_command, probe
from model_settings import ModelSettings


ROOT = Path(__file__).resolve().parent
ACTIVE = {"uploading", "queued", "checking", "running", "stopping"}
JOB_ID = r"[a-f0-9]{12}"
MEDIA = rf"/media/({JOB_ID})/((?:window-\d+/)?clip-\d+\.(?:mp4|jpg|zip))"


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Studio:
    def __init__(self, directory, model):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.lock = threading.RLock()
        self.settings = ModelSettings(directory, self.lock)
        self.jobs = {}
        self.process = None
        for path in directory.glob("*/job.json"):
            row = read_json(path, None)
            if not row or not re.fullmatch(JOB_ID, path.parent.name) or row.get("id") != path.parent.name:
                continue
            self.jobs[row["id"]] = row
            if row["status"] in ACTIVE:
                self.update(row, status="stopped", message="The studio restarted. Completed exports are available.")

    def folder(self, job):
        return self.directory / job["id"]

    def update(self, job, **values):
        with self.lock:
            job.update(values)
            dest = self.folder(job) / "job.json"
            pending = dest.with_suffix(".tmp")
            pending.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            pending.replace(dest)

    def create(self, data, upload=False):
        url = data.get("filename" if upload else "url")
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("Paste a Twitch or YouTube stream URL.")
        url = url.strip()
        for name in ("ffmpeg", "ffprobe"):
            if not shutil.which(name):
                raise ValueError("FFmpeg and FFprobe must be installed. See the setup instructions.")
        if upload:
            url = url.replace("\\", "/").split("/")[-1]
            if Path(url).suffix.lower() not in {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".ts"}:
                raise ValueError("Choose an MP4, MKV, MOV, WebM, AVI, M4V or TS video.")
        else:
            stream_url(url)
        with self.lock:
            if not self.settings.values.get("api_key"):
                raise ValueError("Open AI Settings and save your DeepSeek API key first.")
            if any(job["status"] in ACTIVE for job in self.jobs.values()):
                raise RuntimeError("A stream is already processing. Stop it to start another.")
            job = dict(id=uuid4().hex[:12], url=url, title=url, mode=None,
                       created=datetime.now(timezone.utc).isoformat(), status="queued",
                       message="Waiting to start.")
            if upload:
                job.update(source_kind="upload", status="uploading", mode="recording",
                           filename=url, url=None, message="Uploading video…")
            self.folder(job).mkdir()
            self.update(job)
            self.jobs[job["id"]] = job
            if not upload:
                threading.Thread(target=self.work, args=(job,), daemon=True).start()
            return job["id"]

    def execute(self, job, command, stdout, stderr):
        with self.lock:
            if job["status"] == "stopping":
                return None
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                       cwd=ROOT, stdin=subprocess.DEVNULL,
                                       start_new_session=os.name == "posix")
            self.process = process
        try:
            return process.wait()
        finally:
            with self.lock:
                self.process = None

    def stop(self, job):
        with self.lock:
            if job["status"] not in ACTIVE or job["status"] == "stopping":
                return
            self.update(job, status="stopping", message="Stopping. Finished clips will stay available.")
            if self.process and self.process.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(self.process.pid, signal.SIGINT)
                    else:
                        self.process.terminate()
                except ProcessLookupError:
                    pass

    def work(self, job):
        root = self.folder(job)
        try:
            with self.lock:
                if job["status"] != "stopping":
                    self.update(job, status="checking", message="Checking uploaded video…" if job.get("source_kind") == "upload" else "Checking the stream URL…")
            with (root / "activity.log").open("ab", buffering=0) as log:
                source = job.get("url")
                live = False
                if job.get("source_kind") == "upload":
                    source = str(root / ("source" + Path(job["filename"]).suffix.lower()))
                    try:
                        _, _, audio = probe(source)
                        if not audio:
                            raise ValueError("This video has no audio track for Whisper.")
                    except subprocess.CalledProcessError:
                        raise ValueError("The uploaded file could not be read as a video.") from None
                    with self.lock:
                        if job["status"] != "stopping":
                            self.update(job, status="running", message="Transcribing uploaded video…")
                else:
                    meta_file = root / "metadata.json"
                    with meta_file.open("wb") as meta:
                        code = self.execute(job, [*yt_dlp_command(), "--no-playlist", "--skip-download",
                                                  "--dump-single-json", "--socket-timeout", "25",
                                                  "--retries", "2", "--", job["url"]], meta, log)
                    metadata = read_json(meta_file, {})
                    meta_file.unlink(missing_ok=True)
                    with self.lock:
                        if job["status"] == "stopping":
                            self.update(job, status="stopped", message="Stopped.")
                            return
                        if code != 0:
                            raise ValueError("Couldn’t open this stream. Check that the URL is public and playable.")
                        if metadata.get("live_status") == "is_upcoming":
                            raise ValueError("This stream hasn’t started. Try again once it goes live.")
                        live = metadata.get("is_live") or metadata.get("live_status") == "is_live"
                        self.update(job, status="running", title=metadata.get("title") or job["url"],
                                    mode="live" if live else "recording",
                                    message="Capturing the live stream…" if live else "Downloading the recording…")
                command = [sys.executable, "-u", str(ROOT / "autoshorts.py"), source,
                           "--output", str(root / "exports"), "--publish-kit", "--clips", "3"]
                command += ["--selector", "deepseek", "--settings-file", str(self.settings.path),
                            "--whisper", self.settings.values["whisper"], "--captions"]
                if live:
                    command.append("--live")
                code = self.execute(job, command, log, subprocess.STDOUT)
            with self.lock:
                if job["status"] == "stopping":
                    self.update(job, status="stopped", message="Capture stopped.")
                elif code == 0:
                    clips = read_json(root / "exports" / "clips.json", [])
                    message = ("Finished. Your exports are ready to review." if clips
                               else "Finished. No clip candidates were exported.")
                    self.update(job, status="done", message=message)
                else:
                    raise ValueError("Processing ended early. Check the activity details and try again.")
        except (OSError, ValueError) as exc:
            with self.lock:
                if job["status"] == "stopping":
                    self.update(job, status="stopped", message="Stopped.")
                else:
                    self.update(job, status="error", message=str(exc))

    def details(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            result = job.copy()
        root = self.folder(result)
        clips = read_json(root / "exports" / "clips.json", [])
        result["clips"] = clips
        try:
            with (root / "activity.log").open("rb") as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell()-12000))
                tail = deque(log.read().decode("utf-8", "replace").splitlines(), maxlen=10)
            result["activity"] = "\n".join(line[-500:] for line in tail)
        except OSError:
            result["activity"] = ""
        return result


class Handler(BaseHTTPRequestHandler):
    def json_response(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path, download=False):
        try:
            handle = path.open("rb")
        except OSError:
            self.send_error(404)
            return
        with handle:
            size = path.stat().st_size
            start, end = 0, size - 1
            value = self.headers.get("Range")
            if value:
                match = re.fullmatch(r"bytes=(\d{0,19})-(\d{0,19})", value)
                if match and any(match.groups()):
                    left, right = match.groups()
                    if left:
                        start = int(left)
                        end = min(end, int(right)) if right else end
                    else:
                        start = max(0, size - int(right))
                if not match or not any(match.groups()) or not 0 <= start <= end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
            self.send_response(206 if value else 200)
            if value:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(end - start + 1))
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.end_headers()
            if self.command == "HEAD":
                return
            handle.seek(start)
            remaining = end - start + 1
            try:
                while remaining and (block := handle.read(min(256 * 1024, remaining))):
                    self.wfile.write(block)
                    remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def local_host(self):
        host = self.headers.get("Host", "")
        return re.fullmatch(r"(?:localhost|127\.0\.0\.1|\[::1\])(?::\d{1,5})?", host) is not None

    def do_GET(self):
        if not self.local_host():
            self.send_error(403)
            return
        uri = urlsplit(self.path)
        route = uri.path
        studio = self.server.studio
        if route in ("/", "/studio.css", "/studio.js"):
            self.send_file(ROOT / "web" / ("index.html" if route == "/" else route[1:]))
        elif route == "/api/settings":
            self.json_response(studio.settings.public())
        elif route == "/api/jobs":
            with studio.lock:
                self.json_response(list(reversed(list(studio.jobs.values()))))
        elif match := re.fullmatch(rf"/api/jobs/({JOB_ID})", route):
            data = studio.details(match[1])
            self.json_response(data if data else {"error": "Job not found."}, 200 if data else 404)
        elif match := re.fullmatch(MEDIA, route):
            self.send_file(studio.directory / match[1] / "exports" / match[2],
                           uri.query == "download=1")
        else:
            self.send_error(404)

    do_HEAD = do_GET

    def do_POST(self):
        origin = self.headers.get("Origin")
        host = self.headers.get("Host")
        if (not self.local_host() or (origin and origin != f"http://{host}")
                or self.headers.get_content_type() != ("application/octet-stream" if self.path == "/api/uploads" else "application/json")):
            self.json_response({"error": "Open the studio directly in your browser."}, 403)
            return
        studio = self.server.studio
        try:
            if self.path == "/api/uploads":
                self.receive_upload()
            elif self.path.startswith("/api/settings"):
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Invalid settings request.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Invalid settings request.")
                if self.path == "/api/settings":
                    with studio.lock:
                        if any(j["status"] in ACTIVE for j in studio.jobs.values()):
                            raise RuntimeError("Stop the active job before changing AI settings.")
                        result = studio.settings.save(data)
                elif self.path == "/api/settings/models":
                    result = studio.settings.discover()
                elif self.path == "/api/settings/test":
                    result = studio.settings.test()
                elif self.path == "/api/settings/whisper":
                    result = studio.settings.prepare()
                else:
                    self.json_response({"error": "Unknown settings action."}, 404)
                    return
                self.json_response(result)
            elif self.path == "/api/jobs":
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Paste a single stream URL.")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Paste a single stream URL.")
                self.json_response({"id": studio.create(body)}, 202)
            elif match := re.fullmatch(rf"/api/jobs/({JOB_ID})/stop", self.path):
                with studio.lock:
                    job = studio.jobs.get(match[1])
                    if job:
                        studio.stop(job)
                self.json_response({"ok": True} if job else {"error": "Job not found."}, 202 if job else 404)
            else:
                self.json_response({"error": "Page not found."}, 404)
        except ValueError as exc:
            self.json_response({"error": str(exc)}, 400)
        except RuntimeError as exc:
            self.json_response({"error": str(exc)}, 409)

    def receive_upload(self):
        studio = self.server.studio
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0:
            raise ValueError("Choose a non-empty video file.")
        if size >= shutil.disk_usage(studio.directory).free:
            raise ValueError("There is not enough disk space to upload this video.")
        filename = unquote(self.headers.get("X-Filename", ""))
        job_id = studio.create({"filename": filename}, upload=True)
        job = studio.jobs[job_id]
        root = studio.folder(job)
        temporary = root / "source.partial"
        self.connection.settimeout(120)
        try:
            with temporary.open("wb") as output:
                remaining = size
                while remaining:
                    with studio.lock:
                        if job["status"] == "stopping":
                            raise ValueError("Upload stopped.")
                    block = self.rfile.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError("Upload interrupted. Select the video and try again.")
                    output.write(block)
                    remaining -= len(block)
            with studio.lock:
                if job["status"] == "stopping":
                    raise ValueError("Upload stopped.")
                temporary.replace(root / ("source" + Path(filename).suffix.lower()))
                studio.update(job, status="queued", message="Upload complete. Preparing video…")
                threading.Thread(target=studio.work, args=(job,), daemon=True).start()
        except (OSError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            with studio.lock:
                stopped = job["status"] == "stopping"
                studio.update(job, status="stopped" if stopped else "error",
                              message="Upload stopped." if stopped else "Upload interrupted. Please retry.")
            raise ValueError("Upload stopped or interrupted. Select the video and try again.") from exc
        self.json_response({"id": job_id}, 202)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8070)
    parser.add_argument("--data", type=Path, default=ROOT / "studio-data")
    parser.add_argument("--model", default="base.en", help="Whisper model; use an empty value to disable captions")
    args = parser.parse_args()
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        server.studio = Studio(args.data.resolve(), args.model)
        try:
            print(f"Auto-Shorts Studio · http://localhost:{server.server_port}", flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            with server.studio.lock:
                for job in server.studio.jobs.values():
                    server.studio.stop(job)


if __name__ == "__main__":
    main()
