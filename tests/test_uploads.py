import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import subprocess
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import patch

from emubench import journal, scores, uploads


class AutomaticUploads(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, EMUBENCH_HOME=folder.name)
        env.start()
        self.addCleanup(env.stop)
        for redirect in (redirect_stdout, redirect_stderr):
            capture = redirect(io.StringIO())
            capture.__enter__()
            self.addCleanup(capture.__exit__, None, None, None)
        self.url = "https://github.com/MrCTO13/EmuBench/issues/7"

    def completed(self, title="Personal ROM"):
        rom = Path("Private Game Name.gba")
        with journal.attempt(rom, "mgba") as (run_id, started):
            result = dict(schema=1, id=run_id, local_name=rom.name, finished_utc=journal.now(), started_utc=started,
                          emulator="mGBA", profile=scores.PROFILE, version="0.10.5", source_commit=None,
                          core_sha256="a"*64, worker_sha256="b"*64, rom_sha256="private cartridge hash",
                          system="Linux", arch="x86_64", frames=100, rendered_frames=100, warmup_frames=30,
                          audio_sample_frames=200, frame_ns=[100000]*100)
            result.update(scores.stats(result["frame_ns"]))
            journal.complete(result, str(rom), title)
        return run_id

    def queued(self):
        with journal.database() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM score_outbox ORDER BY rowid")]

    def test_opt_in_has_no_backfill_and_filter_is_shared(self):
        self.completed()
        uploads.configure(True)
        self.assertEqual(self.queued(), [])
        run_id = self.completed()
        shared = self.queued()[0]
        self.assertEqual(shared["run_id"], run_id)
        self.assertEqual(shared["game"], "Personal ROM")
        for field in ("rom_sha256", "frame_ns", "local_name", "started_utc", "finished_utc"):
            self.assertNotIn(field, shared)
        self.assertNotIn("Private Game Name", json.dumps(shared))
        self.completed("Public display title")
        self.assertEqual(self.queued()[1]["game"], "Public display title")
        uploads.configure(False)
        uploads.configure(True)
        self.assertEqual(self.queued(), [])

    def test_offline_retry_and_repeated_sync(self):
        uploads.configure(True)
        self.completed()
        with patch.object(scores, "publish", side_effect=[FileNotFoundError(), self.url]) as send:
            self.assertFalse(uploads.flush())
            uploads.flush()
            self.assertEqual(send.call_count, 1)
            self.assertEqual(len(self.queued()), 1)
            self.assertTrue(uploads.flush(force=True))
            uploads.flush(force=True)
            self.assertEqual(send.call_count, 2)
            self.assertEqual(self.queued(), [])

    def test_concurrent_sync_and_expired_claim(self):
        uploads.configure(True)
        self.completed()
        uploads.claim(False)  # Previous process stopped before delivery.
        self.assertIsNone(uploads.claim(True))
        with journal.database() as db:
            db.execute("UPDATE upload_settings SET lease_until=0")
        claimed, resume = Event(), Event()
        def send(record):
            claimed.set()
            self.assertTrue(resume.wait(5))
            return self.url
        with patch.object(scores, "publish", side_effect=send) as post:
            thread = Thread(target=uploads.flush)
            thread.start()
            try:
                self.assertTrue(claimed.wait(5))
                uploads.flush(force=True)
            finally:
                resume.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(post.call_count, 1)
        self.assertEqual(self.queued(), [])

    def test_lost_post_response_before_search_indexes_issue(self):
        uploads.configure(True)
        run_id = self.completed()
        issue = dict(title=f"[Score {run_id}] Personal ROM", html_url=self.url)
        gets = [b'{"items":[]}', b'[]', b'{"items":[]}', json.dumps([issue]).encode()]
        with patch("subprocess.check_output", side_effect=gets), \
                patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh api", 40)) as post:
            self.assertFalse(uploads.flush())
            self.assertTrue(uploads.flush(force=True))
            self.assertEqual(post.call_count, 1)
        self.assertEqual(self.queued(), [])
