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

The environment needed an additional SOCKS proxy dependency and system certificate configuration for external downloads. Those environment-specific changes are not part of the application. Browser visual testing and Docker build were unavailable here.

Credentials, source videos and private transcripts are excluded from the repository. Model-generated selections and transcriptions still need editorial review for content accuracy.

## Downloaded video upload and preparation diagnostics

- Streamed the supplied recording through the actual HTTP upload endpoint and ran the background worker with real Whisper and DeepSeek. The job completed successfully. DeepSeek again returned no highlights for the stream/audio-check conversation.
- Tested local source routing, normalized filenames, concurrent-job blocking, unsupported file rejection, and a specific Whisper proxy-dependency error message.
- Regression suite: 14 tests passed, with the optional FFmpeg integration test skipped in this run because real media rendering had already been verified above.
- Browser visual upload testing remains unverified in this environment.
