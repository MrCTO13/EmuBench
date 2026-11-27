import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from emubench import details, journal, scores


class Comparison(unittest.TestCase):
    def test_token_is_stable_per_device_and_edition(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            with patch.dict(os.environ, EMUBENCH_HOME=first):
                token = journal.comparison_id("one")
                self.assertEqual(journal.comparison_id("one"), token)
                self.assertNotEqual(journal.comparison_id("two"), token)
            with patch.dict(os.environ, EMUBENCH_HOME=second):
                self.assertNotEqual(journal.comparison_id("one"), token)

    def test_public_snes_and_legacy(self):
        token = str(uuid.uuid4())
        data = dict(schema=2, window=dict(loops=1,timed_ns=1,minimum_ns=10**10,loops_identical=True), id=str(uuid.uuid4()), profile="snes-boot-no-input-v1", emulator="bsnes",
                    version="115", system="Linux", arch="x86_64", source_commit=None,
                    worker_sha256="1"*64, core_sha256="2"*64, rom_sha256="private-hash",
                    frames=100, rendered_frames=100, frame_ns=[1000000]*100, warmup_frames=120,
                    audio_sample_frames=100, comparison_id=token)
        self.assertEqual(scores.public_fields(data,"Color test")["comparison_id"], token)
        with self.assertRaises(ValueError):
            scores.public_fields({**data,"emulator":"mGBA"}, "Color test")
        with self.assertRaises(ValueError):
            scores.public_fields({**data,"comparison_id":"invalid"}, "Color test")
        del data["comparison_id"]
        self.assertNotIn("comparison_id", scores.public_fields(data, "Color test"))

    def test_snapshot_html_contains_only_escaped_embedded_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"comparison.html"
            records = [{"game":"</script><h1>local name"}]
            details.write_embedded(records, path)
            html = path.read_text(encoding="utf-8")
            self.assertNotIn(records[0]["game"],html)
            data = html.split('id="run-data">',1)[1].split('</script>',1)[0]
            self.assertEqual(json.loads(data),records)
            self.assertIn("function comparisonKey", html)
            with self.assertRaises(FileExistsError):
                details.write_embedded(records, path)
