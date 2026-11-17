const el = (id) => document.getElementById(id);
const active = new Set(["queued", "checking", "running", "stopping"]);
const statusText = {
  queued: "Queued", checking: "Checking URL", running: "Processing",
  stopping: "Stopping", stopped: "Stopped", done: "Complete", error: "Failed",
};
let selected = sessionStorage.getItem("auto-shorts-session");
let listKey = "";
let clipKey = "";
let busy = false;
let polling = false;
let revision = 0;

async function request(path, body) {
  const res = await fetch(path, body === undefined ? {cache: "no-store"} : {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "The studio couldn’t complete the request.");
  return data;
}

function node(tag, text, cls) {
  const result = document.createElement(tag);
  if (text) result.textContent = text;
  if (cls) result.className = cls;
  return result;
}

function selectJob(id) {
  selected = id;
  sessionStorage.setItem("auto-shorts-session", id);
  revision += 1;
}

function showList(jobs) {
  const key = JSON.stringify([selected, jobs]);
  if (listKey === key) return;
  listKey = key;
  el("no-jobs").hidden = jobs.length !== 0;
  el("jobs").replaceChildren(...jobs.map((job) => {
    const li = node("li");
    const button = node("button");
    if (job.id === selected) button.setAttribute("aria-current", "true");
    button.append(node("span", job.title), node("small", statusText[job.status]));
    button.title = job.title;
    button.addEventListener("click", () => {
      selectJob(job.id);
      refresh();
    });
    li.append(button);
    return li;
  }));
}

function clock(seconds) {
  const n = Math.floor(seconds);
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}

function showClips(job) {
  let key = JSON.stringify([job.id, job.clips]);
  if (clipKey === key) return;
  clipKey = key;
  el("count").textContent = `${job.clips.length} ready`;
  el("count").hidden = !job.clips.length;
  el("clips").replaceChildren(...job.clips.map((clip) => {
    const link = (file) => "/media/" + job.id + "/" + file.split("/").map(encodeURIComponent).join("/");
    const card = node("article", "", "card");
    const video = node("video");
    video.controls = true;
    video.playsInline = true;
    video.preload = "none";
    video.src = link(clip.file);
    if (clip.cover) video.poster = link(clip.cover);
    const body = node("section");
    body.append(node("h3", clip.title || clip.hook || `Clip ${clip.index}`),
      node("p", `${clock(clip.start)}–${clock(clip.end)} · ${Math.round(clip.end - clip.start)} sec`));
    const actions = node("div", "", "card-footer");
    const mp4 = node("a", "Download MP4");
    mp4.href = link(clip.file) + "?download=1";
    actions.append(mp4);
    if (clip.kit) {
      const zip = node("a", "Post kit");
      zip.href = link(clip.kit) + "?download=1";
      actions.append(zip);
    }
    if (clip.cover) {
      const cover = node("a", "Cover");
      cover.href = link(clip.cover) + "?download=1";
      actions.append(cover);
    }
    if (clip.caption) {
      const copy = node("button", "Copy post");
      copy.type = "button";
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(clip.title + "\n\n" + clip.caption);
          el("notice").textContent = "Post copy copied.";
        } catch {
          el("notice").textContent = "The post text is available in the post kit.";
        }
      });
      actions.append(copy);
    }
    body.append(actions);
    card.append(video, body);
    return card;
  }));
}

function showJob(job) {
  el("job-state").hidden = false;
  el("status").textContent = job.status === "running" && job.mode === "live" ? "Capturing live" : statusText[job.status];
  el("job-title").textContent = job.title;
  const stage = job.activity.split("\n").reverse().find((line) =>
    /^(Transcribing|Finding highlights|Rendering clip|Capturing live stream|Watching for)/.test(line));
  el("message").textContent = job.status === "running" && stage ? stage : job.message;
  el("stop").hidden = !active.has(job.status);
  el("stop").disabled = job.status === "stopping";
  el("log-panel").hidden = !job.activity;
  el("log").textContent = job.activity;
  el("empty").hidden = job.clips.length > 0;
  el("empty-message").textContent = active.has(job.status)
    ? "Clips appear here as they’re ready."
    : "This session has no exports.";
  showClips(job);
}

async function refresh() {
  if (polling) return;
  polling = true;
  const version = revision;
  try {
    const jobs = await request("/api/jobs");
    if (version !== revision) return;
    if (!jobs.some((job) => job.id === selected)) selected = jobs[0]?.id || null;
    showList(jobs);
    el("generate").disabled = busy || jobs.some((job) => active.has(job.status));
    if (selected) {
      const job = await request("/api/jobs/" + selected);
      if (version === revision) showJob(job);
    }
  } catch (err) {
    el("notice").textContent = err.message;
  } finally {
    polling = false;
    if (version !== revision) refresh();
  }
}

el("source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  el("form-error").hidden = true;
  el("notice").textContent = "";
  busy = true;
  el("generate").disabled = true;
  try {
    const data = await request("/api/jobs", {url: el("stream").value});
    selectJob(data.id);
  } catch (err) {
    el("form-error").textContent = err.message;
    el("form-error").hidden = false;
    el("generate").disabled = false;
  } finally {
    busy = false;
    refresh();
  }
});
el("stop").addEventListener("click", async () => {
  el("stop").disabled = true;
  try {
    await request("/api/jobs/" + selected + "/stop", {});
    refresh();
  } catch (err) {
    el("notice").textContent = err.message;
    el("stop").disabled = false;
  }
});
refresh();
setInterval(refresh, 2400);
