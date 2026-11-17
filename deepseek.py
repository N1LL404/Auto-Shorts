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


def segment_id(value):
    """Accept exact integer representations, never round or guess an ID."""
    if type(value) is int:
        return value
    if isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        return int(value.strip())
    if type(value) is float and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def extend_short_pick(segments, first, last, lo, hi, duration, minimum, maximum):
    """Add at most five seconds of nearby speech; preserve the entire chosen story."""
    start = float(segments[first]["start"])
    end = min(duration, float(segments[last]["end"]))
    if not 0 < minimum - (end - start) <= 5:
        return start, end
    options = []
    for left in range(first, lo - 1, -1):
        a = float(segments[left]["start"])
        if start - a > 5:
            break
        for right in range(last, hi):
            b = min(duration, float(segments[right]["end"]))
            added = (start - a) + (b - end)
            if added > 5:
                break
            if 0 <= a <= start < end <= b and minimum <= b - a <= maximum:
                options.append((added, abs((start - a) - (b - end)), a, b))
    if options:
        _, _, start, end = min(options)
    return start, end


def validate_picks(result, segments, lo, hi, duration, minimum, maximum, gate=None,
                   diagnostics=None):
    def report(index, status, detail):
        if diagnostics is not None:
            diagnostics.append({"clip": index, "status": status, "detail": detail})

    clips = result.get("clips")
    if not isinstance(clips, list):
        report(None, "rejected", "Response must contain a clips list.")
        return []
    valid = []
    for index, row in enumerate(clips):
        if not isinstance(row, dict):
            report(index, "rejected", "Clip must be an object.")
            continue
        ids = [segment_id(row.get(field)) for field in ("start_id", "end_id", "peak_id")]
        if any(i is None for i in ids):
            report(index, "rejected", "IDs must be exact integers, not timestamps.")
            continue
        first, last, peak = ids
        if not lo <= first <= peak <= last < hi:
            report(index, "rejected", f"Require {lo} <= start_id <= peak_id <= end_id < {hi}.")
            continue
        start, raw_end = float(segments[first]["start"]), float(segments[last]["end"])
        end = min(duration, raw_end)
        peak_time = float(segments[peak]["start"])
        score = row.get("score")
        if isinstance(score, str):
            try:
                score = float(score)
            except ValueError:
                pass
        if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 100:
            report(index, "rejected", "Score must be a finite number from 0 to 100.")
            continue
        if not (math.isfinite(start) and math.isfinite(raw_end) and raw_end <= duration + .1
                and 0 <= start <= peak_time < end <= duration):
            report(index, "rejected", "Selected speech or peak falls outside the video.")
            continue
        original = (start, end)
        start, end = extend_short_pick(segments, first, last, lo, hi, duration, minimum, maximum)
        if not minimum <= end - start <= maximum:
            report(index, "rejected", f"Actual duration is {end-start:.3f}s; require {minimum}–{maximum}s.")
            continue
        if gate and not gate[0] <= peak_time < gate[1]:
            continue
        hook, reason = row.get("hook"), row.get("reason")
        if not isinstance(hook, str) or not isinstance(reason, str) or not hook.strip():
            report(index, "rejected", "Provide a nonempty hook and a text reason.")
            continue
        if original != (start, end):
            report(index, "repaired", f"Extended nearby speech from {original} to {(start, end)}.")
        valid.append(dict(start=start, end=min(duration, end), peak=peak_time, score=score,
                          hook=hook.strip()[:34], signals=["DeepSeek", reason.strip()[:400]]))
    return valid


def select_clips(segments, duration, settings, limit, minimum, maximum, output, gate=None):
    if not segments and gate is not None:
        (output / "selection.json").write_text("[]", encoding="utf-8")
        return []
    if not segments:
        raise ValueError("Whisper found no speech. DeepSeek needs a transcript to select clips.")
    candidates, diagnostics = [], []
    for number, (lo, hi) in enumerate(transcript_chunks(segments, maximum), start=1):
        print(f"DeepSeek is analyzing transcript section {number}…", flush=True)
        user = {"minimum_seconds": minimum, "maximum_seconds": maximum, "maximum_clips": limit,
                "segments": [{"id": i, "start": s["start"], "end": s["end"], "text": s["text"]}
                             for i, s in enumerate(segments[lo:hi], start=lo)]}
        response = completion(settings["api_key"], settings["model"], PROMPT.read_text(), user)
        issues = []
        parsed = validate_picks(response, segments, lo, hi, duration, minimum, maximum,
                                diagnostics=issues)
        diagnostics.append({"section": number, "attempt": 1, "issues": issues})
        if any(issue["status"] == "rejected" for issue in issues):
            print("DeepSeek is correcting clip boundaries…", flush=True)
            user["correction"] = {
                "previous_selection": response,
                "validation_errors": issues,
                "instruction": (
                    "Correct the rejected clips listed in validation_errors. Recheck IDs and calculate "
                    "segments[end_id].end minus segments[start_id].start. "
                    "Return only clips inside the requested duration range with integer IDs, "
                    "start_id <= peak_id <= end_id, numeric score 0–100, hook and reason. "
                    "Return an empty clips list if no complete story fits."
                ),
            }
            response = completion(settings["api_key"], settings["model"], PROMPT.read_text(), user)
            issues = []
            parsed.extend(validate_picks(response, segments, lo, hi, duration, minimum, maximum,
                                         diagnostics=issues))
            diagnostics.append({"section": number, "attempt": 2, "issues": issues})
            if any(issue["status"] == "rejected" for issue in issues):
                print("Skipping invalid DeepSeek selections; continuing with valid clips. "
                      "Details: selection-diagnostics.json", flush=True)
        (output / "selection-diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2), encoding="utf-8")
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
    if not chosen:
        print("No valid clips selected. See selection-diagnostics.json for boundary errors, "
              "if any. DeepSeek may also return no complete stories.", flush=True)
    return chosen
