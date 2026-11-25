"""Native Mac and Windows front end for the released EmuBench measurement engine."""
from datetime import datetime
from pathlib import Path
import os
import queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid
import webbrowser

from . import adapters, catalog, engines, journal

WORKLOADS = {
    "Cartervania · Game Boy Advance": ("carter", "gba"),
    "Super Carter Bros. 3 · Super NES": ("carter", "snes"),
    "Carter Circuit · Game Boy Advance": ("suite", "gba"),
    "Carter Circuit · Super NES": ("suite", "snes"),
    "Local ROM file": ("run", None),
    "ROM folder": ("bench", None),
    "Resume a folder run": ("resume", None),
}
AUTO = "Latest upstream build"
LOCAL = "Choose a core file"
NAMED = "Specific mGBA release"
BLUE, INK, PAPER, LINE, MUTED = "#174cad", "#14243b", "#fafbf8", "#cad4d6", "#455b6b"


def engine_command():
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "emubench"]
    exe = Path(sys.executable).resolve()
    root = exe.parents[1] / "Resources" if sys.platform == "darwin" else exe.parent
    engine = root / "benchmark" / ("emubench" + engines.EXE)
    if not engine.is_file():
        raise FileNotFoundError("The benchmark engine is missing. Extract the complete download and reopen EmuBench.")
    return [str(engine)]


def recent():
    with journal.database() as db:
        return db.execute("""SELECT a.id,a.context,a.game,a.build,a.finished,a.outcome,a.result,
            a.avg,a.low,a.high,m.speed,m.accuracy FROM attempts a LEFT JOIN attempt_metrics m USING(id)
            ORDER BY a.started DESC,a.rowid DESC LIMIT 100""").fetchall()


def valid_path(value, directory=False):
    if not value.strip():
        raise ValueError("Choose a folder first." if directory else "Choose a file first.")
    path = Path(value).expanduser().resolve()
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError(f"Cannot find {path.name or path}. Choose it again.")
    return str(path)


