import copy
import unittest

from emubench import score


def run(profile, speed, sha="a", low=None, checks=None, device="Example / 4c"):
    console = profile.split("-")[0]
    hz = 60.0988 if console == "snes" else 59.7275
    return {"profile": profile, "speed_x": speed, "average_fps": round(speed * hz),
            "low_1pct_fps": round((low if low is not None else speed) * hz), "min_fps": round(speed * hz / 2),
            "video_mode": {"refresh_hz": hz, "region": "NTSC" if console == "snes" else "handheld"},
            "core_sha256": sha * 64, "worker_sha256": "w" * 64, "hardware": {"device_class": device},
            "repeatability": {"accepted": True}, "scene_checkpoints": ["x", "y"],
            "accuracy": {"checks": checks if checks is not None else
                         ({"65C816 basic": "pass", "SPC700": "pass"} if console == "snes" else
                          {"ARM": "pass", "Thumb": "pass", "Memory": "pass"})}}


def suite(factor, sha="a", **kw):
    return [run(p, factor * (i + 1), sha, **kw) for c in score.SCENES for i, p in enumerate(score.SCENES[c])]


REF = {"suite_version": score.VERSION, "consoles": {
    c: {"core_sha256": "a" * 64, "scenes": {p: float(i + 1) for i, p in enumerate(ps)}} for c, ps in score.SCENES.items()}}


class EB1(unittest.TestCase):
    def test_reference_device_scores_1000(self):
        self.assertEqual(score.device_score(suite(1.0), REF)["score"], 1000)

    def test_twice_as_fast_scores_2000_and_geomean(self):
        r = score.device_score(suite(2.0), REF)
        self.assertEqual(r["score"], 2000)
        runs = suite(1.0)
        for x in runs:
            if x["profile"].startswith("gba"):
                x["speed_x"] *= 4
        self.assertEqual(score.device_score(runs, REF)["score"], 2000)  # sqrt(1 * 4) = 2

    def test_partial_when_console_missing_or_uncalibrated(self):
        runs = [r for r in suite(1.0) if r["profile"].startswith("snes")]
        r = score.device_score(runs, REF)
        self.assertIsNone(r["score"])
        self.assertEqual(r["partial"], "partial (1/2 consoles)")
        empty = copy.deepcopy(REF)
        empty["consoles"]["gba"]["scenes"] = {}
        self.assertIn("reference not measured", score.device_score(suite(1.0), empty)["missing"]["gba"])

    def test_accuracy_gate_and_custom_build(self):
        runs = suite(1.0, checks={"65C816 basic": "fail", "SPC700": "pass", "ARM": "pass", "Thumb": "pass", "Memory": "pass"})
        r = score.device_score(runs, REF)
        self.assertIsNone(r["score"])
        self.assertIn("accuracy gate", r["missing"]["snes"])
        self.assertLess(r["accuracy"]["percent"], 100)
        self.assertIn("pinned reference", score.device_score(suite(1.0, sha="b"), REF)["missing"]["snes"])

    def test_emulator_score_cancels_hardware(self):
        self.assertEqual(score.emulator_score(suite(3.0, sha="b"), suite(2.0))["score"], 1500)
        other = suite(2.0, device="Other / 8c")
        self.assertIsNone(score.emulator_score(suite(3.0, sha="b"), other)["score"])

    def test_playable_needs_average_and_1pct_low(self):
        self.assertTrue(score.playable(run(score.SCENES["snes"][0], 1.2)))
        self.assertFalse(score.playable(run(score.SCENES["snes"][0], 1.2, low=0.9)))
        r = score.device_score(suite(0.5), REF)
        self.assertEqual(r["playable_percent"], 67)  # 0.5x scene fails, 1.0x and 1.5x pass
        self.assertTrue(all("native_fps" in s and "min_fps" in s for s in r["scenes"]))

    def test_shipped_reference_is_honestly_uncalibrated(self):
        ref = score.reference()
        self.assertTrue(all(not c["scenes"] for c in ref["consoles"].values()))


if __name__ == "__main__":
    unittest.main()
