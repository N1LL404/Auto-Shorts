"""DeepSeek transcript selection with verified transcript boundaries."""
import json
import math
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
WHISPER_MODELS = ("tiny.en", "base.en", "small.en", "medium.en", "large-v3")
PROMPT = Path(__file__).parent / "prompts" / "drdonut-editor.md"


def api_request(key, route, payload=None):
    if not key:
        raise ValueError("Add your DeepSeek API key in Settings.")
    request = Request(API + route, data=json.dumps(payload).encode() if payload else None,
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=120) as response:
                return json.load(response)
        except HTTPError as exc:
            if (exc.code == 429 or exc.code >= 500) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            messages = {401: "DeepSeek rejected the API key.", 402: "DeepSeek balance is insufficient.",
                        429: "DeepSeek rate limit reached. Try again later."}
            raise ValueError(messages.get(exc.code, f"DeepSeek request failed (HTTP {exc.code}).")) from None
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise ValueError("Could not reach DeepSeek. Check your connection and try again.") from None
            time.sleep(2 ** attempt)
        except (ValueError, TypeError):
            raise ValueError("DeepSeek returned an unreadable response.") from None


def completion(key, model, system, user):
    result = api_request(key, "/chat/completions", {
        "model": model, "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
        "response_format": {"type": "json_object"}, "max_tokens": 4096,
        "thinking": {"type": "disabled"}, "stream": False,
    })
    try:
        choice = result["choices"][0]
        if not isinstance(choice, dict):
            raise ValueError()
        if choice.get("finish_reason") != "stop":
            raise ValueError()
        value = json.loads(choice["message"]["content"])
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError("DeepSeek returned incomplete or invalid JSON. Please retry.") from None


def load_settings(path):
    if not path or not Path(path).exists():
        return {"api_key": os.environ.get("DEEPSEEK_API_KEY", ""), "model": DEFAULT_MODEL,
                "whisper": "base.en"}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def transcript_chunks(segments, max_length, char_limit=36000):
    start = 0
    while start < len(segments):
        end, size = start, 0
        while end < len(segments):
            cost = len(segments[end]["text"]) + 100
            if size + cost > char_limit and end > start:
                break
            size += cost
            end += 1
        yield start, end
        if end == len(segments):
            break
        # Repeat sufficient context for stories crossing chunk boundaries.
        overlap = end - 1
        while overlap > start and segments[end-1]["end"] - segments[overlap]["start"] < max_length + 15:
            overlap -= 1
        start = max(start + 1, overlap)


def validate_picks(result, segments, lo, hi, duration, minimum, maximum, gate=None):
    clips = result.get("clips")
    if not isinstance(clips, list):
        raise ValueError("DeepSeek response did not contain a clips list.")
    valid = []
    for row in clips:
        if not isinstance(row, dict):
            continue
        ids = [row.get(field) for field in ("start_id", "end_id", "peak_id")]
        if any(type(i) is not int for i in ids):
            continue
        first, last, peak = ids
        if not lo <= first <= peak <= last < hi:
            continue
        start, end = float(segments[first]["start"]), float(segments[last]["end"])
        peak_time = float(segments[peak]["start"])
        score = row.get("score")
        if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 100:
            continue
        if not (0 <= start < end <= duration + .1 and minimum <= end-start <= maximum):
            continue
        if gate and not gate[0] <= peak_time < gate[1]:
            continue
        hook, reason = row.get("hook"), row.get("reason")
        if not isinstance(hook, str) or not isinstance(reason, str) or not hook.strip():
            continue
        valid.append(dict(start=start, end=min(duration, end), peak=peak_time, score=score,
                          hook=hook.strip()[:34], signals=["DeepSeek", reason.strip()[:400]]))
    return valid


def select_clips(segments, duration, settings, limit, minimum, maximum, output, gate=None):
    if not segments and gate is not None:
        (output / "selection.json").write_text("[]", encoding="utf-8")
        return []
    if not segments:
        raise ValueError("Whisper found no speech. DeepSeek needs a transcript to select clips.")
    candidates = []
    for number, (lo, hi) in enumerate(transcript_chunks(segments, maximum), start=1):
        print(f"DeepSeek is analyzing transcript section {number}…", flush=True)
        user = {"minimum_seconds": minimum, "maximum_seconds": maximum, "maximum_clips": limit,
                "segments": [{"id": i, "start": s["start"], "end": s["end"], "text": s["text"]}
                             for i, s in enumerate(segments[lo:hi], start=lo)]}
        response = completion(settings["api_key"], settings["model"], PROMPT.read_text(), user)
        parsed = validate_picks(response, segments, lo, hi, duration, minimum, maximum)
        if response.get("clips") and not parsed:
            print("DeepSeek is correcting clip boundaries…", flush=True)
            user["correction"] = {
                "previous_selection": response,
                "instruction": (
                    "Every previous clip failed validation. Recheck IDs and calculate "
                    "segments[end_id].end minus segments[start_id].start. "
                    "Return only clips inside the requested duration range with integer IDs, "
                    "start_id <= peak_id <= end_id, numeric score 0–100, hook and reason. "
                    "Return an empty clips list if no complete story fits."
                ),
            }
            response = completion(settings["api_key"], settings["model"], PROMPT.read_text(), user)
            parsed = validate_picks(response, segments, lo, hi, duration, minimum, maximum)
            if response.get("clips") and not parsed:
                raise ValueError("DeepSeek selected invalid clip boundaries after correction. Please retry.")
        if gate:
            parsed = [row for row in parsed if gate[0] <= row["peak"] < gate[1]]
        candidates.extend(parsed)
    chosen = []
    for candidate in sorted(candidates, key=lambda c: c["score"], reverse=True):
        if any(max(candidate["start"], other["start"]) < min(candidate["end"], other["end"])
               for other in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) >= limit:
            break
    (output / "selection.json").write_text(json.dumps(chosen, indent=2), encoding="utf-8")
    return chosen
