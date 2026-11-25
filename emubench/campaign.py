"""A private, restartable queue. Each finished measurement is one SQLite transaction."""
from contextlib import closing
import ctypes
import uuid
import hashlib
import json
import os
import plistlib
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from . import accuracy, carter, chips, circuit, downloads, engines, journal, library, scores, uploads


def arguments(commands):
    group = commands.add_parser("campaign", help="Create, resume or inspect an unattended local queue")
    actions = group.add_subparsers(dest="action", required=True)
    new = actions.add_parser("create")
    new.add_argument("queue", type=Path)
    new.add_argument("--rom", type=Path, action="append", help="Local ROM, ZIP or directory (repeatable)")
    new.add_argument("--rom-dir", type=Path, action="append", help="Recursively scan a ROM library (repeatable)")
    new.add_argument("--share-title", action="store_true", help="Share known catalog names and editions")
    new.add_argument("--circuit", choices=("all",*circuit.LEVELS), help="Queue the source-built public scenes")
    new.add_argument("--carts-core", type=Path, help="Include this CartsSNES library in an all-emulator queue")
    new.add_argument("--carter", choices=("all","easy","normal","hard"), help="Queue pinned Carter scenes")
    new.add_argument("--emulator", choices=(*scores.ADAPTERS, "all"),
                     help="Select one emulator or all compatible ones (default for directories)")
    build = new.add_mutually_exclusive_group()
    build.add_argument("--version", default=None)
    build.add_argument("--latest-core", action="store_true")
    build.add_argument("--core", type=Path)
    new.add_argument("--warmup-frames", type=int)
    new.add_argument("--frames", type=int)
    new.add_argument("--timeout", type=int, default=300)
    new.add_argument("--loop", action="store_true", help="Enqueue a new numbered round after each pass")
    new.add_argument("--days", type=float, help="Maximum elapsed days from first resume")
    gate = new.add_mutually_exclusive_group()
    gate.add_argument("--idle-check", type=Path, help="Trusted local executable returning 0 only when safe to time")
    gate.add_argument("--dedicated", action="store_true", help="Explicitly reserve a dedicated host for this queue")
    new.add_argument("--idle-seconds", type=int, default=300, help="Minimum time since macOS HID activity")
    for name in ("resume", "status", "export", "retry", "launch-agent"):
        p = actions.add_parser(name)
        p.add_argument("queue", type=Path)
        if name == "resume":
            p.add_argument("--wait-uploads", action="store_true",
                           help="Keep retrying after measurement until the device's upload queue clears")
        if name in ("retry", "export"):
            p.add_argument("--job", type=int, required=True)
        if name in ("export", "launch-agent"):
            p.add_argument("--out", required=True, type=Path)


