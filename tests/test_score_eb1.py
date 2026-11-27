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
    c: {"core_sha256": "a" * 64, "scenes": {p: float(i + 1) for i, p in enumerate(ps)},
        "required_checks": ["65C816 basic", "SPC700"] if c == "snes" else ["ARM", "Thumb", "Memory"]}
    for c, ps in score.SCENES.items()}}
# A reference that fails some of its own checks: the gate only asks for what it passed.
PARTIAL_REF = copy.deepcopy(REF)
PARTIAL_REF["consoles"]["snes"]["required_checks"] = ["SPC700"]
PARTIAL_REF["consoles"]["gba"]["required_checks"] = ["Memory"]
ALL_PASS = {"65C816 basic": "pass", "SPC700": "pass", "ARM": "pass", "Thumb": "pass", "Memory": "pass"}


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

    def test_check_the_reference_fails_does_not_block(self):
        checks = {**ALL_PASS, "65C816 basic": "fail", "ARM": "fail", "Thumb": "fail"}
        r = score.device_score(suite(1.0, checks=checks), PARTIAL_REF)
        self.assertEqual(r["score"], 1000)
        self.assertEqual(r["accuracy"]["gate"], {"snes": True, "gba": True})
        # Known reference failures still count in the separate Accuracy number.
        self.assertEqual(r["accuracy"]["tested"], 10)  # five checks on each console
        self.assertEqual(r["accuracy"]["percent"], 40.0)
        e = score.emulator_score(suite(2.0, sha="b", checks=checks), suite(1.0, checks=checks), PARTIAL_REF)
        self.assertEqual(e["score"], 2000)

    def test_regression_on_a_check_the_reference_passes_blocks(self):
        checks = {**ALL_PASS, "SPC700": "fail"}
        r = score.device_score(suite(1.0, checks=checks), PARTIAL_REF)
        self.assertIsNone(r["score"])
        self.assertIn("accuracy gate", r["missing"]["snes"])
        self.assertEqual(r["consoles"], {"gba": 1000})
        self.assertEqual(r["accuracy"]["percent"], 80.0)
        e = score.emulator_score(suite(2.0, sha="b", checks=checks), suite(1.0), PARTIAL_REF)
        self.assertIn("accuracy gate", e["missing"]["snes"])
        # A check that was never run does not count as passed for the gate.
        unrun = {k: v for k, v in ALL_PASS.items() if k != "Memory"}
        self.assertIn("accuracy gate", score.device_score(suite(1.0, checks=unrun), PARTIAL_REF)["missing"]["gba"])

    def test_uncalibrated_console_has_no_gate(self):
        empty = copy.deepcopy(PARTIAL_REF)
        del empty["consoles"]["gba"]["required_checks"]
        r = score.device_score(suite(1.0), empty)
        self.assertIn("reference not measured", r["missing"]["gba"])
        self.assertIsNone(r["accuracy"]["gate"]["gba"])
        self.assertIn("reference not measured", score.emulator_score(suite(2.0, sha="b"), suite(1.0), empty)["missing"]["gba"])

    def test_emulator_score_cancels_hardware(self):
        self.assertEqual(score.emulator_score(suite(3.0, sha="b"), suite(2.0), REF)["score"], 1500)
        other = suite(2.0, device="Other / 8c")
        self.assertIsNone(score.emulator_score(suite(3.0, sha="b"), other, REF)["score"])

    def test_playable_needs_average_and_1pct_low(self):
        self.assertTrue(score.playable(run(score.SCENES["snes"][0], 1.2)))
        self.assertFalse(score.playable(run(score.SCENES["snes"][0], 1.2, low=0.9)))
        r = score.device_score(suite(0.5), REF)
        self.assertEqual(r["playable_percent"], 67)  # 0.5x scene fails, 1.0x and 1.5x pass
        self.assertTrue(all("native_fps" in s and "min_fps" in s for s in r["scenes"]))

    def test_shipped_reference_is_well_formed(self):
        ref = score.reference()
        for console, pinned in ref["consoles"].items():
            if not score.calibrated(ref, console):
                self.assertFalse(pinned.get("scenes"))
                continue
            self.assertEqual(set(pinned["scenes"]), set(score.SCENES[console]))
            self.assertTrue(all(v > 0 for v in pinned["scenes"].values()))
            self.assertRegex(pinned["core_sha256"], "^[0-9a-f]{64}$")
            # The gate is exactly what the reference passed in its own recorded accuracy run.
            checks = pinned["reference_accuracy"]["checks"]
            self.assertEqual(sorted(pinned["required_checks"]), sorted(k for k, v in checks.items() if v == "pass"))


if __name__ == "__main__":
    unittest.main()
