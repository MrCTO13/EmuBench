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
        yield db


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


def complete(result, location):
    with database() as db:
        db.execute("""UPDATE attempts SET finished=?,outcome='completed',build=?,result=?,avg=?,low=?,high=?
                      WHERE id=?""", (result["finished_utc"], result["version"], str(location),
                      result["average_fps"], result["low_1pct_fps"], result["high_1pct_fps"], result["id"]))


def history(game, limit):
    if not 1 <= limit <= 10000:
        raise ValueError("Choose a limit from 1 to 10,000")
    with database() as db:
        rows = db.execute("""SELECT started,finished,game,build,outcome,context,result,reason,avg,low,high FROM attempts
                          WHERE instr(lower(game),lower(?)) > 0 ORDER BY started DESC,rowid DESC LIMIT ?""", (game, limit))
        count = 0
        for start, end, name, version, outcome, context, location, error, avg, low, high in rows:
            count += 1
            print(f"{start} .. {end or '?'}  {name}  mGBA {version}  {outcome}  ({context})")
            if avg is not None:
                print(f"  {avg:.0f} avg / {low:.0f} low / {high:.0f} high FPS")
            if location or error:
                print(" ", location or error)
        if not count:
            print("No matching attempts on this device.")
