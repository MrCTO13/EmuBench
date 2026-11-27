"""Per-device attempt journal. Filenames and timestamps here are private by default."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import sqlite3
import uuid
from . import engines


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@contextmanager
def database():
    root = engines.home()
    root.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root / "history.sqlite", timeout=30)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS attempts
            (id TEXT PRIMARY KEY, game TEXT, build TEXT, started TEXT, finished TEXT,
             outcome TEXT, context TEXT, result TEXT, reason TEXT, avg REAL, low REAL, high REAL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS upload_settings
            (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
             retry_after REAL NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
             lease TEXT, lease_until REAL NOT NULL DEFAULT 0, last_error TEXT)""")
        db.execute("CREATE TABLE IF NOT EXISTS score_outbox (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS attempt_metrics(id TEXT PRIMARY KEY, speed REAL, accuracy TEXT, spread REAL)")
        yield db


def comparison_id(rom_hash):
    if rom_hash=="installation":
        from . import attest
        return attest.device(attest.identity()[0])
    # The public token links runs of one exact image in this device journal.
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS workloads (hash TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL)")
        db.execute("INSERT OR IGNORE INTO workloads VALUES (?,?)", (rom_hash, str(uuid.uuid4())))
        return db.execute("SELECT token FROM workloads WHERE hash=?", (rom_hash,)).fetchone()[0]


@contextmanager
def attempt(rom, build, context="single run"):
    run_id, started = str(uuid.uuid4()), now()
    with database() as db:
        db.execute("INSERT INTO attempts(id,game,build,started,outcome,context) VALUES (?,?,?,?,?,?)",
                   (run_id, rom.name, build, started, "unfinished", context))
    try:
        yield run_id, started
    except BaseException as exc:
        with database() as db:
            db.execute("UPDATE attempts SET finished=?,outcome=?,reason=? WHERE id=?",
                       (now(), "interrupted" if isinstance(exc, (KeyboardInterrupt, InterruptedError)) else "failed",
                        str(exc)[:300], run_id))
        raise


def record_completion(db, result, location, title="Personal ROM"):
    from . import uploads
    db.execute("""UPDATE attempts SET finished=?,outcome='completed',build=?,result=?,avg=?,low=?,high=?
                  WHERE id=?""", (result["finished_utc"], result["emulator"] + " " + result["version"], str(location),
                  result["average_fps"], result["low_1pct_fps"], result["high_1pct_fps"], result["id"]))
    from .accuracy import coverage
    db.execute("INSERT OR REPLACE INTO attempt_metrics VALUES(?,?,?,?)",
               (result["id"],result.get("speed_x"),coverage(result),result.get("repeatability",{}).get("relative_spread")))
    uploads.enqueue(db, result, title)


def complete(result, location, title="Personal ROM"):
    with database() as db:
        record_completion(db, result, location, title)


def history(game, limit):
    if not 1 <= limit <= 10000:
        raise ValueError("Choose a limit from 1 to 10,000")
    with database() as db:
        rows = db.execute("""SELECT started,finished,game,build,outcome,context,result,reason,avg,low,high,speed,accuracy,spread FROM attempts LEFT JOIN attempt_metrics USING(id)
                          WHERE instr(lower(game),lower(?)) > 0 ORDER BY started DESC,attempts.rowid DESC LIMIT ?""", (game, limit))
        count = 0
        for start, end, name, version, outcome, context, location, error, avg, low, high, speed, accuracy, spread in rows:
            count += 1
            print(f"{start} .. {end or '?'}  {name}  {version}  {outcome}  ({context})")
            if avg is not None:
                label=f"{speed:.2f}×" if speed is not None else "Unscored"
                spread_label=f" · spread {spread:.1%}" if spread is not None else ""
                print(f"  {label} · {accuracy or 'Untested'}{spread_label} · {avg:.0f} avg / {low:.0f} low / {high:.0f} high FPS")
            if location or error:
                print(" ", location or error)
        if not count:
            print("No matching attempts on this device.")
