import io
import os
import zipfile
from types import SimpleNamespace
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
            result = deepseek.select_clips(SEGMENTS, 150, {"api_key": "secret", "model": "example"},
                                          3, 25, 55, Path(temp))
            self.assertEqual(result, [])
            report = (Path(temp) / "selection-diagnostics.json").read_text()
            self.assertIn("rejected", report)
            self.assertNotIn("secret", report)

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
            if os.name != "nt":
                self.assertEqual(manager.path.stat().st_mode & 0o777, 0o600)
            restored = ModelSettings(Path(temp), threading.RLock())
            self.assertEqual(restored.values["model"], "my-model")
            restored.save({"remove_key": True})
            self.assertFalse(restored.public()["has_key"])

    def test_completion_rejects_malformed_or_truncated_output(self):
        for value in ({"choices": [None]}, {"choices": [{"finish_reason": "length"}]},
                      {"choices": [{"finish_reason": "stop", "message": {"content": "  "}}]}):
            with self.subTest(value=value), patch("deepseek.api_request", return_value=value):
                with self.assertRaisesRegex(ValueError, "invalid JSON"):
                    deepseek.completion("key", "model", "JSON", {})

    def test_invalid_selection_gets_one_correction(self):
        with tempfile.TemporaryDirectory() as temp, patch("deepseek.completion",
                side_effect=[{"clips": [dict(PICK, end_id=500)]}, {"clips": [PICK]}]) as call:
            rows = deepseek.select_clips(SEGMENTS, 150, {"api_key": "key", "model": "model"},
                                        3, 25, 55, Path(temp))
            self.assertEqual(len(rows), 1)
            self.assertEqual(call.call_count, 2)
            self.assertIn("correction", call.call_args.args[3])

    def test_transient_errors_retry_but_auth_errors_do_not(self):
        error = HTTPError("https://api.deepseek.com", 429, "limited", {}, None)
        with patch("deepseek.urlopen", side_effect=[error, io.BytesIO(b'{"data": []}')]) as request, patch("deepseek.time.sleep"):
            self.assertEqual(deepseek.api_request("key", "/models"), {"data": []})
            self.assertEqual(request.call_count, 2)

    def test_silent_live_window_continues_without_paid_call(self):
        with tempfile.TemporaryDirectory() as temp, patch("deepseek.completion") as call:
            self.assertEqual(deepseek.select_clips([], 90, {}, 3, 25, 55, Path(temp), (30, 60)), [])
            call.assert_not_called()
            with self.assertRaisesRegex(ValueError, "no speech"):
                deepseek.select_clips([], 90, {}, 3, 25, 55, Path(temp))

    def test_invalid_model_list_is_user_facing_error(self):
        with tempfile.TemporaryDirectory() as temp, patch("model_settings.api_request", return_value=[]):
            manager = ModelSettings(Path(temp), threading.RLock())
            with self.assertRaisesRegex(ValueError, "invalid model list"):
                manager.discover()

    @unittest.skipUnless(os.environ.get("AUTO_SHORTS_TEST_VIDEO"), "Set AUTO_SHORTS_TEST_VIDEO for real FFmpeg integration")
    def test_transcript_to_video_and_publish_kit(self):
        source = Path(os.environ["AUTO_SHORTS_TEST_VIDEO"])
        fixture = {"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"clips": [PICK]})}}]}
        args = SimpleNamespace(whisper="base.en", start=None, selector="deepseek",
            settings_file=None, clips=3, min_length=25, max_length=55, hook=None,
            publish_kit=True, captions=True, facecam=(0, 0, .24, .241), center=.5, fps=30)
        with tempfile.TemporaryDirectory() as temp, patch("autoshorts.transcribe", return_value=SEGMENTS[:11]), patch(
                "deepseek.urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps(fixture).encode())):
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "fixture-only"}):
                rows = autoshorts.process(source, args, Path(temp))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["hook"], PICK["hook"])
            self.assertEqual((rows[0]["start"], rows[0]["end"]), (5, 35))
            duration, video, audio = autoshorts.probe(Path(temp) / rows[0]["file"])
            self.assertAlmostEqual(duration, 30, delta=.15)
            self.assertEqual((video["width"], video["height"]), (1080, 1920))
            self.assertTrue(audio)
            with zipfile.ZipFile(Path(temp) / rows[0]["kit"]) as kit:
                self.assertEqual(set(kit.namelist()), {"short.mp4", "cover.jpg", "post.txt"})
            self.assertEqual(len(json.loads((Path(temp) / "transcript.json").read_text())), 11)

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
