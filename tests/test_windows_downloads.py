"""Download failure regression tests; no network or Windows executables needed."""
import hashlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from http.client import IncompleteRead

spec = importlib.util.spec_from_file_location("windows_tools",
    Path(__file__).resolve().parents[1] / "packaging" / "fetch_windows_tools.py")
downloads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloads)


class DownloadTests(unittest.TestCase):
    def test_503_then_success(self):
        error = HTTPError("https://example.test", 503, "Unavailable", {}, None)
        with patch.object(downloads.urllib.request, "urlopen",
                side_effect=[error, io.BytesIO(b"checksum")]) as request, patch.object(downloads.time, "sleep") as sleep:
            self.assertEqual(downloads.get("https://example.test"), b"checksum")
            self.assertEqual(request.call_count, 2)
            sleep.assert_called_once_with(2)

    def test_persistent_outage_has_bounded_retries(self):
        with patch.object(downloads.urllib.request, "urlopen",
                side_effect=URLError("offline")) as request, patch.object(downloads.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "after 5 attempts"):
                downloads.get("https://example.test")
            self.assertEqual(request.call_count, 5)
            self.assertEqual(sleep.call_count, 4)

    def test_permanent_error_does_not_retry(self):
        error = HTTPError("https://example.test", 404, "Not found", {}, None)
        with patch.object(downloads.urllib.request, "urlopen", side_effect=error), patch.object(downloads.time, "sleep") as sleep:
            with self.assertRaises(HTTPError):
                downloads.get("https://example.test")
            sleep.assert_not_called()

    def test_interrupted_transfer_restarts_download(self):
        with patch.object(downloads.urllib.request, "urlopen",
                side_effect=[IncompleteRead(b"partial"), io.BytesIO(b"complete")]), patch.object(downloads.time, "sleep"):
            self.assertEqual(downloads.get("https://example.test"), b"complete")

    def test_checksum_is_still_enforced(self):
        with patch.object(downloads, "get", return_value=b"tampered"):
            with self.assertRaisesRegex(RuntimeError, "Checksum mismatch"):
                downloads.verified("https://example.test", hashlib.sha256(b"original").hexdigest())


if __name__ == "__main__":
    unittest.main()
