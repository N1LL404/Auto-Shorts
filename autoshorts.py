"""Local DrDonut stream highlight review and portrait export."""
import argparse
import array
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import html
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from urllib.parse import urlparse
import zipfile


EVENTS = {
    "Fight": r"\b(pvp|killed|kill him|fight|mace|popped|totem|one heart)\b",
    "Trap": r"\b(trap|trapped|escape|ambush|raid)\b",
    "Loot": r"\b(shulker|spawner|diamonds|auction|million|billion|loot)\b",
    "Reveal": r"\b(look at this|what is that|no way|watch this|there it is)\b",
}
REACTION = re.compile(r"\b(no way|oh my god|what the|let'?s go|bro what)\b", re.I)


@dataclass
class Candidate:
    start: float
    end: float
    peak: float
    score: float
    signals: list
    hook: str


def run(*args):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE).stdout


def probe(path):
    data = json.loads(run("ffprobe", "-v", "error", "-show_streams", "-show_format",
                          "-of", "json", str(path)))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if video is None:
        raise ValueError("The input has no video track.")
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("The source must have a positive duration.")
    return duration, video, any(s["codec_type"] == "audio" for s in data["streams"])


def audio_activity(path, duration, has_audio):
    if not has_audio:
        return [0.0] * math.ceil(duration)
    # Keep speech frequencies and use one RMS value per second.
    pcm = run("ffmpeg", "-v", "error", "-i", str(path), "-vn", "-af",
              "highpass=f=140,lowpass=f=3500", "-ac", "1", "-ar", "2000", "-f", "s16le", "-")
    samples = array.array("h", pcm)
    return [math.log1p(math.sqrt(sum(x*x for x in chunk) / len(chunk)))
            for i in range(0, len(samples), 2000) if (chunk := samples[i:i+2000])]


def gameplay_activity(path):
    # A central crop excludes the webcam, chat and most stream overlays.
    frames = run("ffmpeg", "-v", "error", "-threads", "2", "-i", str(path), "-an",
                 "-filter_threads", "1", "-vf",
                 "fps=4,crop=iw*0.52:ih*0.72:iw*0.24:ih*0.14,scale=48:32,format=gray",
                 "-threads", "1", "-f", "rawvideo", "-")
    size = 48 * 32
    previous = None
    seconds = []
    for i in range(0, len(frames), size):
        frame = frames[i:i+size]
        change = sum(abs(a-b) for a, b in zip(previous, frame)) / size if previous else 0
        second = i // size // 4
        if second == len(seconds):
            seconds.append([])
        seconds[second].append(change)
        previous = frame
    return [statistics.median(values) for values in seconds]


