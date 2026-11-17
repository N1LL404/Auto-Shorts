from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import threading

import whisper_bundle
from model_settings import ModelSettings


class BundleTests(unittest.TestCase):
    def make_model(self, root):
        folder = root / "whisper-models" / "base.en"
        folder.mkdir(parents=True)
        for name in whisper_bundle.REQUIRED_FILES:
            (folder / name).write_bytes(b"fixture")
        return folder

    def test_complete_bundle_is_loaded_locally_and_reported_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = self.make_model(root)
            constructor = Mock()
            with patch.object(whisper_bundle, "ROOT", root), patch.dict(
                    "sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=constructor)}):
                whisper_bundle.load_whisper("base.en")
                constructor.assert_called_once_with(str(folder), device="cpu",
                                                     compute_type="int8", local_files_only=True)
                settings = ModelSettings(root, threading.RLock())
                self.assertIn("base.en", settings.public()["ready"])
                self.assertIn("base.en", settings.public()["bundled"])

    def test_missing_packaged_model_does_not_download(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(whisper_bundle, "ROOT", Path(directory)):
            constructor = Mock()
            with patch.object(whisper_bundle.sys, "frozen", True, create=True), patch.dict(
                    "sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=constructor)}):
                with self.assertRaisesRegex(ValueError, "Extract the entire app ZIP"):
                    whisper_bundle.load_whisper("base.en")
                constructor.assert_not_called()

    def test_optional_model_uses_existing_download_flow(self):
        constructor = Mock()
        with patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=constructor)}):
            whisper_bundle.load_whisper("small.en")
            constructor.assert_called_once_with("small.en", device="cpu", compute_type="int8")


if __name__ == "__main__":
    unittest.main()
