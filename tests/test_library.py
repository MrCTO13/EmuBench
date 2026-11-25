from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from emubench import library, scores


class Library(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "My library"
        self.root.mkdir()
        self.log = StringIO()
        for context in (redirect_stderr, redirect_stdout):
            capture = context(self.log)
            capture.__enter__()
            self.addCleanup(capture.__exit__, None, None, None)

    def test_nested_mixed_files_zip_members_duplicates_and_filtering(self):
        sub = self.root / "Europe" / "Pack"
        sub.mkdir(parents=True)
        gba = bytes.fromhex("2e0000ea") + b"g"*508
        snes = b"s"*32768
        (self.root/"outside.GbA").write_bytes(gba)
        (sub/"notes.txt").write_text("irrelevant")
        with ZipFile(sub/"mixed.ZIP", "w", ZIP_DEFLATED) as pack:
            pack.writestr("alias.gba", gba)
            pack.writestr("__MACOSX/game.sfc", snes)
            pack.writestr("asia/one.SMC", snes)
            pack.writestr("world/other.gba", gba + b"v")
            pack.writestr("too-small.sfc", b"")
        (sub/"corrupt.zip").write_bytes(b"bad")
        runs = library.discover([self.root, sub], "all")
        self.assertEqual([r["emulator"] for r in runs], ["mgba", "gpsp", "snes9x", "bsnes", "mgba", "gpsp"])
        self.assertEqual(runs[2]["member"], "asia/one.SMC")
        self.assertEqual(runs[3]["sha256"], runs[2]["sha256"])
        self.assertIn("1 duplicate", self.log.getvalue())
        self.assertIn("2 unreadable", self.log.getvalue())
        self.assertEqual(len(library.discover([self.root],"snes9x")), 1)
        self.assertEqual(library.read_pinned_member(sub/"mixed.ZIP","asia/one.SMC","bsnes"), snes)
        with ZipFile(sub/"mixed.ZIP","w") as changed:
            changed.writestr("asia/one.SMC", b"x"*32768)
        with self.assertRaisesRegex(ValueError, "ROM changed"):
            scores.measure(sub/"mixed.ZIP", None, None, 0, 100, 30, emulator="bsnes",
                           expected_rom=runs[3]["sha256"], member=runs[2]["member"])

    def test_empty_and_symlink_loop(self):
        with self.assertRaisesRegex(ValueError,"No compatible"):
            library.discover([self.root],"all")
        external = self.root.parent/"private.gba"
        external.write_bytes(b"a"*512)
        try:
            (self.root/"loop").symlink_to(self.root, target_is_directory=True)
            (self.root/"link.gba").symlink_to(external)
        except OSError:
            self.skipTest("Symlinks unavailable here")
        with self.assertRaisesRegex(ValueError,"No compatible"):
            library.discover([self.root],"all")