def create(args):
    if (args.circuit or args.carter) and (args.frames is not None or args.warmup_frames is not None):
        raise ValueError("A Carter scene defines its own setup and measurement window")
    args.frames = 1800 if args.frames is None else args.frames
    args.warmup_frames = 120 if args.warmup_frames is None else args.warmup_frames
    if not 100 <= args.frames <= 1_000_000 or not 0 <= args.warmup_frames <= 1_000_000:
        raise ValueError("Invalid frame window")
    if args.timeout < 1 or args.idle_seconds < 1 or args.days is not None and not 0 < args.days <= 3650:
        raise ValueError("Timeout, idle period and optional day limit must be positive")
    if sys.platform != "darwin" and not (args.idle_check or args.dedicated):
        raise ValueError("Choose --idle-check for this device or --dedicated for a reserved test host")
    gate = str(args.idle_check.resolve(strict=True)) if args.idle_check else None
    if gate and not os.access(gate, os.X_OK):
        raise ValueError("Idle check must be executable")
    if args.queue.exists():
        raise FileExistsError("Queue already exists. Use campaign resume.")
    folders = [p.expanduser().resolve(strict=True) for p in args.rom_dir or ()]
    for folder in folders:
        if not folder.is_dir():
            raise ValueError(f"--rom-dir requires a directory: {folder}")
    paths = [p.expanduser().resolve(strict=True) for p in args.rom or ()] + folders
    batch = any(p.is_dir() or p.suffix.lower() == ".zip" for p in paths)
    emulator = args.emulator or ("all" if batch and not (args.core or args.version) else "mgba")
    if emulator == "all" and (args.core or args.version):
        raise ValueError("Select one emulator when pinning a particular core or version")
    if args.version and emulator != "mgba":
        raise ValueError("For SNES select --core PATH or --latest-core")
    if args.carts_core and (emulator!="all" or args.core):
        raise ValueError("--carts-core requires --emulator all")
    if args.circuit:
        if paths or args.carter:
            raise ValueError("Circuit generates its own cartridges")
        peers = ["mgba","snes9x","bsnes"] + (["cartssnes"] if args.carts_core else []) if emulator=="all" else [emulator]
        workloads=[]
        for peer in peers:
            for scene in circuit.SCENES:
                if scene.console!=("gba" if peer=="mgba" else "snes") or args.circuit not in ("all",scene.level):
                    continue
                rom=circuit.cartridge(scene.console,scene.level)
                workloads.append(dict(path=str(rom),sha256=scene.digest,emulator=peer,scene=scene.profile))
    elif args.carter:
        if batch or emulator == "all" or len(paths) > 1:
            raise ValueError("A Carter queue accepts one emulator and one pinned cartridge")
        console = "gba" if emulator == "mgba" else "snes"
        rom = carter.cartridge(console, paths[0] if paths else None)
        workloads = [dict(path=str(rom), sha256=carter.GAMES[console].digest, emulator=emulator, scene=scene.profile)
                     for scene in carter.SCENES if scene.console == console and args.carter in ("all", scene.level)]
    elif not paths:
        raise ValueError("Supply --rom, --rom-dir or --carter")
    elif batch or emulator == "all":
        workloads = library.discover(paths, emulator)
        if args.carts_core:
            workloads.extend([dict(w,emulator="cartssnes") for w in workloads if w["emulator"]=="snes9x"])
    else:
        workloads = []
        for path in dict.fromkeys(paths):
            scores.validate_file(path, emulator)
            workloads.append(dict(path=str(path), sha256=engines.digest(path), emulator=emulator))

    cores = {}
    for peer in dict.fromkeys(w["emulator"] for w in workloads):
        tag = commit = None
        if peer=="cartssnes" and args.carts_core:
            core=args.carts_core.expanduser().resolve(strict=True)
        elif args.core:
            core = args.core.expanduser().resolve(strict=True)
        elif peer == "mgba" and (args.version or args.circuit and not args.latest_core or not (args.latest_core or args.carter or batch or emulator == "all")):
            core, meta = engines.install(args.version or engines.REFERENCE)
            tag, commit = meta["tag"], meta["commit"]
        else:
            core = downloads.latest_core(peer)
        cores[peer] = dict(path=str(core), sha256=engines.digest(core), tag=tag, commit=commit)
    engines.worker()
    plan = dict(share_title=args.share_title, campaign_id=str(uuid.uuid4()), workloads=workloads, cores=cores, warmup=args.warmup_frames, frames=args.frames,
                timeout=args.timeout, loop=args.loop, days=args.days, idle_check=gate,
                dedicated=args.dedicated, idle_seconds=args.idle_seconds)
    if args.circuit:
        plan["worker_sha256"]=engines.digest(engines.worker())
        plan["chips"]={peer:chips.run(peer,Path(build["path"])) for peer,build in cores.items() if peer!="mgba"}
    if args.carter:
        plan["accuracy"] = accuracy.run(emulator, Path(cores[emulator]["path"]))
    dest = args.queue.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp) / "queue.sqlite"
        with closing(sqlite3.connect(stage)) as db, db:
            db.execute("CREATE TABLE campaign (plan TEXT, started REAL, state TEXT, heartbeat REAL)")
            db.execute("INSERT INTO campaign VALUES (?, NULL, 'ready', NULL)", (json.dumps(plan),))
            db.execute("""CREATE TABLE jobs (id INTEGER PRIMARY KEY, round INTEGER, rom INTEGER,
                          status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0,
                          available REAL DEFAULT 0, error TEXT, result TEXT, UNIQUE(round,rom))""")
            db.execute("CREATE INDEX pending_jobs ON jobs(id) WHERE status='pending'")
            db.execute("CREATE TABLE failures (job INTEGER, time REAL, reason TEXT)")
            enqueue(db, plan, 1)
        os.link(stage, dest)
    print(f"Shared campaign (when uploads are enabled): {uploads.service.ORIGIN}/campaign/{plan['campaign_id']}")
    print(f"Created {dest} with {len(workloads)} jobs in round 1")


def enqueue(db, plan, number):
    db.executemany("INSERT INTO jobs(round,rom) VALUES (?,?)",
                   ((number, i) for i in range(len(plan["workloads"]))))


