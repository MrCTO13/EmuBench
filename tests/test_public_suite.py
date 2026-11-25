import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from emubench import calibration, chips, circuit, downloads, engines, identify, scores


class PublicSuite(unittest.TestCase):
    def test_frozen_cartridges_and_checkpoint_rejection(self):
        with TemporaryDirectory() as folder, patch.dict(os.environ, EMUBENCH_HOME=folder):
            for scene in circuit.SCENES:
                path=circuit.cartridge(scene.console,scene.level)
                self.assertEqual(engines.digest(path), scene.digest)
                self.assertEqual(len(scene.playback), 1440)
                with self.assertRaises(ValueError):
                    scene.validate(scene.digest, scene.warmup, circuit.FRAMES, ())
                path.write_bytes(b"interrupted")
                self.assertEqual(engines.digest(circuit.cartridge(scene.console,scene.level)),scene.digest)

    def test_chip_markers_and_checksum(self):
        for name in chips.NAMES:
            image=chips.cartridge(name)
            checksum=int.from_bytes(image[0x7fde:0x7fe0],"little")
            self.assertEqual(sum(image)&65535,checksum)
        for word,expected in [(31,"unresolved"),(31<<10,"fail"),(31<<5,"pass"),(0,"unresolved")]:
            self.assertEqual(chips.verdict(b"256 224 0\n"+word.to_bytes(2,"little")*(256*224)),expected)

    def test_paired_minimum_and_outliers(self):
        rows=[]
        for block in range(6):
            for frames,average in [(600,130),(1800,100),(10800,100)]:
                rows.append({"block":block,"frames":frames,"metrics":[average,80,110]})
        short,long=calibration.assess(rows,[600,1800],6)
        self.assertFalse(short["within_tolerance"])
        self.assertTrue(long["within_tolerance"])
        self.assertFalse(calibration.assess(rows[:-1],[1800],6)[0]["within_tolerance"])

    def test_edition_metadata_is_local_and_header_agnostic(self):
        data=bytes(32768)
        digest=hashlib.sha1(data).hexdigest()
        raw=f'clrmamepro ( )\ngame (\nname "Test (USA) (Rev 2)"\nrom ( sha1 {digest} )\n)'.encode()
        with TemporaryDirectory() as folder, patch.dict(os.environ,EMUBENCH_HOME=folder), patch.dict(
                identify.CATALOGS,snes=("Test",hashlib.sha256(raw).hexdigest())), patch.object(downloads,"fetch_bytes",return_value=raw):
            self.assertIsNone(identify.match("snes",data))
            self.assertEqual(identify.install("snes"),1)
            match=identify.match("snes",data)
            self.assertEqual(match["title"],"Test (USA) (Rev 2)")
            self.assertEqual(match,identify.match("snes",b"X"*512+data))
            self.assertNotEqual(match["edition"],hashlib.sha256(data).hexdigest())
            self.assertIsNone(identify.match("snes",b"x"*32768))

    def test_arm64_file_identity(self):
        with TemporaryDirectory() as td:
            p=Path(td)/"core"
            elf=bytearray(256)
            elf[:6]=b"\x7fELF\x02\x01"
            elf[18:20]=bytes((183,0))
            p.write_bytes(elf)
            downloads.check_arch(p,"linux-arm64")
            with self.assertRaises(ValueError):downloads.check_arch(p,"linux-x64")
            pe=bytearray(256)
            pe[:2]=b"MZ"
            pe[60]=128
            pe[128:134]=bytes.fromhex("5045000064aa")
            p.write_bytes(pe)
            downloads.check_arch(p,"windows-arm64")
            with self.assertRaises(ValueError):downloads.check_arch(p,"windows-x64")
