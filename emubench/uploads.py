"""Per-device opt-in and a durable queue of public score summaries."""
import json
import sqlite3
import subprocess
import sys
import time
import uuid

from . import journal, scores


def enqueue(db, result, title):
    if not db.execute("SELECT 1 FROM upload_settings WHERE enabled=1").fetchone():
        return
    try:
        summary = scores.public_fields(result, title)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"Saved locally. This score cannot be uploaded: {exc}", file=sys.stderr)
        return
    db.execute("INSERT OR IGNORE INTO score_outbox(id,payload) VALUES (?,?)",
               (summary["run_id"], json.dumps(summary, separators=(",", ":"))))


def configure(enabled):
    with journal.database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""INSERT INTO upload_settings(id,enabled) VALUES(1,?)
                      ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled""", (int(enabled),))
        if not enabled:
            db.execute("DELETE FROM score_outbox")
            db.execute("UPDATE upload_settings SET lease=NULL,lease_until=0,retry_after=0,failures=0,last_error=NULL")


def enabled():
    with journal.database() as db:
        return bool(db.execute("SELECT 1 FROM upload_settings WHERE enabled=1").fetchone())


def wait_for_pending():
    announced = False
    while True:
        with journal.database() as db:
            pending = db.execute("""SELECT max(retry_after,lease_until) FROM upload_settings
                                     WHERE enabled=1 AND EXISTS (SELECT 1 FROM score_outbox)""").fetchone()
        if not pending:
            return
        if not announced:
            print("Measurements finished. Waiting for queued score uploads.", flush=True)
            announced = True
        delay = pending[0] - time.time()
        if delay > 0:
            time.sleep(min(delay, 30))
        else:
            flush(limit=3)


def status():
    with journal.database() as db:
        row = db.execute("SELECT enabled,retry_after,last_error FROM upload_settings").fetchone()
        pending = db.execute("SELECT count(*) FROM score_outbox").fetchone()[0]
    print(f"Automatic uploads {'on' if row and row[0] else 'off'} · {pending} queued")
    print(f"Public scoreboard: https://github.com/{scores.REPOSITORY}/issues")
    if row and row[2]:
        print("Last upload:", row[2])
        print("Next automatic retry after", time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(row[1])))


def claim(force):
    with journal.database() as db:
        db.execute("BEGIN IMMEDIATE")
        now = time.time()
        setting = db.execute("""SELECT failures FROM upload_settings WHERE enabled=1
                                AND lease_until<=? AND (retry_after<=? OR ?)""", (now, now, force)).fetchone()
        if not setting:
            return None
        item = db.execute("SELECT id,payload FROM score_outbox ORDER BY rowid LIMIT 1").fetchone()
        if not item:
            return None
        token = str(uuid.uuid4())
        # Covers the publisher's SQLite lock wait and both bounded GitHub requests.
        db.execute("UPDATE upload_settings SET lease=?,lease_until=?", (token, now + 180))
        return token, setting[0], item[0], json.loads(item[1])


def finish(token, run_id, failures, error=None):
    with journal.database() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM upload_settings WHERE lease=?", (token,)).fetchone():
            return
        delay = min(3600, 60 * 2 ** min(failures, 6)) if error else 0
        if not error:
            db.execute("DELETE FROM score_outbox WHERE id=?", (run_id,))
        db.execute("""UPDATE upload_settings SET lease=NULL,lease_until=0,retry_after=?,failures=?,last_error=?""",
                   (time.time() + delay if error else 0, failures + 1 if error else 0, error))


def flush(force=False, limit=None):
    sent = 0
    while limit is None or sent < limit:
        claimed = claim(force)
        if not claimed:
            return True
        token, failures, run_id, summary = claimed
        try:
            url = scores.publish(summary)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, subprocess.SubprocessError) as exc:
            error = "GitHub CLI unavailable" if isinstance(exc, FileNotFoundError) else type(exc).__name__
            finish(token, run_id, failures, error)
            print(f"Score queued for retry ({error}). Check connectivity and gh auth status.", file=sys.stderr)
            return False
        finish(token, run_id, failures)
        print(f"Uploaded score: {url}", flush=True)
        sent += 1
    return True
