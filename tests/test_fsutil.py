"""The private home must work on vfat/exFAT SD cards, which refuse hard links."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from emubench import attest, fsutil, scores

REAL_LINK = os.link


def refused(*args, **kwargs):
    raise PermissionError(errno.EPERM, "Operation not permitted")


class NoHardLinks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.env = mock.patch.dict(os.environ, {"EMUBENCH_HOME": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    def leftovers(self):
        return sorted(p.name for p in self.root.iterdir() if p.name != "installation.secret")

    def test_identity_falls_back_to_rename(self):
        with mock.patch("os.link", side_effect=refused):
            key, _ = attest.identity()
            again, _ = attest.identity()
        secret = self.root / "installation.secret"
        self.assertEqual(len(secret.read_bytes()), 64)
        self.assertEqual(key.encode(), again.encode())
        self.assertEqual(self.leftovers(), [])

    def test_existing_identity_is_never_overwritten(self):
        secret = self.root / "installation.secret"
        secret.write_bytes(b"k" * 64)
        stage = self.root / "stage"
        stage.write_bytes(b"x" * 64)
        with mock.patch("os.link", side_effect=refused), self.assertRaises(FileExistsError):
            fsutil.publish_new(stage, secret)
        self.assertEqual(secret.read_bytes(), b"k" * 64)

    def test_failed_rename_leaves_no_partial_secret(self):
        with mock.patch("os.link", side_effect=refused), \
                mock.patch("os.rename", side_effect=OSError(errno.EIO, "I/O error")), \
                self.assertRaises(OSError):
            attest.identity()
        self.assertFalse((self.root / "installation.secret").exists())
        self.assertEqual(self.leftovers(), [])

    def test_other_link_errors_still_raise(self):
        stage = self.root / "stage"
        stage.write_bytes(b"x")
        with mock.patch("os.link", side_effect=OSError(errno.ENOSPC, "No space")), self.assertRaises(OSError):
            fsutil.publish_new(stage, self.root / "dest")
        self.assertFalse((self.root / "dest").exists())

    def test_result_save_without_hard_links(self):
        dest = self.root / "out" / "run.json"
        with mock.patch("os.link", side_effect=refused):
            path = scores.save({"id": "run"}, dest)
            with self.assertRaises(FileExistsError):
                scores.save({"id": "other"}, dest)
        self.assertEqual(path.read_text(encoding="utf-8"), '{"id":"run"}')
        self.assertEqual(sorted(p.name for p in dest.parent.iterdir()), ["run.json"])

    def test_hard_links_still_used_where_supported(self):
        stage = self.root / "stage"
        stage.write_bytes(b"x")
        with mock.patch("os.link", wraps=REAL_LINK) as link:
            fsutil.publish_new(stage, self.root / "dest")
        link.assert_called_once()
        self.assertTrue(stage.exists())


if __name__ == "__main__":
    unittest.main()