class Desktop:
    def __init__(self, root, engine=None):
        self.root, self.engine = root, engine or engine_command()
        self.events = queue.Queue()
        self.proc = None
        self.proc_lock = threading.Lock()
        self.stop_requested = threading.Event()
        self.busy = False
        self.rows = {}
        self.poll_id = None
        self.workload = tk.StringVar(value=next(iter(WORKLOADS)))
        self.emulator = tk.StringVar()
        self.scene = tk.StringVar(value="Normal")
        self.source = tk.StringVar(value=AUTO)
        self.core = tk.StringVar()
        self.version = tk.StringVar(value=engines.REFERENCE)
        self.path = tk.StringVar()
        self.reserved = tk.BooleanVar()
        self.status = tk.StringVar(value="Ready")
        self.help = tk.StringVar()
        self.metrics = [tk.StringVar(value="—") for _ in range(4)]
        self.accuracy = tk.StringVar(value="Run a benchmark to see its score.")
        root.title("EmuBench")
        root.geometry("900x715")
        root.minsize(700, 640)
        root.configure(background=PAPER)
        root.protocol("WM_DELETE_WINDOW", self.close)
        if os.name == "nt":
            icon = Path(__file__).with_name("assets") / "emubench.png"
            if icon.is_file():
                self.icon = tk.PhotoImage(file=icon)
                root.iconphoto(True, self.icon)
        self.styles()
        self.layout()
        self.workload_changed()
        self.refresh_history()
        self.poll_id = root.after(120, self.poll)

    def styles(self):
        family = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=(family, 11), background=PAPER, foreground=INK)
        style.configure("TFrame", background=PAPER)
        style.configure("TLabel", background=PAPER, foreground=INK)
        style.configure("Muted.TLabel", foreground=MUTED, font=(family, 10))
        style.configure("Title.TLabel", font=(family, 21, "bold"))
        style.configure("Score.TLabel", font=(family, 23, "bold"), foreground=BLUE)
        style.configure("TButton", padding=(10, 6), bordercolor=LINE)
        style.map("TButton", background=[("active", "#e2eaf1")])
        style.configure("Run.TButton", padding=(17, 8), background=BLUE, foreground="white", font=(family, 11, "bold"))
        style.map("Run.TButton", background=[("disabled", "#68798a"), ("active", "#103b87")], foreground=[("disabled", "white")])
        style.configure("TCombobox", padding=4, fieldbackground="white")
        style.map("TCombobox", fieldbackground=[("readonly", "white")], foreground=[("readonly", INK)])
        style.configure("TNotebook.Tab", padding=(16, 8))
        style.map("TNotebook.Tab", background=[("selected", PAPER)], foreground=[("selected", BLUE)])
        style.configure("Treeview", rowheight=29, fieldbackground="white", background="white")
        style.configure("Treeview.Heading", font=(family, 10, "bold"), padding=5)

    def layout(self):
        mast = tk.Frame(self.root, bg=INK)
        mast.pack(fill="x")
        tk.Label(mast, text="EmuBench", foreground="white", background=INK,
                 font=("Helvetica", 23, "bold")).pack(side="left", padx=22, pady=11)
        tk.Label(mast, text=catalog.host_target().replace("macos", "macOS").replace("windows", "Windows").replace("-", "  ·  "),
                 background=INK, foreground="#d4e4ff").pack(side="right", padx=22)
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=12)
        self.setup = ttk.Frame(self.tabs, padding=(16, 12))
        history = ttk.Frame(self.tabs, padding=12)
        activity = ttk.Frame(self.tabs, padding=12)
        for frame, label in [(self.setup, "Benchmark"), (history, "History"), (activity, "Run log")]:
            self.tabs.add(frame, text=label)
        self.setup.columnconfigure(1, weight=1)
        ttk.Label(self.setup, text="Run a benchmark", style="Title.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 7))
        self.workbox = self.combo("Workload", self.workload, list(WORKLOADS), 1, self.workload_changed)
        self.pathrow = self.path_field("Location", self.path, 2, self.pick_workload)
        self.emubox = self.combo("Emulator", self.emulator, [], 3, self.emulator_changed)
        self.scenebox = self.combo("Scene", self.scene, ["Easy", "Normal", "Hard", "All"], 4)
        self.sourcebox = self.combo("Emulator build", self.source, [AUTO, LOCAL], 5, self.source_changed)
        self.corerow = self.path_field("Core file", self.core, 6, self.pick_core)
        self.versionrow = self.field("Release", ttk.Entry(self.setup, textvariable=self.version), 7)
        self.reserve = ttk.Checkbutton(self.setup, text="This computer is reserved for the folder run", variable=self.reserved)
        self.reserve.grid(row=8, column=1, columnspan=2, sticky="w")
        ttk.Label(self.setup, textvariable=self.help, style="Muted.TLabel", wraplength=550).grid(row=9, column=0, columnspan=3, sticky="w", pady=(6, 9))
        actions = ttk.Frame(self.setup)
        actions.grid(row=10, column=0, columnspan=3, sticky="ew")
        self.run_button = ttk.Button(actions, text="Run benchmark", style="Run.TButton", command=self.start)
        self.run_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        ttk.Label(actions, textvariable=self.status, style="Muted.TLabel", wraplength=330).pack(side="left", padx=6)
        ttk.Separator(self.setup).grid(row=11, column=0, columnspan=3, sticky="ew", pady=14)
        stats = ttk.Frame(self.setup)
        stats.grid(row=12, column=0, columnspan=3, sticky="ew")
        for i, label in enumerate(["Console speed", "Average FPS", "1% low FPS", "1% high FPS"]):
            stats.columnconfigure(i, weight=1, uniform="metrics")
            ttk.Label(stats, text=label, style="Muted.TLabel").grid(row=0, column=i, sticky="w")
            ttk.Label(stats, textvariable=self.metrics[i], style="Score.TLabel").grid(row=1, column=i, sticky="w")
        ttk.Label(self.setup, textvariable=self.accuracy, style="Muted.TLabel", wraplength=600).grid(row=13, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.history = ttk.Treeview(history, columns=("date", "game", "build", "fps", "outcome"), show="headings", selectmode="browse")
        for key, label, width in [("date","Local time",122),("game","Game / scene",200),("build","Emulator",116),("fps","Avg FPS",64),("outcome","Outcome",96)]:
            self.history.heading(key, text=label)
            self.history.column(key, width=width, minwidth=48, stretch=key in ("game","build"), anchor="e" if key=="fps" else "w")
        bar = ttk.Scrollbar(history, orient="vertical", command=self.history.yview)
        self.history.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.history.pack(fill="both", expand=True)
        row = ttk.Frame(history)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="View frame chart", command=self.chart).pack(side="left")
        ttk.Button(row, text="Publish score…", command=self.publish).pack(side="left", padx=8)
        ttk.Button(row, text="Refresh", command=self.refresh_history).pack(side="left")
        self.history.bind("<Double-1>", lambda _: self.chart())
        self.log = tk.Text(activity, background=INK, foreground="#eff6ff", insertbackground="white", font=("Menlo" if sys.platform=="darwin" else "Consolas", 10), wrap="word", padx=12, pady=12, state="disabled")
        logbar=ttk.Scrollbar(activity, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=logbar.set)
        logbar.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

    def field(self, label, widget, row):
        name = ttk.Label(self.setup, text=label)
        name.grid(row=row, column=0, sticky="w", padx=(0, 20), pady=4)
        widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
        return name, widget

    def combo(self, label, variable, values, row, callback=None):
        box = ttk.Combobox(self.setup, textvariable=variable, values=values, state="readonly")
        pair = self.field(label, box, row)
        if callback:
            box.bind("<<ComboboxSelected>>", lambda _: callback())
        return pair

    def path_field(self, label, variable, row, command):
        container = ttk.Frame(self.setup)
        entry=ttk.Entry(container, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True)
        if variable is self.path:
            entry.bind("<FocusOut>", lambda _: self.update_rom_choices())
        ttk.Button(container, text="Browse…", command=command).pack(side="left", padx=(6, 0))
        return self.field(label, container, row)

    @staticmethod
    def show(pair, visible):
        for widget in pair:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def pick_workload(self):
        kind = WORKLOADS[self.workload.get()][0]
        if kind=="resume":
            folder=engines.home()/"campaigns"
            path=filedialog.askopenfilename(parent=self.root, title="Resume a saved queue", initialdir=str(folder) if folder.is_dir() else None, filetypes=[("EmuBench queues","*.sqlite"),("All files","*")])
        elif kind=="bench":
            path=filedialog.askdirectory(parent=self.root)
        else:
            path=filedialog.askopenfilename(parent=self.root, title="Choose a ROM")
        if path:
            self.path.set(path)
            self.choose_peers()

    def update_rom_choices(self):
        if WORKLOADS[self.workload.get()][0]=="run" and Path(self.path.get()).suffix.lower()!=self.last_suffix:
            self.choose_peers()

    def pick_core(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose a libretro core")
        if path:
            self.core.set(path)

    def workload_changed(self):
        self.path.set("")
        kind, _ = WORKLOADS[self.workload.get()]
        self.show(self.pathrow, kind in ("run", "bench", "resume"))
        self.show(self.scenebox, kind in ("suite", "carter"))
        self.show(self.emubox, kind!="resume")
        self.show(self.sourcebox, kind!="resume")
        self.reserve.grid() if kind=="bench" else self.reserve.grid_remove()
        self.choose_peers()
        self.help.set({"carter":"Recorded gameplay. EmuBench checks the scene against reference images.",
            "suite":"The same repeatable scene runs three times on your device.",
            "run":"Choose an unpacked ROM and a compatible emulator. The run starts at boot.",
            "bench":"Scan subfolders and save a queue that you can resume from the Workload menu.",
            "resume":"Choose a saved .sqlite queue from your EmuBench campaigns folder."}[kind])

    def choose_peers(self):
        kind, system = WORKLOADS[self.workload.get()]
        self.last_suffix=Path(self.path.get()).suffix.lower()
        if kind in ("carter", "suite"):
            peers = ["mgba"] if system=="gba" else ["snes9x","bsnes","cartssnes"]
        elif kind=="run":
            ext=Path(self.path.get()).suffix.lower()
            system=adapters.SUFFIXES.get(ext)
            peers=list(adapters.ROUTES[system][1]) if system else list(adapters.NAMES)
            if ext==".chd":
                peers+=list(adapters.ROUTES["pcecd"][1])
            if system=="snes":
                peers.append("cartssnes")
        else:
            peers=list(adapters.NAMES)
        self.peers={adapters.NAMES[k]:k for k in peers}
        self.emubox[1].configure(values=list(self.peers))
        if self.emulator.get() not in self.peers:
            self.emulator.set(next(iter(self.peers)))
        self.emulator_changed()

    def emulator_changed(self):
        kind=WORKLOADS[self.workload.get()][0]
        peer=self.peers[self.emulator.get()]
        options=[LOCAL] if peer=="cartssnes" else [AUTO, LOCAL]
        if peer=="mgba" and kind not in ("bench","resume"):
            options.append(NAMED)
        self.sourcebox[1].configure(values=options)
        self.core.set("")
        self.source.set(options[0])
        self.source_changed()

    def source_changed(self):
        visible=WORKLOADS[self.workload.get()][0]!="resume"
        self.show(self.corerow, visible and self.source.get()==LOCAL)
        self.show(self.versionrow, visible and self.source.get()==NAMED)

    def plan(self):
        kind, _ = WORKLOADS[self.workload.get()]
        if kind=="resume":
            return ["campaign","resume",valid_path(self.path.get())], None
        peer=self.peers[self.emulator.get()]
        args=[kind]
        if kind=="bench":
            args += [valid_path(self.path.get(), True)]
            if self.reserved.get():
                args.append("--dedicated")
            elif sys.platform!="darwin":
                raise ValueError("Reserve this computer for the folder run before starting.")
        elif kind=="run":
            args += ["--rom",valid_path(self.path.get())]
        else:
            args += ["--scene",self.scene.get().lower()]
        args += ["--emulator",peer]
        if self.source.get()==LOCAL:
            args += ["--core",valid_path(self.core.get())]
        elif self.source.get()==NAMED:
            release=self.version.get().strip()
            if release!="latest" and not engines.TAG.fullmatch(release):
                raise ValueError("Enter an mGBA release such as 0.10.5, or latest.")
            args += ["--version",release]
        elif catalog.host_target()=="windows-arm64":
            return args, peer
        elif kind=="run":
            args.append("--latest-core")
        return args, None

    def start(self):
        try:
            args, translated = self.plan()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Check benchmark settings", str(exc), parent=self.root)
            return
        self.launch(args, "Benchmark", translated=translated)

    def launch(self, args, title, translated=None, report=None):
        if self.busy:
            return
        self.busy=True
        self.stop_requested.clear()
        self.run_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.status.set(title+" running…")
        if title=="Benchmark":
            self.before={row[0] for row in recent()}
            for metric in self.metrics:
                metric.set("—")
            self.accuracy.set("Measuring…")
        self.append_log("\n"+title)
        def work():
            try:
                selected=list(args)
                if translated:
                    self.events.put(("line","Downloading the x64 emulator for Windows on Arm translation."))
                    output=self.execute(["download",translated,"--channel","core","--target","windows-x64"])
                    selected+=["--core",valid_path(output.strip())]
                self.execute(selected)
                self.events.put(("done",(title, report)))
            except Exception as exc:
                self.events.put(("error",str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def execute(self, args):
        flags = subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
        with self.proc_lock:
            if self.stop_requested.is_set():
                raise ValueError("Stopped")
            self.proc=subprocess.Popen(self.engine+list(map(str,args)), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, errors="replace", creationflags=flags, start_new_session=os.name!="nt",
                env=os.environ | {"PYINSTALLER_RESET_ENVIRONMENT":"1","PYTHONUNBUFFERED":"1","PYTHONIOENCODING":"utf-8"})
            proc=self.proc
        last=""
        with proc:
            for line in proc.stdout:
                line=line.rstrip()
                if line:
                    last=line
                    self.events.put(("line",line))
            code=proc.wait()
        with self.proc_lock:
            self.proc=None
        if self.stop_requested.is_set():
            raise ValueError("Stopped")
        if code:
            raise ValueError(last or f"Engine exited with status {code}")
        return last

    def stop(self):
        self.stop_requested.set()
        with self.proc_lock:
            proc=self.proc
            if proc and proc.poll() is None:
                if os.name=="nt":
                    subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    try:
                        os.killpg(proc.pid,signal.SIGTERM)
                    except ProcessLookupError:
                        pass
        self.status.set("Stopping…")

    def append_log(self,line):
        self.log.configure(state="normal")
        self.log.insert("end",line+"\n")
        if int(self.log.index("end-1c").split(".")[0])>400:
            self.log.delete("1.0","30.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        for _ in range(100):
            try:
                kind, value=self.events.get_nowait()
            except queue.Empty:
                break
            if kind=="line":
                self.append_log(value)
                continue
            self.busy=False
            self.stop_button.state(["disabled"])
            self.run_button.state(["!disabled"])
            if kind=="error":
                self.append_log(value)
                self.status.set("Stopped" if self.stop_requested.is_set() else "Failed · see Run log")
                self.accuracy.set("No new score.")
                self.refresh_history()
            else:
                title, report=value
                self.status.set(title+" finished")
                self.refresh_history(show_score=title=="Benchmark")
                if report:
                    webbrowser.open(report.as_uri())
        self.poll_id=self.root.after(120,self.poll)

    def refresh_history(self, show_score=False):
        records=recent()
        self.rows={r[0]:r for r in records}
        previous=self.history.selection()
        self.history.delete(*self.history.get_children())
        for r in records:
            date=datetime.fromisoformat(r[4].replace("Z","+00:00")).astimezone().strftime("%b %d %H:%M") if r[4] else "—"
            title=r[1] if r[1] and r[1]!="single run" else r[2]
            self.history.insert("", "end", iid=r[0], values=(date,title,r[3],f"{r[7]:.0f}" if r[7] is not None else "—",r[5]))
        if records:
            self.history.selection_set(previous[0] if previous and previous[0] in self.rows else records[0][0])
        if show_score:
            complete=next((r for r in records if r[5]=="completed" and r[6] and r[0] not in self.before),None)
            if complete:
                _,context,game,build,_,_,_,avg,low,high,speed,accuracy=complete
                for el,val in zip(self.metrics,[f"{speed:.2f}×" if speed is not None else "—",*[f"{v:.0f}" if v is not None else "—" for v in (avg,low,high)]]):
                    el.set(val)
                self.accuracy.set(f"{context if context and context!='single run' else game}  ·  {build}  ·  {accuracy or 'Accuracy untested'}")
            else:
                self.accuracy.set("No new completed scores. See History and Run log.")

    def selected_result(self):
        selection=self.history.selection()
        row=self.rows.get(selection[0]) if selection else None
        if self.busy or not row or not row[6] or not Path(row[6]).is_file():
            messagebox.showinfo("Choose a completed run", "Select a saved, completed run while EmuBench is idle.", parent=self.root)
            return None
        return row

    def chart(self):
        row=self.selected_result()
        if row:
            folder=engines.home()/"reports"
            folder.mkdir(parents=True, exist_ok=True)
            path=folder/(row[0]+"-"+uuid.uuid4().hex+".html")
            self.launch(["details",row[6],"--out",path],"Frame chart",report=path)

    def publish(self):
        row=self.selected_result()
        if row and messagebox.askyesno("Publish this score?", "Share this run’s hardware, timings and accuracy checks at emubench.games? ROM files and local paths stay on this device.",parent=self.root):
            self.launch(["publish",row[6],"--yes"],"Publication")

    def close(self):
        if self.busy:
            if messagebox.askyesno("Stop the current job?", "Stop this job before closing EmuBench?", parent=self.root):
                self.stop()
                self.root.after(200,self.close_when_idle)
            return
        if self.poll_id:
            self.root.after_cancel(self.poll_id)
        self.root.destroy()

    def close_when_idle(self):
        if self.busy:
            self.root.after(200,self.close_when_idle)
        else:
            self.close()


def main():
    root=tk.Tk()
    Desktop(root)
    root.mainloop()


if __name__=="__main__":
    main()
