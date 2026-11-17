import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from model_settings import ModelSettings
from studio import Studio, Handler, ThreadingHTTPServer


class UploadTests(unittest.TestCase):
    def test_upload_is_streamed_and_uses_local_processing(self):
        with tempfile.TemporaryDirectory() as temp:
            studio = Studio(Path(temp), "base.en")
            studio.settings.save({"api_key": "fixture-key"})
            with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
                server.studio = studio
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    req = Request(f"http://127.0.0.1:{server.server_port}/api/uploads",
                                  data=b"test-video-bytes",
                                  headers={"Content-Type":"application/octet-stream",
                                           "X-Filename":"my%20download.MP4"})
                    with patch.object(studio, "work") as work, patch("studio.stream_url") as remote:
                        with urlopen(req) as response:
                            result = json.load(response)
                        remote.assert_not_called()
                    job = studio.jobs[result["id"]]
                    self.assertEqual(job["filename"], "my download.MP4")
                    source = studio.folder(job) / "source.mp4"
                    self.assertEqual(source.read_bytes(), b"test-video-bytes")
                    self.assertFalse((studio.folder(job) / "source.partial").exists())
                    commands = []
                    def execute(job, command, stdout, stderr):
                        commands.append(command)
                        return 0
                    with patch("studio.probe", return_value=(30, {}, True)), patch.object(
                            studio, "execute", side_effect=execute):
                        studio.work(job)
                    self.assertEqual(len(commands), 1)
                    self.assertIn(str(source), commands[0])
                    self.assertIn("--selector", commands[0])
                    self.assertNotIn("--live", commands[0])
                    self.assertEqual(job["status"], "done")
                    req = Request(f"http://127.0.0.1:{server.server_port}/api/uploads",
                                  data=b"test", headers={"Content-Type":"application/octet-stream",
                                                       "X-Filename":"invalid.exe"})
                    with self.assertRaises(HTTPError) as error:
                        urlopen(req)
                    self.assertEqual(error.exception.code, 400)
                finally:
                    server.shutdown()
                    thread.join()

    def test_upload_reserves_job_and_normalizes_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            studio = Studio(Path(temp), "base.en")
            studio.settings.save({"api_key":"fixture-key"})
            id = studio.create({"filename":"../../recording.mp4"}, upload=True)
            self.assertEqual(studio.jobs[id]["filename"], "recording.mp4")
            self.assertEqual(studio.jobs[id]["status"], "uploading")
            with self.assertRaises(RuntimeError):
                studio.create({"filename":"second.mp4"}, upload=True)

    def test_whisper_failure_has_specific_remedy(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = ModelSettings(Path(temp), threading.RLock())
            def missing(*args, **kwargs):
                raise ImportError("Using SOCKS proxy but socksio is missing")
            with patch.dict(sys.modules, {"faster_whisper":SimpleNamespace(WhisperModel=missing)}):
                settings._prepare("base.en")
            self.assertEqual(settings.download["status"], "error")
            self.assertIn("socksio", settings.download["message"])


if __name__ == "__main__":
    unittest.main()