def idle_gate(plan):
    if plan["dedicated"]:
        return lambda: True
    if plan["idle_check"]:
        def external():
            try:
                return subprocess.run([plan["idle_check"]], timeout=4, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                return False
        return external
    if sys.platform != "darwin":
        raise ValueError("The queue's idle policy needs macOS")
    quartz = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    idle = quartz.CGEventSourceSecondsSinceLastEventType
    idle.argtypes = [ctypes.c_int, ctypes.c_uint32]
    idle.restype = ctypes.c_double
    return lambda: idle(1, 0xffffffff) >= plan["idle_seconds"]


def state(db, message):
    db.execute("UPDATE campaign SET state=?, heartbeat=?", (message, time.time()))


def resume(db, path, plan):
    engines.home().mkdir(parents=True, exist_ok=True)
    if "workloads" not in plan:
        # Preserve job indices, pinned builds and Carter scene identity in v0.4 and older queues.
        emulator = plan.get("emulator", "mgba")
        plan["cores"] = {emulator: dict(path=plan["core"], sha256=plan["core_hash"],
                                        tag=plan.get("version"), commit=plan["commit"])}
        plan["workloads"] = [dict(path=p, sha256=digest, emulator=emulator)
                             for p, digest in plan["roms"]]
        for workload, scene in zip(plan["workloads"], plan.get("scenes", ())):
            workload["scene"] = scene
    ready = idle_gate(plan)
    for build in plan["cores"].values():
        if engines.digest(Path(build["path"])) != build["sha256"]:
            raise ValueError("A selected core has changed. Create a queue for the new build.")
    with db:
        db.execute("UPDATE campaign SET started=COALESCE(started,?)", (time.time(),))
    start = db.execute("SELECT started FROM campaign").fetchone()[0]
    deadline = start + plan["days"] * 86400 if plan["days"] else float("inf")
    last_message = None
    while True:
        wait = 0
        finished = False
        with db:
            # A second coordinator waits for this transaction. An abrupt stop
            # rolls an unfinished job back to pending, including its retry count.
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            job = db.execute("SELECT id,round,rom,attempts FROM jobs WHERE status='pending' AND available<=? ORDER BY id LIMIT 1", (now,)).fetchone()
            if now >= deadline:
                message, finished = "deadline reached", True
            elif not job:
                if db.execute("SELECT 1 FROM jobs WHERE status='pending' LIMIT 1").fetchone():
                    message, wait = "waiting for retry", 5
                elif plan["loop"]:
                    # Permanently failing jobs stay held across rounds until a targeted retry.
                    number = db.execute("SELECT MAX(round) FROM jobs").fetchone()[0] + 1
                    held = {r[0] for r in db.execute("SELECT DISTINCT rom FROM jobs WHERE status='held'")}
                    eligible = [i for i in range(len(plan["workloads"])) if i not in held]
                    if eligible:
                        db.executemany("INSERT INTO jobs(round,rom) VALUES (?,?)", [(number, i) for i in eligible])
                        message = f"starting round {number}"
                    else:
                        message, finished = "all remaining jobs need review", True
                else:
                    message, finished = "queue finished", True
            elif min(shutil.disk_usage(p).free for p in (path.parent, engines.home(), tempfile.gettempdir())) < 256 * 1024**2:
                message, wait = "waiting for disk space", 30
            elif not ready() or (sys.platform == "darwin" and not plan["dedicated"] and not plan["idle_check"]
                                 and os.getloadavg()[0] >= max(1.0, (os.cpu_count() or 1) * .5)):
                message, wait = "waiting for idle", 15
            else:
                job_id, number, idx, attempts = job
                workload = plan["workloads"][idx]
                emulator = workload["emulator"]
                build = plan["cores"][emulator]
                rom = Path(workload["path"])
                local_name = Path(workload.get("member", rom.name)).name
                print(f"Round {number}, job {job_id}: {local_name} ({emulator})", flush=True)
                try:
                    with journal.attempt(Path(local_name), build["tag"] or "local core", f"round {number}, job {job_id}") as (run_id, started):
                        public_scene = circuit.PROFILES.get(workload.get("scene"))
                        scene = public_scene or carter.PROFILES.get(workload.get("scene"))
                        if "scene" in workload and not scene:
                            raise ValueError("Unrecognized campaign scene")
                        result = scores.measure(rom, None, Path(build["path"]), scene.warmup if scene else plan["warmup"],
                                                circuit.FRAMES if public_scene else carter.FRAMES if scene else plan["frames"], plan["timeout"],
                                                lambda: time.time() < deadline and ready(), workload["sha256"],
                                                emulator, scene=scene, member=workload.get("member"))
                        if public_scene:
                            if result["worker_sha256"] != plan["worker_sha256"]:
                                raise ValueError("Circuit worker changed since the campaign was created")
                            if emulator in plan["chips"]:
                                result["chips"]=plan["chips"][emulator]
                        elif scene:
                            result["accuracy"] = accuracy.validated(plan["accuracy"],scene.console,
                                                                   result["core_sha256"],result["worker_sha256"])
                        if result["core_sha256"] != build["sha256"]:
                            raise ValueError("Core changed during campaign")
                        result["share_title"] = plan.get("share_title", False)
                        if plan.get("campaign_id"):
                            result["campaign_id"] = plan["campaign_id"]
                        result["source_commit"] = build["commit"]
                        if emulator=="mgba" and build["tag"] and build["commit"]:
                            result["build_recipe"]="mgba-libretro-cmake-v1"
                        result.update(id=run_id, local_name=scene.title if scene else local_name, started_utc=started, finished_utc=journal.now())
                        # The job, journal and pending upload must survive a restart together.
                        # Attach only after measurement, which uses its own device journal connection.
                        db.execute("ATTACH DATABASE ? AS device", (str(engines.home() / "history.sqlite"),))
                        try:
                            with db:
                                db.execute("UPDATE jobs SET status='done',result=?,error=NULL WHERE id=?",
                                           (json.dumps(result, separators=(",", ":")), job_id))
                                journal.record_completion(db, result, f"{path} (export job {job_id})")
                        finally:
                            db.execute("DETACH DATABASE device")
                    message = f"saved job {job_id}"
                except scores.InterruptedWindow as exc:
                    message, wait = str(exc), 10
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    db.execute("INSERT INTO failures VALUES (?,?,?)", (job_id, time.time(), str(exc)[:240]))
                    attempts += 1
                    status = "held" if attempts >= 3 else "pending"
                    db.execute("UPDATE jobs SET status=?,attempts=?,available=?,error=? WHERE id=?",
                               (status, attempts, now + 30 * attempts, str(exc)[:240], job_id))
                    message = f"job {job_id}: {status} after attempt {attempts}"
            state(db, message)
        if message != last_message:
            print(message, flush=True)
            last_message = message
        uploads.flush(limit=None if finished else 3)
        if finished:
            return
        if wait:
            time.sleep(min(wait, max(0, deadline - time.time())))


def execute(args):
    if args.action == "create":
        return create(args)
    path = args.queue.expanduser().resolve(strict=True)
    with closing(sqlite3.connect(path, timeout=3600)) as db:
        plan, state_name, heartbeat = db.execute("SELECT plan,state,heartbeat FROM campaign").fetchone()
        if args.action == "resume":
            if args.wait_uploads and not uploads.enabled():
                raise ValueError("Run 'emubench uploads enable' before using --wait-uploads")
            resume(db, path, json.loads(plan))
            if args.wait_uploads:
                uploads.wait_for_pending()
        elif args.action == "launch-agent":
            if sys.platform != "darwin":
                raise ValueError("Launch agents are for macOS")
            command = [sys.executable]
            if not getattr(sys, "frozen", False):
                command.extend(["-m", "emubench"])
            spec = {"Label": "org.emubench.campaign." + hashlib.sha256(str(path).encode()).hexdigest()[:12],
                    "ProgramArguments": [*command, "campaign", "resume", str(path)], "RunAtLoad": True,
                    "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 60,
                    "WorkingDirectory": str(Path(__file__).resolve().parent.parent) if not getattr(sys, "frozen", False) else str(path.parent),
                    "EnvironmentVariables": {"EMUBENCH_HOME": str(engines.home()), "PATH": os.environ.get("PATH", os.defpath)}}
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("xb") as f:
                plistlib.dump(spec, f)
            print(f"Wrote {args.out}. Load it on the intended Mac to enable resume at login.")
        elif args.action == "status":
            print(f"{state_name} · last checkpoint {time.ctime(heartbeat) if heartbeat else 'pending'}")
            for number, status, count in db.execute("SELECT round,status,count(*) FROM jobs GROUP BY round,status ORDER BY round,status"):
                print(f"round {number}  {status}: {count}")
            print("Recorded failures:", db.execute("SELECT COUNT(*) FROM failures").fetchone()[0])
            for i, error in db.execute("SELECT id,error FROM jobs WHERE status='held'"):
                print(f"job {i} held: {error}")
        elif args.action == "retry":
            with db:
                count = db.execute("UPDATE jobs SET status='pending',available=0,attempts=0 WHERE id=? AND status='held'", (args.job,)).rowcount
                if not count:
                    raise ValueError("Choose a held job ID from campaign status")
        else:
            row = db.execute("SELECT result FROM jobs WHERE id=? AND status='done'", (args.job,)).fetchone()
            if not row:
                raise ValueError("Choose a completed job ID")
            print(scores.save(json.loads(row[0]), args.out))
