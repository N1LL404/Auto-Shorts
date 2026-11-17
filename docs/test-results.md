# Validation — 17 November 2026

## Real services and media

- Installed faster-whisper 1.2.1 and downloaded the actual base.en model.
- Ran Settings model preparation successfully.
- Transcribed the supplied 59.73-second recording into 10 segments and 95 word timestamps.
- Connected to the official DeepSeek API with a user-provided temporary credential. Model discovery and the small generation connection test succeeded.
- Sent the actual recording transcript to DeepSeek. It returned no candidates for the stream setup / audio-check conversation.
- Transcribed reference 06 and sent its actual transcript to DeepSeek. The initial duration selection failed validation. One automatic correction produced a valid 12.37–39.84-second interval, lasting 27.47 seconds, with the hook “WAIT — DID THE TRAP WORK?”.
- Separately rendered a manual 25-second excerpt of the supplied recording using real Whisper captions. FFprobe confirmed 1080×1920 H.264 video, AAC audio and 25-second duration. Inspected a rendered frame to confirm caption, facecam and HUD placement.
- Generated MP4, cover and post ZIP using FFmpeg.
- Twitch metadata lookup reached the service and reported that DrDonut was offline. Actual live capture and full YouTube URL download remain unverified in this test.

## Regression suite

All 12 tests passed, including the optional real-video FFmpeg test. Coverage includes credential persistence without returning keys to the browser, HTTP settings, provider errors and retries, malformed response handling, transcript coverage, verified segment boundaries, duplicate removal, automatic boundary correction, silent live windows, and media/package output.

Run:

```bash
PYTHONPATH=. AUTO_SHORTS_TEST_VIDEO=/path/to/recording.mp4 python -m unittest discover -s tests -v
node --check web/studio.js
```

The regression suite simulates provider and transcription responses. The real-service checks above were separate runs.

## Fixes prompted by testing

- Pin PyAV to 18.1.0 with faster-whisper 1.2.1. PyAV 19 removed the metadata_errors argument used by this faster-whisper version.
- Retry a fully invalid clip selection once with explicit correction instructions.
- Continue past silent windows in a live stream without invoking DeepSeek.
- Show readable errors for malformed completion responses and model lists.

The environment needed an additional SOCKS proxy dependency and system certificate configuration for external downloads. Those environment-specific changes are not part of the application. Browser visual testing was unavailable here.

Credentials, source videos and private transcripts are excluded from the repository. Model-generated selections and transcriptions still need editorial review for content accuracy.

## Downloaded video upload and preparation diagnostics

- Streamed the supplied recording through the actual HTTP upload endpoint and ran the background worker with real Whisper and DeepSeek. The job completed successfully. DeepSeek again returned no highlights for the stream/audio-check conversation.
- Tested local source routing, normalized filenames, concurrent-job blocking, unsupported file rejection, and a specific Whisper proxy-dependency error message.
- Regression suite: 14 tests passed, with the optional FFmpeg integration test skipped in this run because real media rendering had already been verified above.
- Browser visual upload testing remains unverified in this environment.

## Bundled Whisper base.en

The Windows packaging configuration now includes the pinned base.en model weights,
tokenizer, vocabulary and configuration. Files are checksum-verified before
packaging. The packaged self-test loads the model with local-only access and
runs transcription on a short silent sample.

A separate real test copied the model into an app-style model directory, used an
empty Hugging Face cache, enabled offline mode, and made the model download
function raise if called. The supplied recording transcribed successfully into
10 segments and 95 timestamped words. No model download was attempted.

Regression suite: 17 tests passed and the optional real-video rendering test was
skipped. The Windows executable itself still requires the manual Windows build.

## DeepSeek boundary recovery

The selector now accepts exact integer ID representations, calculates duration
from transcript timestamps after clamping small end-of-video rounding errors,
and can extend a slightly short selection by up to five seconds of nearby
speech. It preserves the selected story and peak; it does not guess unknown
IDs, truncate overlong stories, or pad very short moments.

Rejected selections receive one correction request with specific validation
errors. Valid selections survive mixed responses and failed boundary
corrections. Unrecoverable selections are skipped so later transcript sections
can still produce clips. Per-section reasons are written to
selection-diagnostics.json without API keys or transcript text.

Regression checks cover numeric representations, fractional/unknown IDs,
short-clip recovery, source and section limits, live peak gates, mixed valid
and invalid responses, empty selections, and continuation after repeated
invalid boundaries. These use deterministic DeepSeek responses; they do not
reproduce the user's unavailable failing API response.

All 29 tests passed, including real FFmpeg export of a generated test video to
a 30-second 1080x1920 MP4 with audio, captions, cover and publishing ZIP.
Transcription and DeepSeek responses were fixtures in that rendering test.
The Windows executable was not rebuilt or tested in this environment.

