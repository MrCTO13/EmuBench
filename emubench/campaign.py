"""A private, restartable queue. Each finished measurement is one SQLite transaction."""
from contextlib import closing
import ctypes
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
from . import engines, journal, scores


def arguments(commands):
    group = commands.add_parser("campaign", help="Create, resume or inspect an unattended local queue")
    actions = group.add_subparsers(dest="action", required=True)
    new = actions.add_parser("create")
    new.add_argument("queue", type=Path)
    new.add_argument("--rom", type=Path, action="append", required=True)
    build = new.add_mutually_exclusive_group()
    build.add_argument("--version", default=None)
    build.add_argument("--core", type=Path)
    new.add_argument("--warmup-frames", type=int, default=120)
    new.add_argument("--frames", type=int, default=1800)
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
        if name in ("retry", "export"):
            p.add_argument("--job", type=int, required=True)
        if name in ("export", "launch-agent"):
            p.add_argument("--out", required=True, type=Path)


def create(args):
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
    roms = []
    for path in dict.fromkeys(p.expanduser().resolve(strict=True) for p in args.rom):
        if path.suffix.lower() != ".gba" or not path.is_file() or not 192 <= path.stat().st_size <= 32 * 1024**2:
            raise ValueError(f"Invalid GBA ROM: {path.name}")
        roms.append([str(path), engines.digest(path)])
    if args.core:
        core = args.core.expanduser().resolve(strict=True)
        commit = None
    else:
        core, meta = engines.install(args.version or engines.REFERENCE)
        commit = meta["commit"]
    engines.worker()  # Finish compilation before making the queue eligible.
    plan = dict(roms=roms, core=str(core), core_hash=engines.digest(core), commit=commit,
                version=meta["tag"] if not args.core else None, warmup=args.warmup_frames, frames=args.frames, timeout=args.timeout, loop=args.loop,
                days=args.days, idle_check=gate, dedicated=args.dedicated, idle_seconds=args.idle_seconds)
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
            db.execute("CREATE TABLE failures (job INTEGER, time REAL, reason TEXT)")
            enqueue(db, plan, 1)
        os.link(stage, dest)
    print(f"Created {dest} with {len(roms)} jobs in round 1")


def enqueue(db, plan, number):
    db.executemany("INSERT INTO jobs(round,rom) VALUES (?,?)",
                   ((number, i) for i in range(len(plan["roms"]))))


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
    ready = idle_gate(plan)
    core = Path(plan["core"])
    if engines.digest(core) != plan["core_hash"]:
        raise ValueError("The selected core has changed. Create a queue for the new build.")
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
                    eligible = [i for i in range(len(plan["roms"])) if i not in held]
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
                rom, rom_hash = plan["roms"][idx]
                print(f"Round {number}, job {job_id}", flush=True)
                try:
                    with journal.attempt(Path(rom), plan.get("version") or "local core", f"round {number}, job {job_id}") as (run_id, started):
                        result = scores.measure(Path(rom), None, core, plan["warmup"], plan["frames"],
                                                plan["timeout"], lambda: time.time() < deadline and ready(), rom_hash)
                        if result["core_sha256"] != plan["core_hash"]:
                            raise ValueError("Core changed during campaign")
                        result["source_commit"] = plan["commit"]
                        result.update(id=run_id, local_name=Path(rom).name, started_utc=started, finished_utc=journal.now())
                        db.execute("UPDATE jobs SET status='done',result=?,error=NULL WHERE id=?",
                                   (json.dumps(result, separators=(",", ":")), job_id))
                        db.commit()
                        journal.complete(result, f"{path} (export job {job_id})")
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
            resume(db, path, json.loads(plan))
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
                    "EnvironmentVariables": {"EMUBENCH_HOME": str(engines.home())}}
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
