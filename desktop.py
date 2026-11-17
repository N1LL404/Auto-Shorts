"""Auto-Shorts desktop entry point and packaged worker."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import queue


def configure_runtime():
    root = Path(__file__).resolve().parent
    bundled = root / "bin"
    if bundled.exists():
        os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")
    data = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "AutoShorts"
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(data / "models"))
    if sys.stdout is None:
        sys.stdout = (data / "desktop.log").open("a", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = sys.stdout
    if os.name == "nt":
        original = subprocess.Popen
        class HiddenProcess(original):
            def __init__(self, *args, **kwargs):
                kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
                super().__init__(*args, **kwargs)
        subprocess.Popen = HiddenProcess
    return data


def open_local(path):
    if os.name == "nt":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class Desktop:
    def __init__(self, root, data):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        from studio import Studio
        self.tk, self.ttk = tk, ttk
        self.dialog, self.alert = filedialog, messagebox
        self.root, self.data = root, data
        self.studio = Studio(data, "base.en")
        self.events = queue.Queue()
        self.rows = {}
        root.title("Auto-Shorts · DrDonut")
        root.geometry("1030x800")
        root.minsize(840, 650)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f5ef")
        style.configure("TLabel", background="#f4f5ef")
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("TButton", padding=7)
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="DrDonut Shorts Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Choose a downloaded video or paste a stream link.").pack(anchor="w", pady=(3, 16))
        settings = ttk.LabelFrame(outer, text="DeepSeek & Whisper", padding=12)
        settings.pack(fill="x")
        settings.columnconfigure(1, weight=1)
        values = self.studio.settings.public()
        self.key = tk.StringVar()
        self.model = tk.StringVar(value=values["model"])
        self.whisper = tk.StringVar(value=values["whisper"])
        ttk.Label(settings, text="DeepSeek API key").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(settings, textvariable=self.key, show="•").grid(row=0, column=1, sticky="ew")
        ttk.Label(settings, text="Leave blank to keep the saved key.").grid(row=1, column=1, sticky="w")
        ttk.Label(settings, text="DeepSeek model").grid(row=2, column=0, sticky="w")
        self.model_box = ttk.Combobox(settings, textvariable=self.model)
        self.model_box.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(settings, text="Whisper model").grid(row=3, column=0, sticky="w")
        ttk.Combobox(settings, textvariable=self.whisper, values=values["whisper_choices"],
                     state="readonly").grid(row=3, column=1, sticky="ew")
        buttons = ttk.Frame(settings)
        buttons.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        for label, callback in [
            ("Save settings", self.save_settings), ("Load models", lambda: self.model_action("models")),
            ("Test connection", lambda: self.model_action("test")), ("Download Whisper", self.prepare),
            ("Remove key", self.remove_key),
        ]:
            ttk.Button(buttons, text=label, command=callback).pack(side="left", padx=(0, 6))
        self.settings_status = tk.StringVar(value="Key saved." if values["has_key"] else "Enter your DeepSeek API key to begin.")
        ttk.Label(settings, textvariable=self.settings_status, wraplength=900).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.whisper_status = tk.StringVar()
        ttk.Label(settings, textvariable=self.whisper_status, wraplength=900).grid(
            row=6, column=0, columnspan=2, sticky="w")
        source = ttk.LabelFrame(outer, text="Source video", padding=12)
        source.pack(fill="x", pady=12)
        self.source_kind = tk.StringVar(value="file")
        choices = ttk.Frame(source)
        choices.pack(fill="x")
        ttk.Radiobutton(choices, text="Downloaded video", value="file", variable=self.source_kind).pack(side="left")
        ttk.Radiobutton(choices, text="Twitch / YouTube URL", value="url", variable=self.source_kind).pack(side="left", padx=15)
        self.source = tk.StringVar()
        line = ttk.Frame(source)
        line.pack(fill="x", pady=8)
        ttk.Entry(line, textvariable=self.source).pack(side="left", fill="x", expand=True)
        ttk.Button(line, text="Choose video…", command=self.choose).pack(side="left", padx=(8, 0))
        actions = ttk.Frame(source)
        actions.pack(fill="x")
        self.generate = ttk.Button(actions, text="Generate Shorts", command=self.start)
        self.generate.pack(side="left")
        self.stop_button = ttk.Button(actions, text="Stop", command=self.stop)
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Open output folder", command=self.open_folder).pack(side="left")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(outer, textvariable=self.status, wraplength=930).pack(anchor="w", pady=(0, 8))
        self.jobs_box = ttk.Combobox(outer, state="readonly")
        self.jobs_box.pack(fill="x", pady=(0, 8))
        self.jobs_box.bind("<<ComboboxSelected>>", lambda event: self.refresh_clips())
        self.clips = ttk.Treeview(outer, columns=("title", "range", "score"), show="headings", height=5)
        for name, label, width in [("title", "Clip", 560), ("range", "Source time", 130), ("score", "Score", 70)]:
            self.clips.heading(name, text=label)
            self.clips.column(name, width=width)
        self.clips.pack(fill="both", expand=True)
        self.clips.bind("<Double-1>", lambda event: self.open_clip())
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="Play clip", command=self.open_clip).pack(side="left")
        ttk.Button(bar, text="Open post kit", command=lambda: self.open_clip("kit")).pack(side="left", padx=8)
        self.log = tk.Text(outer, height=5, wrap="word", state="disabled")
        self.log.pack(fill="x")
        self.job_ids = []
        self.clip_key = None
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll()

    def choose(self):
        name = self.dialog.askopenfilename(filetypes=[("Videos", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.ts"), ("All files", "*.*")])
        if name:
            self.source_kind.set("file")
            self.source.set(name)

    def save_settings(self):
        try:
            from studio import ACTIVE
            with self.studio.lock:
                if any(j["status"] in ACTIVE for j in self.studio.jobs.values()):
                    raise ValueError("Stop the current job before changing settings.")
                self.studio.settings.save({"api_key": self.key.get(), "model": self.model.get(),
                                           "whisper": self.whisper.get()})
            self.key.set("")
            self.settings_status.set("Settings saved. DeepSeek API usage is billed to your account.")
            return True
        except (ValueError, OSError) as exc:
            self.settings_status.set(str(exc))
            return False

    def remove_key(self):
        if self.save_settings():
            self.studio.settings.save({"remove_key": True})
            self.settings_status.set("API key removed.")

    def model_action(self, action):
        if not self.save_settings():
            return
        self.settings_status.set("Connecting to DeepSeek…")
        def work():
            try:
                result = self.studio.settings.discover() if action == "models" else self.studio.settings.test()
                self.events.put((action, result))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def prepare(self):
        if self.save_settings():
            self.studio.settings.prepare()

    def start(self):
        if not self.save_settings():
            return
        try:
            if self.source_kind.get() == "file":
                path = Path(self.source.get()).expanduser().resolve()
                if not path.is_file():
                    raise ValueError("Choose a downloaded video file.")
                id = self.studio.create({"filename": path.name}, upload=True)
                with self.studio.lock:
                    job = self.studio.jobs[id]
                    self.studio.update(job, local_source=str(path), status="queued",
                                       message="Preparing selected video…")
                    threading.Thread(target=self.studio.work, args=(job,), daemon=True).start()
            else:
                self.studio.create({"url": self.source.get()})
            self.job_ids = []
        except (ValueError, RuntimeError, OSError) as exc:
            self.status.set(str(exc))

    def stop(self):
        from studio import ACTIVE
        with self.studio.lock:
            for job in self.studio.jobs.values():
                if job["status"] in ACTIVE:
                    self.studio.stop(job)

    def current(self):
        i = self.jobs_box.current()
        return self.studio.details(self.job_ids[i]) if 0 <= i < len(self.job_ids) else None

    def refresh_clips(self):
        self.clip_key = None

    def open_folder(self):
        job = self.current()
        folder = self.studio.folder(job) / "exports" if job else self.data
        open_local(folder if folder.exists() else folder.parent)

    def open_clip(self, field="file"):
        selected = self.clips.selection()
        job = self.current()
        if selected and job:
            row = self.rows.get(selected[0], {})
            if field in row:
                open_local(self.studio.folder(job) / "exports" / row[field])

    def poll(self):
        from studio import ACTIVE
        while not self.events.empty():
            kind, result = self.events.get()
            if kind == "models":
                self.model_box["values"] = result["models"]
                self.settings_status.set("Models loaded. Choose one and save.")
            else:
                self.settings_status.set(result["message"] if kind == "test" else result)
        with self.studio.lock:
            jobs = list(reversed(list(self.studio.jobs.values())))
            ids = [j["id"] for j in jobs]
            busy = any(j["status"] in ACTIVE for j in jobs)
        if ids != self.job_ids:
            self.job_ids = ids
            self.jobs_box["values"] = [j["title"] for j in jobs]
            if ids:
                self.jobs_box.current(0)
        self.generate["state"] = "disabled" if busy else "normal"
        self.stop_button["state"] = "normal" if busy else "disabled"
        state = self.studio.settings.public()
        self.whisper_status.set(state["download"]["message"])
        job = self.current()
        if job:
            self.status.set(job["status"].capitalize() + " · " + job["message"])
            self.log.configure(state="normal")
            self.log.delete("1.0", "end")
            self.log.insert("end", job["activity"])
            self.log.configure(state="disabled")
            key = (job["id"], repr(job["clips"]))
            if key != self.clip_key:
                self.clip_key = key
                self.clips.delete(*self.clips.get_children())
                self.rows = {}
                for i, clip in enumerate(job["clips"]):
                    iid = str(i)
                    self.rows[iid] = clip
                    self.clips.insert("", "end", iid=iid, values=(
                        clip.get("hook") or clip.get("title", "Clip"),
                        f'{clip["start"]:.1f}–{clip["end"]:.1f}s', clip["score"]))
        self.root.after(1000, self.poll)

    def close(self):
        from studio import ACTIVE
        with self.studio.lock:
            busy = any(j["status"] in ACTIVE for j in self.studio.jobs.values())
        if busy and not self.alert.askyesno("Close Auto-Shorts", "Stop the current job and close the app?"):
            return
        self.stop()
        self.root.destroy()


def main():
    data = configure_runtime()
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        sys.stdout = open(sys.argv[2], "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stdout
        sys.argv = [sys.argv[0], *sys.argv[3:]]
        from autoshorts import main as worker
        worker()
        return
    import tkinter as tk
    root = tk.Tk()
    app = Desktop(root, data)
    if "--self-test" in sys.argv:
        from autoshorts import probe
        from faster_whisper import WhisperModel
        import av, onnxruntime, ctranslate2, tokenizers
        root.update()
        for executable in ("ffmpeg", "ffprobe", "node", "yt-dlp"):
            subprocess.run([executable, "-version" if executable.startswith("ff") else "--version"],
                           check=True, stdout=subprocess.DEVNULL)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "sample.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=s=320x240:d=1", "-c:v", "libx264", str(sample)], check=True)
            assert probe(sample)[1]["width"] == 320
        root.destroy()
        print("DESKTOP_SELF_TEST_PASSED", flush=True)
        return
    root.mainloop()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        if "--self-test" not in sys.argv and "--worker" not in sys.argv:
            from tkinter import messagebox
            messagebox.showerror("Auto-Shorts", "The app could not start. See desktop.log in your AutoShorts data folder.")
        sys.exit(1)
