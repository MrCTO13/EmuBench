import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess
from emubench import scores


class Scores(unittest.TestCase):
    def setUp(self):
        self.trace = {"schema": 2, "window":{"loops":1,"timed_ns":1,"minimum_ns":10000000000,"loops_identical":True}, "id": str(uuid.uuid4()), "emulator": "mGBA",
                      "profile": scores.PROFILE, "version": "0.10.5", "source_commit": None,
                      "core_sha256": "a"*64, "worker_sha256": "b"*64, "rom_sha256": "private",
                      "system": "Linux", "arch": "x86_64", "frames": 100, "rendered_frames": 100,
                      "warmup_frames": 10, "audio_sample_frames": 800, "frame_ns": [i*100000 for i in range(1,101)]}

    def test_percentiles_and_privacy(self):
        fields = scores.public_fields(self.trace, "A game")
        self.assertEqual(fields["low_1pct_fps"], 101)
        self.assertEqual(fields["high_1pct_fps"], 10000)
        self.assertEqual(fields["average_fps"], 198)
        self.assertNotIn("rom_sha256", fields)
        self.assertNotIn("frame_ns", fields)
        self.trace["rendered_frames"] -= 1
        with self.assertRaises(ValueError):
            scores.public_fields(self.trace, "A game")

    def test_upload_receipt_and_payload(self):
        public = scores.public_fields(self.trace, "A game")
        url = "https://github.com/MrCTO13/EmuBench/issues/13"
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, EMUBENCH_HOME=folder), \
             patch("subprocess.check_output", side_effect=[b'{"items":[]}', b'[]']), \
             patch("subprocess.run", return_value=CompletedProcess([], 0, json.dumps({"html_url":url}).encode())) as post:
            self.assertEqual(scores.publish(public), url)
            self.assertEqual(scores.publish(public), url)
            self.assertEqual(post.call_count, 1)
            payload = json.loads(post.call_args.kwargs["input"])
            self.assertIn("1% low FPS", payload["body"])
            self.assertNotIn("private", payload["body"])

    def test_never_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "score.json"
            scores.save(self.trace, dest)
            with self.assertRaises(FileExistsError):
                scores.save(self.trace, dest)

    def test_single_frame_dip_is_visible(self):
        from emubench.details import timeline
        frames = [1_000_000] * 1800
        frames[707] = 40_000_000
        bins = timeline(frames)
        slow = max(bins, key=lambda b: b["worst_ms"])
        self.assertLessEqual(len(bins), 120)
        self.assertEqual(slow["worst_frame"], 708)
        self.assertEqual(slow["worst_ms"], 40)
        self.assertEqual(slow["worst_fps"], 25)
        self.assertEqual(slow["worst_at_ms"], 747)
        self.assertAlmostEqual(bins[-1]["end_ms"], sum(frames)/1e6)
