import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import autoshorts
import deepseek
from model_settings import ModelSettings
from studio import Handler, Studio, ThreadingHTTPServer


SEGMENTS = [
    {"start": i*5, "end": (i+1)*5, "text": f"Story sentence {i}.",
     "words": [{"start": i*5, "end": (i+1)*5, "text": f"Sentence {i}"}]}
    for i in range(30)
]
PICK = {"start_id": 1, "end_id": 6, "peak_id": 4, "score": 90,
        "hook": "THE TRAP WORKED", "reason": "Setup, trap reveal and reaction."}


class WorkflowTests(unittest.TestCase):
    def test_boundaries_are_taken_from_transcript(self):
        rows = deepseek.validate_picks({"clips": [PICK, dict(PICK, end_id=300),
                dict(PICK, start_id=True), dict(PICK, score=float("nan"))]},
                SEGMENTS, 0, 30, 150, 25, 55)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["start"], rows[0]["end"]), (5, 35))

    def test_all_transcript_sections_are_covered(self):
        ranges = list(deepseek.transcript_chunks(SEGMENTS, 55, char_limit=500))
        self.assertEqual(set(i for lo, hi in ranges for i in range(lo, hi)), set(range(30)))

    def test_selection_deduplicates_and_reports_invalid_boundaries(self):
        with tempfile.TemporaryDirectory() as temp, patch("deepseek.completion",
                return_value={"clips": [PICK, dict(PICK, score=80)]}):
            result = deepseek.select_clips(SEGMENTS, 150, {"api_key": "secret", "model": "example"},
                                          3, 25, 55, Path(temp))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["hook"], PICK["hook"])
        with tempfile.TemporaryDirectory() as temp, patch("deepseek.completion",
                return_value={"clips": [dict(PICK, end_id=500)]}):
            with self.assertRaisesRegex(ValueError, "invalid clip boundaries"):
                deepseek.select_clips(SEGMENTS, 150, {"api_key": "secret", "model": "example"},
                                      3, 25, 55, Path(temp))

    def test_errors_do_not_expose_key(self):
        error = HTTPError("https://api.deepseek.com", 401, "secret-key-here", {}, None)
        with patch("deepseek.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "^DeepSeek rejected the API key.$"):
                deepseek.api_request("secret-key-here", "/models")

    def test_settings_key_is_preserved_and_never_returned(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ModelSettings(Path(temp), threading.RLock())
            public = manager.save({"api_key": "secret-key", "model": "my-model", "whisper": "small.en"})
            self.assertNotIn("secret-key", json.dumps(public))
            manager.save({"api_key": "", "model": "my-model", "whisper": "small.en"})
            self.assertEqual(manager.values["api_key"], "secret-key")
            self.assertEqual(manager.path.stat().st_mode & 0o777, 0o600)
            restored = ModelSettings(Path(temp), threading.RLock())
            self.assertEqual(restored.values["model"], "my-model")
            restored.save({"remove_key": True})
            self.assertFalse(restored.public()["has_key"])

    def test_settings_api_and_job_command(self):
        with tempfile.TemporaryDirectory() as temp:
            studio = Studio(Path(temp), "base.en")
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.studio = studio
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            def post(path, data):
                req = Request(base+path, data=json.dumps(data).encode(),
                              headers={"Content-Type":"application/json"})
                with urlopen(req) as response:
                    return json.load(response)
            try:
                public = post("/api/settings", {"api_key": "key", "model": "deepseek-flash",
                                               "whisper": "tiny.en"})
                self.assertTrue(public["has_key"])
                with patch("model_settings.completion", return_value={"ok": True}):
                    self.assertIn("successful", post("/api/settings/test", {})["message"])
                with patch("model_settings.api_request", return_value={"data":[{"id":"my-model"}]}):
                    self.assertEqual(post("/api/settings/models", {})["models"], ["my-model"])
                with patch("studio.stream_url"), patch.object(studio, "work"):
                    id = studio.create({"url":"https://youtu.be/example"})
                commands = []
                def execute(job, command, stdout, stderr):
                    commands.append(command)
                    if "--dump-single-json" in command:
                        stdout.write(json.dumps({"title":"Test", "live_status":"was_live"}).encode())
                    return 0
                with patch.object(studio, "execute", side_effect=execute):
                    studio.work(studio.jobs[id])
                command = commands[-1]
                self.assertEqual(command[command.index("--selector")+1], "deepseek")
                self.assertEqual(command[command.index("--whisper")+1], "tiny.en")
                self.assertNotIn("key", command)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
