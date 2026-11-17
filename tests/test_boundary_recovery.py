"""Regressions for twice-invalid DeepSeek selections using deterministic responses."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import deepseek

SEGMENTS = [{"start": i * 5, "end": (i + 1) * 5, "text": f"Sentence {i}"}
            for i in range(30)]
PICK = {"start_id": 1, "end_id": 6, "peak_id": 4, "score": 90,
        "hook": "THE TRAP WORKED", "reason": "Setup and payoff."}


class BoundaryRecoveryTests(unittest.TestCase):
    def validate(self, picks, duration=150, lo=0, hi=30, minimum=25, maximum=55):
        return deepseek.validate_picks({"clips": picks}, SEGMENTS, lo, hi, duration,
                                       minimum, maximum)

    def select(self, responses, chunks=None):
        with tempfile.TemporaryDirectory() as temp, patch("deepseek.completion",
                side_effect=responses) as call, patch("deepseek.transcript_chunks",
                return_value=iter(chunks or [(0, 30)])):
            rows = deepseek.select_clips(SEGMENTS, 150, {"api_key": "private", "model": "test"},
                                         3, 25, 55, Path(temp))
            saved = json.loads((Path(temp) / "selection.json").read_text())
            report = json.loads((Path(temp) / "selection-diagnostics.json").read_text())
            self.assertEqual(saved, rows)
            self.assertNotIn("private", json.dumps(report))
            return rows, call.call_count, report

    def test_exact_numeric_representations_work_without_retry(self):
        rows, calls, _ = self.select([{"clips": [dict(PICK, start_id="1", end_id=6.0,
                                                       peak_id="4", score="90")]}])
        self.assertEqual(calls, 1)
        self.assertEqual((rows[0]["start"], rows[0]["end"]), (5, 35))

    def test_short_pick_keeps_entire_story_and_peak(self):
        rows, calls, report = self.select([{"clips": [dict(PICK, end_id=4)]}])
        self.assertEqual(calls, 1)
        row = rows[0]
        self.assertLessEqual(row["start"], 5)
        self.assertGreaterEqual(row["end"], 25)
        self.assertEqual(row["end"] - row["start"], 25)
        self.assertEqual(row["peak"], 20)
        self.assertEqual(report[0]["issues"][0]["status"], "repaired")

    def test_does_not_invent_ids_or_round_fractional_values(self):
        for value in (True, False, 1.5, "1.5", "00:05", -1, 500, float("nan")):
            with self.subTest(value=value):
                self.assertEqual(self.validate([dict(PICK, start_id=value)]), [])

    def test_does_not_cut_long_story_or_pad_tiny_moment(self):
        self.assertEqual(self.validate([dict(PICK, end_id=20)]), [])
        self.assertEqual(self.validate([dict(PICK, start_id=4, end_id=4)]), [])

    def test_video_end_is_clamped_before_length_check(self):
        self.assertEqual(self.validate([PICK], duration=28), [])
        rows = self.validate([PICK], duration=34.95)
        self.assertEqual(rows[0]["end"], 34.95)
        self.assertEqual(self.validate([PICK], duration=34.95, lo=1, hi=7, minimum=30), [])
        self.assertEqual(self.validate([dict(PICK, peak_id=6)], duration=30), [])

    def test_repair_stays_inside_section(self):
        self.assertEqual(self.validate([dict(PICK, end_id=4)], lo=1, hi=5), [])

    def test_repeated_invalid_section_does_not_stop_later_sections(self):
        bad = {"clips": [dict(PICK, end_id=500)]}
        good = {"clips": [dict(PICK, start_id=15, end_id=20, peak_id=18)]}
        rows, calls, report = self.select([bad, bad, good], [(0, 15), (15, 30)])
        self.assertEqual(calls, 3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start"], 75)
        self.assertEqual(len(report), 3)

    def test_partial_success_survives_invalid_correction(self):
        bad = dict(PICK, end_id=500)
        rows, calls, _ = self.select([{"clips": [PICK, bad]}, {"clips": [bad]}])
        self.assertEqual(calls, 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start"], 5)

    def test_missing_clips_list_is_corrected(self):
        rows, calls, _ = self.select([{"wrong": []}, {"clips": [PICK]}])
        self.assertEqual((len(rows), calls), (1, 2))

    def test_valid_empty_selection_is_not_retried(self):
        rows, calls, _ = self.select([{"clips": []}])
        self.assertEqual((rows, calls), ([], 1))

    def test_repaired_peak_still_respects_live_gate(self):
        response = {"clips": [dict(PICK, end_id=4)]}
        rows = deepseek.validate_picks(response, SEGMENTS, 0, 30, 150, 25, 55, (30, 60))
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
