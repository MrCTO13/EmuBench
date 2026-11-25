"""Exercise resolver, download integrity, cache recovery and partial batch failure offline."""
import io
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from zlib import crc32

from emubench import downloads as dl
from emubench.catalog import CATALOG


def zipped(members):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


class Downloads(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        env = patch.dict(os.environ, EMUBENCH_HOME=folder.name)
        env.start()
        self.addCleanup(env.stop)
        self.member = "mgba_libretro.so"
        self.binary = b"\x7fELF\x02\x01" + b"\x00" * 12 + b"\x3e\x00" + b"native core"
        self.zip = zipped([(self.member, self.binary), ("../unused.txt", b"ignore other members")])
        self.spec = dl.Package("mgba", "linux-x64", "core", "nightly", self.member + ".zip",
                               "https://example.invalid/core.zip", "known", f"crc32:{crc32(self.binary):08x}",
                               member=self.member)

    def response(self, data, size=None):
        obj = io.BytesIO(data)
        obj.url = self.spec.url
        obj.headers = {"Content-Length": str(len(data) if size is None else size)}
        return obj

    def test_core_cache_reuse_and_repair(self):
        with patch.object(dl.engines, "open_upstream", side_effect=lambda req: self.response(self.zip)) as fetch:
            path, receipt = dl.obtain(self.spec)
            self.assertEqual(path.read_bytes(), self.binary)
            self.assertEqual(receipt["file_sha256"], sha256(self.binary).hexdigest())
            self.assertEqual(dl.obtain(self.spec)[0], path)
            self.assertEqual(fetch.call_count, 1)
            path.write_bytes(b"bad cache")
            self.assertEqual(dl.obtain(self.spec)[0].read_bytes(), self.binary)
            self.assertEqual(fetch.call_count, 2)
            self.assertFalse(list(self.root.rglob("unused.txt")))

    def test_concurrent_acquisition(self):
        with patch.object(dl.engines, "open_upstream", side_effect=lambda req: self.response(self.zip)), ThreadPoolExecutor(2) as pool:
            paths = list(pool.map(lambda _: dl.obtain(self.spec)[0], range(2)))
        self.assertEqual(paths[0], paths[1])
        self.assertEqual(paths[0].read_bytes(), self.binary)
        self.assertEqual(len(list(self.root.rglob("*.json"))), 1)

    def test_rollover_reloads_stale_index_and_checks_new_core(self):
        actual = f"{crc32(self.binary):08x}"
        urls = []

        def upstream(request):
            url = request.full_url
            urls.append(url)
            if ".index-extended" in url:
                crc = actual if "?refresh=" in url else "00000000"
                return self.response(f"2026-11-24 {crc} {self.member}.zip\n".encode())
            return self.response(self.zip)

        dl.core_index.cache_clear()
        self.addCleanup(dl.core_index.cache_clear)
        with patch.object(dl.engines, "open_upstream", side_effect=upstream), patch.object(dl.time, "sleep"):
            spec, path = dl.get("mgba", "linux-x64", "core")
        self.assertEqual(spec.checksum, "crc32:" + actual)
        self.assertEqual(path.read_bytes(), self.binary)
        self.assertEqual(len(urls), 4)
        self.assertTrue(urls[-1].endswith("?crc32=" + actual))
        self.assertEqual(len(list(self.root.rglob("*.json"))), 1)

    def test_invalid_core_never_promoted(self):
        for spec, payload in [(self.spec, zipped([("../"+self.member, self.binary)])),
                              (replace(self.spec, checksum="crc32:00000000"), self.zip),
                              (replace(self.spec, target="windows-x64"), self.zip)]:
            with self.subTest(target=spec.target, crc=spec.checksum), patch.object(
                    dl.engines, "open_upstream", return_value=self.response(payload)), self.assertRaises(ValueError):
                dl.obtain(spec)
        self.assertFalse(list(self.root.rglob("*.json")))
        self.assertFalse(list(self.root.rglob("*.so")))

    def test_transfer_length_and_sha(self):
        for response, spec in [(self.response(self.zip, 123456), self.spec),
                               (self.response(self.zip), replace(self.spec, checksum="sha256:"+"0"*64))]:
            with patch.object(dl.engines, "open_upstream", return_value=response), self.assertRaises(ValueError):
                dl.transfer(spec, self.root/"partial")

    def test_invalid_desktop_and_aliases(self):
        self.assertEqual(dl.emulator_id("Genesis Plus GX"), "genesis-plus-gx")
        self.assertEqual(dl.emulator_id("MGBA"), "mgba")
        self.assertEqual(dl.emulator_id("mednafen_pce_fast"), "beetle-pce-fast")
        with self.assertRaisesRegex(ValueError, "No published libretro core"):
            dl.resolve("duckstation", "linux-x64", "core")
        with self.assertRaisesRegex(ValueError, "Invalid release tag"):
            dl.resolve("mgba", "linux-x64", version="../main")
        with self.assertRaisesRegex(ValueError, "No matching desktop"):
            dl.resolve("fceumm", "macos-x64", version="0.1")
        payload = self.root / "payload"
        payload.write_bytes(b"This is HTML")
        with self.assertRaisesRegex(ValueError, "package format"):
            dl.prepare_file(replace(self.spec, name="game.exe", member=""), payload, self.root)

    def test_release_routing_and_ambiguous_asset(self):
        name = "mGBA-0.10.5-macos.dmg"
        asset = {"name": name, "browser_download_url": "https://github.com/mgba-emu/mgba/releases/download/0.10.5/"+name}
        with patch.object(dl, "release", return_value=("0.10.5", [asset])):
            self.assertEqual(dl.resolve("mgba","macos-arm64").channel, "desktop")
        with patch.object(dl, "release", return_value=("0.10.5", [asset, asset])), self.assertRaisesRegex(ValueError, "Multiple"):
            dl.resolve("mgba","macos-arm64")
        with patch.object(dl, "release", return_value=("0.10.5", [])), patch.object(
                dl, "core_index", return_value={self.member+".zip": ("2026-11-24", "aa00bb11")}):
            self.assertEqual(dl.resolve("mgba","linux-x64").checksum, "crc32:aa00bb11")
            with self.assertRaisesRegex(ValueError, "No matching desktop"):
                dl.resolve("mgba","linux-x64", version="0.10.5")

    def test_batch_continues_after_failure(self):
        with patch.object(dl, "get", side_effect=[ValueError("unavailable"), (self.spec, None)]) as fetch, \
                redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            self.assertEqual(dl.batch(["mgba","snes9x"], "linux-x64","auto","latest",True), 1)
            self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(CATALOG), 18)
