import io
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import autoshorts
from progress import emit, snapshot


class ProgressTests(unittest.TestCase):
    def test_worker_event_reaches_presentation(self):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            emit(1, 43, "Audio timeline 43s / 100s")
        state = snapshot({"status": "running", "activity": out.getvalue()})
        self.assertEqual((state["stage"], state["percent"]), (1, 43))
        self.assertIn("43%", state["detail"])

    def test_ai_waiting_has_no_fake_percent(self):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            emit(2, detail="Section 2 of 4")
        state = snapshot({"status": "running", "activity": out.getvalue()})
        self.assertIsNone(state["percent"])
        self.assertTrue(state["active"])

    def test_terminal_states_stop_animation(self):
        for status in ("done", "stopped", "error"):
            state = snapshot({"status": status, "message": "result"})
            self.assertFalse(state["active"])
            self.assertEqual(state["percent"], 100 if status == "done" else 0)

    def test_bad_and_truncated_events_are_ignored(self):
        for text in ('{', '{"stage": 9}', '{"stage": 1, "percent": "bad"}', '{"stage": 1, "percent": NaN}'):
            self.assertIsNone(snapshot({"status": "running", "activity": "AUTOSHORTS_PROGRESS " + text})["percent"])

    def test_transcription_reports_timeline_and_completion(self):
        segment = SimpleNamespace(start=0, end=5, text=" hello ", words=[])
        model = SimpleNamespace(transcribe=lambda *a, **k: (iter([segment]), SimpleNamespace(duration=10)))
        with patch("autoshorts.whisper_model", return_value=model), patch("autoshorts.emit") as report:
            rows = autoshorts.transcribe("fixture.mp4", "base.en")
        self.assertEqual(rows[0]["text"], "hello")
        self.assertEqual([c.args[1] for c in report.call_args_list if len(c.args) > 1], [50, 100])
