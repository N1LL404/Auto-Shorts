# Auto-Shorts · DrDonut

Find candidate highlights in DrDonut's Minecraft streams and render them as vertical Shorts. The default layout keeps the facecam above the action, with room for the hearts, armor, and hotbar. Clips open in a local review page where you can watch and download each export.

## Desktop app (Windows)

Run **Build Windows desktop app** from
[GitHub Actions](https://github.com/N1LL404/Auto-Shorts/actions/workflows/desktop-windows.yml).
When it completes, download the **AutoShorts-Windows-x64** artifact and extract the ZIPs,
and double-click **AutoShorts.exe** inside the AutoShorts folder.

The package includes Python, FFmpeg, FFprobe, yt-dlp, Node and transcription
dependencies, plus the **Whisper base.en model weights**. Enter your DeepSeek
API key, choose a video file or paste a URL, then click **Generate Shorts**.
The included English model transcribes locally without a first-run download.
Larger models remain optional downloads in Settings. Clips open in your default video player.
Bundling base.en adds approximately 148 MB before ZIP compression.

Settings and output are stored under `%LOCALAPPDATA%/AutoShorts`. Keep the
executable and its `_internal` folder together. The Windows build is unsigned.

To run the desktop interface from Python source, install the requirements and
run `python desktop.py`. The web interface remains available with `python studio.py`.
Developers can build Windows packages with the **Build Windows desktop app**
GitHub workflow, which verifies the bundled tools and launches the packaged GUI
before saving a downloadable build artifact. Builds are started manually.

## DeepSeek + local Whisper

The studio now uses DeepSeek to read the transcript and select complete stories.
Open **AI Settings** before the first run:

1. Enter your DeepSeek API key and click **Save settings**.
2. Click **Load DeepSeek models**, choose a model available on your account, and save.
3. Click **Test connection** to verify generation. This makes a small billed API call.
4. In the desktop app, **base.en** is bundled and ready. For another model, use **Prepare selected model**. In the web interface, use **Download Whisper**.
5. Paste your YouTube or Twitch link and click **Generate Shorts**.

For completed videos, the app downloads the full recording, transcribes it with
word timestamps, analyzes every transcript section with DeepSeek, removes
overlapping candidates, and renders the highest-scoring clips. For active streams,
it performs the same steps on rolling windows as footage arrives.

The DrDonut editing instructions are in
[prompts/drdonut-editor.md](prompts/drdonut-editor.md). They tell DeepSeek to find
a setup, payoff and reaction, prefer standalone stories, and preserve sentence
boundaries. Returned segment IDs are checked against the actual transcript.
DeepSeek-selected hooks are retained in the rendered video. Empty selections
are allowed when a transcript has no strong moments. API failures surface as
errors and do not silently switch to motion-based selection.

Whisper runs locally. Transcript text is sent to DeepSeek for analysis.
Your API key is saved in the local data directory with restricted file permissions
and is never returned to the browser. Blank key input preserves the saved key.
Use **Remove key** to delete it. Keep this local data directory private.
DeepSeek charges your account for analysis. Whisper does not require an API key.
Only optional model downloads and source installations need Hugging Face access.
The packaged base.en model is loaded directly from the app folder.

## Paste a URL in Studio

Run the studio on your computer, open [localhost:8070](http://localhost:8070),
paste a public Twitch or YouTube stream link, or choose **Upload video** and select a downloaded recording. Click **Generate Shorts**. Uploads show progress and use the same saved Whisper and DeepSeek settings.
The studio detects whether the link is live or recorded. It starts capturing
a live broadcast from when you submit it and adds clips as they finish.
For a completed recording it processes the video as a batch.

Install Python 3.11+, FFmpeg/FFprobe with libass and libx264,
DejaVu Sans, and Node.js 24+ or a supported Deno runtime for YouTube extraction:

```bash
python -m pip install -r requirements.txt
python studio.py
```

In source installations, the first job downloads the selected model if it has not been prepared. The desktop package includes base.en. Each
clip comes with a video preview, an MP4, a cover, and a ZIP with the video
and post copy. Use **Stop job** to end a live capture. Finished exports stay
available when you restart the studio. Your saved DeepSeek API key is used for analysis. The studio
runs locally and requires network access to read the stream and download
the model. If extraction fails, open **Activity details** for yt-dlp's
message. Private, restricted, or upcoming streams may be unavailable.

## Command line

Install Python 3.11+, DejaVu Sans, and FFmpeg (with FFprobe, libass and libx264). For stream URLs, install yt-dlp. For transcript scoring and burned-in captions, install faster-whisper and select a model. The model downloads at first use.

```bash
python -m pip install -r requirements.txt
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

## Verification

Run `PYTHONPATH=. python -m unittest discover -s tests -v` to check transcript
boundary validation, chunk coverage, duplicate removal, API error handling,
credential persistence and the Settings HTTP endpoints. Tests use simulated
DeepSeek responses and do not spend API credits.

Real DeepSeek calls, Whisper download and transcription, and captioned FFmpeg
rendering have now been tested. See [test results](docs/test-results.md) for
verified behavior, fixes and remaining live-source limitations.

## Reference implementation reviewed

- AutoClip’s [AI model settings](https://github.com/zhouxiaoka/autoclip/blob/main/docs/AI_MODEL_CONFIGURATION.md)
  define provider credentials, connection testing, model discovery and local model preparation.
- Its [timeline extraction](https://github.com/zhouxiaoka/autoclip/blob/main/backend/pipeline/step2_timeline.py)
  and [scoring](https://github.com/zhouxiaoka/autoclip/blob/main/backend/pipeline/step3_scoring.py)
  informed transcript chunking, checked timeline selection and ranking.
- The official [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
  defines the JSON response format. The editable default is `deepseek-flash`;
  use the account model list in Settings to choose another available model.

## Whisper preparation troubleshooting

If you see “Whisper preparation failed”, update to this version and retry
**AI Settings → Download Whisper**. The status now identifies missing packages,
SOCKS proxy requirements, certificate problems, disk space and permissions.

Stop the studio, update the source and install the compatible dependencies:

```bash
git pull
python -m pip install --upgrade -r requirements.txt
python studio.py
```

Open AI Settings and retry the download. For a SOCKS proxy, also install
`socksio`. Hugging Face must be reachable from the computer running the studio.

Uploaded videos are streamed to the studio data directory and retained with their
session. Available disk space is checked before accepting an upload. Interrupted
uploads are removed and can be retried. Uploads do not require yt-dlp.
