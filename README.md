# Auto-Shorts · DrDonut

Find candidate highlights in DrDonut's Minecraft streams and render them as vertical Shorts. The default layout keeps the facecam above the action, with room for the hearts, armor, and hotbar. Clips open in a local review page where you can watch and download each export.

## Get started

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
