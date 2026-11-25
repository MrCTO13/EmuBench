import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from emubench import accuracy, carter, scores, video


class Carter(unittest.TestCase):
    def test_scenes_have_fixed_durations_and_distinct_ids(self):
        self.assertEqual(len(carter.PROFILES),6)
        for scene in carter.SCENES:
            self.assertEqual(sum(n for n,_ in scene.route),180)
            self.assertEqual(len(scene.playback),2*(scene.warmup+180))
            self.assertEqual(len(set(scene.references)),len(scene.references))

    def test_cartridge_mismatch_and_missed_checkpoint(self):
        scene = carter.SCENES[0]
        with tempfile.TemporaryDirectory() as folder:
            rom = Path(folder)/"test.gba"
            rom.write_bytes(b"another cartridge")
            with self.assertRaisesRegex(ValueError,"pinned"):
                carter.cartridge("gba",rom)
        with patch.object(video,"fingerprint",side_effect=["0"*64,"1"*64]), self.assertRaisesRegex(ValueError,"unscored"):
            scene.validate(carter.GAMES["gba"].digest,scene.warmup,180,(b"a",b"b"))

    def test_marker_unknown_is_never_a_pass(self):
        for system,(w,h) in {"gba":(240,160),"snes":(256,224)}.items():
            blank = f"{w} {h} 2\n".encode() + bytes(w*h*2)
            self.assertEqual(accuracy.verdict(system,blank),"unresolved")
        with self.assertRaises(ValueError):
            video.rgb_frame(b"240 160 1\nempty")
        with self.assertRaises(ValueError):
            accuracy.validated({"checks":{}},"snes","a"*64,"b"*64)

    def test_score_identity_and_privacy(self):
        scene = carter.SCENES[-1]
        result = {"schema":1,"id":str(uuid.uuid4()),"emulator":"bsnes","profile":scene.profile,"version":"115",
                  "source_commit":None,"core_sha256":"2"*64,"worker_sha256":"3"*64,"system":"Darwin","arch":"arm64",
                  "warmup_frames":scene.warmup,"frames":180,"rendered_frames":180,"frame_ns":[1000000]*180,
                  "audio_sample_frames":180,"rom_sha256":carter.GAMES["snes"].digest,
                  "scene_checkpoints":scene.references[0]}
        result["accuracy"]={"suite":accuracy.VERSION,"core_sha256":result["core_sha256"],
                            "worker_sha256":result["worker_sha256"],"checks":{"65C816 basic":"pass","SPC700":"fail"}}
        public=scores.public_fields(result,"Another scene")
        self.assertEqual(public["game"],scene.title)
        self.assertNotIn("rom_sha256",public)
        self.assertEqual(public["accuracy"]["checks"]["SPC700"],"fail")
        for changes in ({"emulator":"mGBA"},{"scene_checkpoints":["bad"]},{"rom_sha256":"0"*64},
                        {"profile":carter.SCENES[-2].profile},{"accuracy":{**result["accuracy"],"worker_sha256":"4"*64}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                scores.public_fields({**result,**changes},"Carter")
