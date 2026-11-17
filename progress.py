"""Worker progress messages and a UI-independent presentation model."""
import json
import math

PREFIX = "AUTOSHORTS_PROGRESS "


def emit(stage, percent=None, detail=""):
    print(PREFIX + json.dumps({"stage": stage, "percent": percent, "detail": detail}), flush=True)


def snapshot(job):
    active = job.get("status") in ("queued", "checking", "uploading", "running", "stopping")
    result = {"stage": 0, "percent": None, "title": "Preparing source",
              "detail": job.get("message", ""), "active": active}
    titles = ["Preparing source", "Transcribing speech", "Finding the best moments", "Exporting shorts"]
    for line in job.get("activity", "").splitlines():
        if not line.startswith(PREFIX):
            continue
        try:
            value = json.loads(line[len(PREFIX):])
            stage, percent = value["stage"], value.get("percent")
            if type(stage) is not int or stage not in range(4):
                continue
            if percent is not None and (type(percent) not in (int, float) or not math.isfinite(percent)):
                continue
            result.update(stage=stage, title=titles[stage],
                          percent=None if percent is None else max(0, min(100, percent)),
                          detail=str(value.get("detail", "")))
        except (ValueError, KeyError, TypeError):
            continue
    if result["percent"] is not None:
        result["detail"] += f' · {result["percent"]:.0f}% of this stage'
    elif active:
        result["detail"] += " · Working; percentage unavailable"
    if not active:
        status = job.get("status")
        result.update(title={"done": "Job complete", "error": "Job needs attention", "stopped": "Job stopped"}.get(status, "Ready"),
                      detail=job.get("message", ""), percent=100 if status == "done" else 0)
    return result
