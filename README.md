# Auto-Shorts · DrDonut

Find candidate highlights in DrDonut's Minecraft streams and render them as vertical Shorts. The default layout keeps the facecam above the action, with room for the hearts, armor, and hotbar. Clips open in a local review page where you can watch and download each export.

## Paste a URL in Studio

Run the studio on your computer, open [localhost:8070](http://localhost:8070),
paste a public Twitch or YouTube stream link, and click **Generate Shorts**.
The studio detects whether the link is live or recorded. It starts capturing
a live broadcast from when you submit it and adds clips as they finish.
For a completed recording it processes the video as a batch.

With Docker and Compose installed:

```bash
docker compose up --build
```

For a native install, use Python 3.11+, FFmpeg/FFprobe with libass and libx264,
DejaVu Sans, and Node.js 24+ or a supported Deno runtime for YouTube extraction:

```bash
python -m pip install -r requirements.txt
python studio.py
```

The first transcribed job downloads the local English Whisper model. Each
clip comes with a video preview, an MP4, a cover, and a ZIP with the video
and post copy. Use **Stop job** to end a live capture. Finished exports stay
available when you restart the studio. No AI API key is needed. The studio
runs locally and requires network access to read the stream and download
the model. If extraction fails, open **Activity details** for yt-dlp's
message. Private, restricted, or upcoming streams may be unavailable.

## Command line

Install Python 3.10+, DejaVu Sans, and FFmpeg (with FFprobe, libass and libx264). For stream URLs, install yt-dlp. For transcript scoring and burned-in captions, install faster-whisper and select a model. The model downloads at first use.

```bash
python -m pip install -U yt-dlp faster-whisper
python autoshorts.py "stream-recording.mp4" --output shorts-output
```

Open `shorts-output/review.html`. The associated `clips.json` records source timestamps, scoring signals, and export filenames. Scores rank candidates within a run.

A completed Twitch VOD or YouTube video URL can take the place of the local file. Add `--live` on an active public stream to capture and process it progressively:

```bash
python autoshorts.py "https://www.twitch.tv/drdonut" --live --output live-session
```

A live run starts a rolling capture, waits for three approximately 30-second segments, then processes overlapping windows. The top-level review lists candidates across the session. Refresh the page for new clips. A stream must have a format with audio and video together that yt-dlp can pipe. Segment boundaries depend on source keyframes. Ctrl+C stops the capture and keeps finished exports. Run this on a computer that can stay online while the stream is live.

## Tune a clip

```bash
python autoshorts.py "stream-recording.mp4" --start 2 --end 34 \
  --hook "WHAT IS THAT?" --whisper base.en --captions --output selected
```

- `--start` and `--end` select a precise source range. Without them, the ranker favors sustained central gameplay motion, audio peaks, and available transcript and chat cues. It looks for PvP, traps, loot and reactions in speech and leaves room around the peak for context.
- `--hook` puts your editorial headline on the facecam seam. Surround a word with asterisks, as in `WHAT IS *THAT*?`, to highlight it in yellow. An automatic headline is available for transcript-detected reveals. With `--whisper base.en --captions`, spoken words appear in short uppercase groups above the HUD.
- `--chat chat.jsonl` accepts rows such as `{"seconds":12.34}`. Supply a synchronized log from the beginning of the capture or recording. Live Twitch and YouTube chat collection is a separate integration.
- `--facecam 0,0,0.24,0.241` sets the normalized source rectangle. Adjust it if an overlay moves or a recording includes browser borders. `--center` sets the horizontal gameplay crop center and defaults to 0.5.
- Choose `--clips`, `--min-length`, and `--max-length` to tune the review batch. Exports are 1080×1920 at 60 fps by default. Use `--fps 30` to keep 30 fps footage at its original cadence.

[Read the reference analysis and validation notes](docs/reference-analysis.md).

[AutoClip](https://github.com/zhouxiaoka/autoclip) informed the analyze, review, export flow. [OpenShorts](https://github.com/mutonby/openshorts) informed the stacked presentation and seam placement. Auto-Shorts implements the DrDonut layout and scoring pipeline locally.