def normalize(values, count):
    if not values:
        return [0.0] * count
    ordered = sorted(values)
    baseline = ordered[len(values) // 2]
    spread = max(ordered[int((len(values)-1)*0.9)] - baseline, 0.15)
    return [max(0.0, min(2.0, (values[i] - baseline) / spread))
            if i < len(values) else 0.0 for i in range(count)]


def read_chat(path):
    if path is None:
        return Counter()
    chat = Counter()
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            if line.strip():
                try:
                    ts = float(json.loads(line)["seconds"])
                except (ValueError, TypeError, KeyError) as exc:
                    raise ValueError(f"Invalid chat timestamp on line {number} of {path}.") from exc
                if math.isfinite(ts) and ts >= 0:
                    chat[int(ts)] += 1
    return chat


@lru_cache(maxsize=1)
def whisper_model(model):
    try:
        from whisper_bundle import load_whisper
        return load_whisper(model)
    except ImportError as exc:
        raise ValueError("Install faster-whisper to use --whisper.") from exc


def transcribe(path, model):
    if not model:
        return []
    print("Transcribing speech and timing captions…", flush=True)
    segments, _ = whisper_model(model).transcribe(
        str(path), language="en", vad_filter=True, word_timestamps=True)
    return [{"start": s.start, "end": s.end, "text": s.text.strip(),
             "words": [{"start": w.start, "end": w.end, "text": w.word.strip()}
                       for w in (s.words or [])]} for s in segments]


def rank(path, duration, has_audio, segments, chat, limit, min_length, max_length, peak_gate=None):
    count = math.ceil(duration)
    audio = normalize(audio_activity(path, duration, has_audio), count)
    motion = normalize(gameplay_activity(path), count)
    # Only a small share of the score comes from chat volume.
    chat_counts = [sum(chat[t] for t in range(i-2, i+3)) for i in range(count)]
    chat_signal = normalize([math.log1p(n) for n in chat_counts], count)
    speech = {}
    events = {}
    for segment in segments:
        i = min(count - 1, max(0, int((segment["start"] + segment["end"]) / 2)))
        line = segment["text"]
        labels = [label for label, pattern in EVENTS.items() if re.search(pattern, line, re.I)]
        if labels:
            events.setdefault(i, set()).update(labels)
        speech[i] = max(speech.get(i, 0), .9 if REACTION.search(line) else .55 if labels else 0)

    scores = []
    for i in range(count):
        nearby = range(max(0, i-2), min(count, i+3))
        motion_context = sum(motion[t] for t in nearby) / 5
        payoff_context = min(1.0, max(.25, (duration - i) / 7))
        scores.append(payoff_context * (
            .42 * max(audio[t] for t in nearby) + .85 * motion_context
            + .31 * chat_signal[i] + max(speech.get(t, 0) for t in nearby)
            + .25 * min(audio[i], motion[i])
        ))
    candidates = []
    for peak in sorted(range(count), key=lambda i: (-scores[i], i)):
        if peak_gate and not peak_gate[0] <= peak < peak_gate[1]:
            continue
        if scores[peak] <= 0 and candidates:
            break
        if any(c.start - 5 <= peak <= c.end + 5 for c in candidates):
            continue
        # Start before the beat and retain the response. Extend through nearby action.
        before = min(13, max_length * .38)
        after = min(12, max_length * .32)
        start = max(0.0, peak - before)
        end = min(duration, max(start + min_length, peak + after))
        while end < min(duration, start + max_length - 1):
            window = scores[int(end):int(end)+4]
            if not window or max(window) < .55:
                break
            end = min(duration, start + max_length, end + 3)
        start = max(0.0, min(start, end - min_length))
        # Prefer complete phrases at the edges while respecting the length cap.
        for s in segments:
            if s["start"] < start < s["end"] and end - s["start"] <= max_length:
                start = s["start"]
            if s["start"] < end < s["end"] and s["end"] - start <= max_length:
                end = min(duration, s["end"])
        if any(max(0, min(c.end, end) - max(c.start, start)) > 4 for c in candidates):
            continue
        local = range(max(0, peak-3), min(count, peak+4))
        labels = sorted(set().union(*(events.get(i, set()) for i in local)))
        signals = [*labels]
        for signal, values in (("audio rise", audio), ("gameplay motion", motion), ("chat spike", chat_signal)):
            if max(values[t] for t in local) >= .45:
                signals.append(signal)
        candidates.append(Candidate(round(start, 3), round(end, 3), peak,
                                    round(scores[peak], 2), signals,
                                    "DID THAT JUST HAPPEN?" if "Reveal" in labels else ""))
        if len(candidates) >= limit:
            break
    return candidates


def ass_time(t):
    centis = round(max(0, t)*100)
    hours, rest = divmod(centis, 360000)
    minutes, rest = divmod(rest, 6000)
    seconds, sub = divmod(rest, 100)
    return f"{hours}:{minutes:02}:{seconds:02}.{sub:02}"


def ass_text(text):
    return str(text).replace("\\", "／").replace("{", "(").replace("}", ")").replace("\n", " ")


def make_overlay(candidate, segments, hook, captions):
    rows = ["""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,DejaVu Sans,53,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,5,42,42,0,1
Style: Caption,DejaVu Sans,48,&H00FFFFFF,&H0000EDFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,5,1,5,54,54,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""]
    def line(start, end, style, body):
        if end > start:
            rows.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{body}")
    length = candidate.end - candidate.start
    if hook:
        parts = re.split(r"(\*[^*]+\*)", hook.upper())
        body = "".join(
            r"{\c&H0000EDFF&}" + ass_text(text[1:-1]) + r"{\c&H00FFFFFF&}"
            if text.startswith("*") and text.endswith("*") else ass_text(text)
            for text in parts
        )
        line(0, length, "Hook", r"{\pos(540,504)}" + body)
    if captions:
        for segment in segments:
            words = segment["words"]
            for i in range(0, len(words), 4):
                batch = words[i:i+4]
                start = max(0, batch[0]["start"] - candidate.start)
                end = min(length, batch[-1]["end"] - candidate.start)
                body = " ".join(ass_text(w["text"].upper()) for w in batch)
                line(start, end, "Caption", r"{\pos(540,1600)}" + body)
    return "\n".join(rows) + "\n"


def rectangle(value):
    try:
        box = tuple(map(float, value.split(",")))
        if len(box) == 4 and all(math.isfinite(n) for n in box):
            x, y, w, h = box
            if min(x, y) >= 0 and min(w, h) >= .02 and x+w <= 1 and y+h <= 1:
                return box
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Use normalized x,y,width,height inside the source frame.")


def layout(facecam, center):
    x, y, w, h = facecam
    # Fit each pane by cropping to its aspect ratio before scaling.
    face = (f"crop='min(iw*{w},ih*{h}*1080/504)':'min(ih*{h},iw*{w}*504/1080)':"
            f"'iw*{x}+(iw*{w}-ow)/2':'ih*{y}+(ih*{h}-oh)/2',scale=1080:504,setsar=1")
    game = (f"crop='min(iw,ih*1080/1416)':'min(ih,iw*1416/1080)':"
            f"'max(0,min(iw-ow,iw*{center}-ow/2))':'ih-oh',scale=1080:1416,setsar=1")
    return f"[0:v]split=2[a][b];[a]{face}[face];[b]{game}[game];[face][game]vstack"


def render(path, candidate, dest, args, segments, has_audio):
    hook = args.hook if args.hook is not None else candidate.hook
    with tempfile.TemporaryDirectory() as temp:
        overlay = Path(temp) / "overlay.ass"
        overlay.write_text(make_overlay(candidate, segments, hook, args.captions), encoding="utf-8")
        graph = layout(args.facecam, args.center) + f",ass=filename='{overlay.as_posix()}'[out]"
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-threads", "2", "-ss", str(candidate.start), "-i", str(path), "-t",
                   str(candidate.end - candidate.start), "-filter_complex_threads", "2",
                   "-filter_complex", graph, "-map", "[out]", "-map", "0:a:0?",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "3",
                   "-pix_fmt", "yuv420p", "-r", str(args.fps)]
        if has_audio:
            command += ["-af", "acompressor=threshold=0.125:ratio=2:attack=20:release=180,alimiter=limit=0.95:level=0",
                        "-c:a", "aac", "-b:a", "160k"]
        temp_output = dest.with_suffix(".partial.mp4")
        try:
            subprocess.run([*command, "-movflags", "+faststart", str(temp_output)], check=True)
            temp_output.replace(dest)
        finally:
            temp_output.unlink(missing_ok=True)
    return re.sub(r"\*([^*]+)\*", r"\1", hook)


def publish_kit(output, candidate, index, segments):
    lines = [s for s in segments if s["start"] >= candidate.start and s["end"] <= candidate.end
             and 8 <= len(s["text"]) <= 90 and len(s["text"].split()) >= 3]
    near = [s for s in lines if abs(s["start"] - candidate.peak) <= 10]
    line = min(near, key=lambda s: abs(s["start"] - candidate.peak))["text"] if near else ""
    title = f"DrDonut: {line}" if line else "DrDonut on Donut SMP"
    lead = f'“{line}”\n\n' if line else ""
    caption = f"{lead}DrDonut on Donut SMP. #DrDonut #DonutSMP #Minecraft #Shorts"
    name = f"clip-{index:02}"
    cover = output / f"{name}.jpg"
    kit = output / f"{name}.zip"
    timestamp = max(0, min(candidate.end - candidate.start - .15, candidate.peak - candidate.start))
    run("ffmpeg", "-v", "error", "-y", "-ss", str(timestamp), "-i", str(output / f"{name}.mp4"),
        "-frames:v", "1", "-vf", "scale=540:960", "-threads", "1", str(cover))
    temp = kit.with_suffix(".partial.zip")
    try:
        with zipfile.ZipFile(temp, "w") as archive:
            archive.write(output / f"{name}.mp4", "short.mp4")
            archive.write(cover, "cover.jpg")
            archive.writestr("post.txt", f"{title}\n\n{caption}\n")
        temp.replace(kit)
    finally:
        temp.unlink(missing_ok=True)
    return {"title": title, "caption": caption, "cover": cover.name, "kit": kit.name}


def auto_headline(segments, candidate):
    nearby = [s for s in segments if s["start"] >= candidate.start and s["end"] <= candidate.end
              and abs(s["start"] - candidate.peak) <= 12]
    phrases = [re.sub(r"[^\w '?!.+-]", "", s["text"]).strip() for s in nearby]
    short = [p for p in phrases if 8 <= len(p) <= 29 and len(p.split()) >= 3]
    if short:
        return next((p for p in short if REACTION.search(p)), short[0])
    return candidate.hook or "DRDONUT ON *DONUT SMP*"


def review(output, records):
    cards = []
    for row in records:
        detail = html.escape(", ".join(row["signals"]) or "manual selection")
        title = html.escape(row["hook"] or f"Candidate {row['index']}")
        file = html.escape(row["file"], quote=True)
        cards.append(f'<article><h2>{title}</h2><p>{row["start"]:.1f}s–{row["end"]:.1f}s · '
                     f'{detail} · score {row["score"]:.2f}</p>'
                     f'<video controls preload="metadata" src="{file}"></video>'
                     f'<p><a href="{file}" download>Download MP4</a></p></article>')
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Auto-Shorts review</title>
<style>body{background:#101318;color:#f4f5f7;font:16px system-ui;margin:32px auto;padding:0 20px;max-width:1250px}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));gap:20px}
article{background:#1b2029;border-radius:14px;padding:16px}video{width:100%;max-height:65vh;background:#000}
a{color:#a4f6ad}p{color:#c9d0dc}</style><h1>Auto-Shorts review</h1><main>"""
    (output / "review.html").write_text(page + "".join(cards) + "</main></html>", encoding="utf-8")
    pending = output / ".clips.json"
    pending.write_text(json.dumps(records, indent=2), encoding="utf-8")
    pending.replace(output / "clips.json")


def process(path, args, output, offset=0, peak_gate=None):
    output.mkdir(parents=True, exist_ok=True)
    duration, _, has_audio = probe(path)
    segments = transcribe(path, args.whisper) if has_audio else []
    (output / "transcript.json").write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
    if args.start is not None:
        end = min(duration, args.end)
        if not math.isfinite(args.end) or not 0 <= args.start < end:
            raise ValueError("Manual cut falls outside the source.")
        candidates = [Candidate(args.start, end, args.start, 0, [], "")]
    elif getattr(args, "selector", "local") == "deepseek":
        from deepseek import load_settings, select_clips
        picks = select_clips(segments, duration, load_settings(args.settings_file), args.clips,
                             args.min_length, args.max_length, output, peak_gate)
        candidates = [Candidate(**row) for row in picks]
    else:
        print("Finding highlights…", flush=True)
        chat = Counter({t-int(offset): n for t, n in read_chat(args.chat).items()})
        candidates = rank(path, duration, has_audio, segments, chat, args.clips,
                          args.min_length, args.max_length, peak_gate)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for candidate in candidates:
        index = len(records) + 1
        dest = output / f"clip-{index:02}.mp4"
        if (getattr(args, "publish_kit", False) and args.hook is None
                and getattr(args, "selector", "local") != "deepseek"):
            candidate.hook = auto_headline(segments, candidate)
        print(f"Rendering clip {index}…", flush=True)
        hook = render(path, candidate, dest, args, segments, has_audio)
        row = vars(candidate).copy()
        row.update(index=index, file=dest.name, hook=hook)
        if getattr(args, "publish_kit", False):
            row.update(publish_kit(output, candidate, index, segments))
        for key in ("start", "end", "peak"):
            row[key] = round(row[key] + offset, 3)
        records.append(row)
    review(output, records)
    print(f"{len(records)} clip(s) → {output / 'review.html'}", flush=True)
    return records


def stream_url(url):
    host = urlparse(url).hostname
    if urlparse(url).scheme != "https" or host not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
        "twitch.tv", "www.twitch.tv", "m.twitch.tv",
    }:
        raise ValueError("Use a Twitch or YouTube HTTPS link.")
    if not shutil.which("yt-dlp"):
        raise ValueError("Install yt-dlp to use Twitch or YouTube links.")
    return url


def yt_dlp_command():
    return ["yt-dlp", "--js-runtimes", "node"] if shutil.which("node") else ["yt-dlp"]


def capture_live(args):
    url = stream_url(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Choose an empty --output directory for a live session.")
    # CSV entries are flushed after a segment is closed, including the final one.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        manifest = root / "capture.csv"
        fetch = subprocess.Popen([*yt_dlp_command(), "--no-playlist", "--socket-timeout", "30",
                                  "-f", "b[height<=1080][protocol^=m3u8]/b[height<=1080]/b",
                                  "-o", "-", "--", url], stdout=subprocess.PIPE)
        try:
            capture = subprocess.Popen([
                "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin", "-i", "pipe:0",
                "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-f", "segment",
                "-segment_time", str(args.segment_seconds), "-reset_timestamps", "1",
                "-segment_list", str(manifest), "-segment_list_type", "csv",
                str(root / "part-%06d.ts")], stdin=fetch.stdout)
            fetch.stdout.close()
            try:
                live_windows(args, root, manifest, capture)
                if capture.returncode:
                    raise ValueError("FFmpeg lost the live feed. Check its output above.")
                if fetch.wait(timeout=10):
                    raise ValueError("yt-dlp ended with an error. Check its output above.")
            finally:
                if capture.poll() is None:
                    capture.terminate()
                    capture.wait()
        finally:
            if fetch.poll() is None:
                fetch.terminate()
                try:
                    fetch.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    fetch.kill()
                    fetch.wait()


def live_windows(args, root, manifest, capture):
    import csv

    first = 0
    offset = 0.0
    all_records = []
    print("Capturing live stream. The first review includes context from three segments.", flush=True)
    try:
        while True:
            stopped = capture.poll() is not None
            rows = list(csv.reader(manifest.read_text().splitlines())) if manifest.exists() else []
            rows = [r for r in rows if len(r) == 3]
            if len(rows)-first >= 3 or (stopped and first < len(rows)):
                window = rows[first:first+3]
                lengths = [max(0, float(r[2])-float(r[1])) for r in window]
                playlist = root / "window.ffconcat"
                playlist.write_text("ffconcat version 1.0\n" + "".join(
                    f"file {Path(r[0]).name}\nduration {length:.6f}\n"
                    for r, length in zip(window, lengths)), encoding="utf-8")
                source = root / "window.mp4"
                run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-i", str(playlist),
                    "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", str(source))
                left = 0 if first == 0 else lengths[0]
                final_window = stopped and len(rows)-first <= 3
                right = math.inf if final_window else sum(lengths[:2])
                records = process(source, args, args.output / f"window-{first:04}", offset, (left, right))
                for row in records:
                    if any(max(0, min(r["end"], row["end"]) - max(r["start"], row["start"])) > 5
                           for r in all_records[-12:]):
                        continue
                    row["index"] = len(all_records) + 1
                    for key in ("file", "cover", "kit"):
                        if key in row:
                            row[key] = f"window-{first:04}/{row[key]}"
                    all_records.append(row)
                review(args.output, all_records)
                if final_window:
                    break
                print("Watching for the next live moment…", flush=True)
                offset += lengths[0]
                (root / Path(window[0][0]).name).unlink()
                first += 1
            elif stopped:
                if first == 0:
                    raise ValueError("The stream ended before any video was captured.")
                break
            else:
                time.sleep(2)
    except KeyboardInterrupt:
        print("\nCapture stopped. Completed review files are available.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Local recording, Twitch link, or YouTube link")
    parser.add_argument("--live", action="store_true", help="Review clips progressively while capturing")
    parser.add_argument("--output", type=Path, default=Path("shorts-output"))
    parser.add_argument("--clips", type=int, default=3)
    parser.add_argument("--min-length", type=float, default=25)
    parser.add_argument("--max-length", type=float, default=55)
    parser.add_argument("--facecam", type=rectangle, default=(0, 0, .24, .241))
    parser.add_argument("--center", type=float, default=.5, help="Horizontal gameplay center, 0–1")
    parser.add_argument("--fps", type=int, choices=(30, 60), default=60)
    parser.add_argument("--hook", help="Headline to place at the facecam/gameplay seam")
    parser.add_argument("--whisper", metavar="MODEL", help="Optional faster-whisper model, e.g. base.en")
    parser.add_argument("--captions", action="store_true", help="Burn in captions from --whisper")
    parser.add_argument("--selector", choices=("local", "deepseek"), default="local")
    parser.add_argument("--settings-file", type=Path)
    parser.add_argument("--publish-kit", action="store_true", help="Write a cover, post copy and ZIP for each clip")
    parser.add_argument("--chat", type=Path, help="JSONL with message timestamps in source seconds")
    parser.add_argument("--start", type=float, help="Manual cut start in seconds")
    parser.add_argument("--end", type=float, help="Manual cut end in seconds")
    parser.add_argument("--segment-seconds", type=int, default=30, help="Live capture segment target")
    args = parser.parse_args()
    if (not math.isfinite(args.max_length)
            or not 0 < args.min_length <= args.max_length or args.clips < 1):
        parser.error("Set a positive clip count and valid minimum/maximum lengths.")
    if not 0 <= args.center <= 1 or args.segment_seconds < 10:
        parser.error("Set gameplay center to 0–1 and segment length to at least 10 seconds.")
    if (args.start is None) != (args.end is None) or (args.live and args.start is not None):
        parser.error("Use --start and --end together on a recording.")
    if args.selector == "deepseek" and not args.whisper:
        parser.error("DeepSeek selection requires --whisper MODEL.")
    if args.captions and not args.whisper:
        parser.error("--captions requires --whisper MODEL.")
    for program in ("ffmpeg", "ffprobe"):
        if not shutil.which(program):
            parser.error(f"Install {program} and put it on PATH.")
    try:
        if args.live:
            capture_live(args)
        elif args.source.startswith(("https://", "http://")):
            url = stream_url(args.source)
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "source.mp4"
                subprocess.run([*yt_dlp_command(), "--no-playlist", "--no-progress",
                                "--socket-timeout", "30",
                                "--merge-output-format", "mp4", "--remux-video", "mp4",
                                "-o", str(source.with_suffix(".%(ext)s")), "--", url], check=True)
                process(source, args, args.output)
        else:
            process(Path(args.source), args, args.output)
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Auto-Shorts: {exc}\n")


if __name__ == "__main__":
    main()
