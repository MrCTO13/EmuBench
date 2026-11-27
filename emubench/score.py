"""EmuBench 1: one versioned suite, reference = 1000, geometric means.

Three headline numbers, never folded together:

* Device score: pinned reference emulators (exact core hashes) on any hardware.
  Per console, the geometric mean over the suite scenes of
  (scene x-real-speed / reference device x-real-speed) x 1000, then the geometric
  mean over consoles. Same software for everyone, so only the hardware differs.
* Emulator score: emulator X against the reference emulator on the same machine.
  Per console, the geometric mean of (X speed / reference emulator speed) x 1000.
  The hardware cancels out. Public numbers are the median across devices, split by
  CPU architecture, and only verified builds count.
* Accuracy: its own number. A console only counts toward a speed score when every
  scene matched its reference checkpoints and the console passed its pinned minimum
  checks. Speed never buys accuracy points and accuracy never buys speed points.

Plus Playable %: the share of suite scenes at >= 1.0x average and with the 1% low at
or above the console's native frame rate. Raw FPS (average, 1% low, minimum) and the
native target stay next to every score.

Changing any scene, weight, reference or window makes a new suite version. Scores
from different versions are never compared.
"""
import json
import math
from pathlib import Path

from . import carter

SUITE = "EmuBench 1 (draft)"
VERSION = "eb1-draft-1"
REFERENCE_SCORE = 1000

# Gameplay replays are the headline. Carter Circuit is a synthetic PPU sub-score
# and stays out of EmuBench 1 because its loops idle in a VBlank wait.
SCENES = {
    "snes": tuple(s.profile for s in carter.SCENES if s.console == "snes"),
    "gba": tuple(s.profile for s in carter.SCENES if s.console == "gba"),
}
# Pinned minimum checks per console for the accuracy gate.
REQUIRED_CHECKS = {
    "snes": ("65C816 basic", "SPC700"),
    "gba": ("ARM", "Thumb", "Memory"),
}


def reference():
    """Lab-measured reference ladder. Consoles stay uncalibrated until measured."""
    data = json.loads(Path(__file__).with_name("reference_eb1.json").read_text(encoding="utf-8"))
    if data.get("suite_version") != VERSION:
        raise ValueError("Reference file belongs to another suite version")
    return data


def geomean(values):
    values = list(values)
    if not values or any(not (isinstance(v, (int, float)) and v > 0 and math.isfinite(v)) for v in values):
        raise ValueError("Geometric mean needs positive finite values")
    return math.exp(sum(math.log(v) for v in values) / len(values))


def console_of(result):
    return result["profile"].split("-")[0]


def playable(result):
    """>= 1.0x on average and the 1% low at or above the native frame rate."""
    target = result["video_mode"]["refresh_hz"]
    # Published FPS values are rounded to whole frames, so allow that half frame.
    return result["speed_x"] >= 1.0 and result["low_1pct_fps"] + 0.5 >= target


def accuracy(results):
    """Separate accuracy number: tested checks passed, plus the per-console gate."""
    by_console = {}
    for r in results:
        checks = {**r.get("accuracy", {}).get("checks", {}), **r.get("chips", {})}
        by_console.setdefault(console_of(r), {}).update(checks)
    tested = [v for checks in by_console.values() for v in checks.values() if v in ("pass", "fail")]
    gate = {c: all(by_console.get(c, {}).get(k) == "pass" for k in REQUIRED_CHECKS.get(c, ()))
            for c in by_console}
    return {"percent": round(100 * sum(v == "pass" for v in tested) / len(tested), 1) if tested else None,
            "tested": len(tested), "gate": gate}


def raw(result):
    return {"profile": result["profile"], "speed_x": result["speed_x"],
            "average_fps": result["average_fps"], "low_1pct_fps": result["low_1pct_fps"],
            "min_fps": result.get("min_fps"), "native_fps": result["video_mode"]["refresh_hz"],
            "region": result["video_mode"]["region"], "playable": playable(result)}


def _usable(results):
    """One accepted run per scene (the latest wins) for a single emulator build."""
    scenes = {}
    for r in results:
        if r.get("repeatability", {}).get("accepted") is True and r.get("scene_checkpoints"):
            scenes[r["profile"]] = r
    return scenes


def _why_missing(results, profiles):
    rejected = sorted({why for r in results if r.get("profile") in profiles
                       for why in r.get("repeatability", {}).get("rejected_for", [])})
    return "scenes rejected by the timing gate (" + ", ".join(rejected) + ")" if rejected else "missing scenes"


def device_score(results, ref=None):
    """Results from the pinned reference emulators on one device."""
    ref = ref or reference()
    scenes = _usable(results)
    gate = accuracy(results)["gate"]
    consoles, missing = {}, []
    for console, profiles in SCENES.items():
        pinned = ref["consoles"].get(console)
        runs = [scenes.get(p) for p in profiles]
        if not pinned or not pinned.get("scenes"):
            missing.append((console, "reference not measured yet"))
            continue
        if any(r is None for r in runs):
            missing.append((console, _why_missing(results, profiles)))
            continue
        if any(r["core_sha256"] != pinned["core_sha256"] for r in runs):
            missing.append((console, "not the pinned reference emulator"))
            continue
        if not gate.get(console):
            missing.append((console, "failed the accuracy gate"))
            continue
        consoles[console] = round(REFERENCE_SCORE * geomean(
            r["speed_x"] / pinned["scenes"][r["profile"]] for r in runs))
    return _headline(consoles, missing, scenes)


def emulator_score(results, baseline):
    """Emulator X (results) against the reference emulator (baseline) on the same device."""
    ours, theirs = _usable(results), _usable(baseline)
    gate = accuracy(results)["gate"]
    consoles, missing = {}, []
    for console, profiles in SCENES.items():
        pairs = [(ours.get(p), theirs.get(p)) for p in profiles]
        if any(a is None or b is None for a, b in pairs):
            missing.append((console, _why_missing(results + baseline, profiles)))
            continue
        if any(a["hardware"] != b["hardware"] or a["worker_sha256"] != b["worker_sha256"] for a, b in pairs):
            missing.append((console, "not measured on the same device and harness"))
            continue
        if not gate.get(console):
            missing.append((console, "failed the accuracy gate"))
            continue
        consoles[console] = round(REFERENCE_SCORE * geomean(a["speed_x"] / b["speed_x"] for a, b in pairs))
    return _headline(consoles, missing, ours)


def _headline(consoles, missing, scenes):
    runs = list(scenes.values())
    complete = not missing and len(consoles) == len(SCENES)
    return {"suite": SUITE, "suite_version": VERSION,
            "score": round(geomean(consoles.values())) if complete else None,
            "partial": None if complete else f"partial ({len(consoles)}/{len(SCENES)} consoles)",
            "consoles": consoles, "missing": dict(missing),
            "playable_percent": round(100 * sum(map(playable, runs)) / len(runs)) if runs else None,
            "accuracy": accuracy(runs), "scenes": [raw(r) for r in runs]}


def load(paths):
    return [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]


def describe(report, kind):
    lines = [f"{report['suite']} · {kind}"]
    lines.append(f"Score         {report['score']}" if report["score"] is not None else f"Score         none · {report['partial']}")
    for console, value in report["consoles"].items():
        lines.append(f"  {console.upper():<5}       {value}")
    for console, why in report["missing"].items():
        lines.append(f"  {console.upper():<5}       not scored · {why}")
    acc = report["accuracy"]
    lines.append(f"Accuracy      {acc['percent']}% of {acc['tested']} tested checks" if acc["percent"] is not None else "Accuracy      untested")
    if report["playable_percent"] is not None:
        lines.append(f"Playable      {report['playable_percent']}% of scenes")
    for s in report["scenes"]:
        lines.append(f"  {s['profile']:<24} {s['speed_x']:.2f}× · {s['average_fps']} avg / {s['low_1pct_fps']} 1% low / "
                     f"{s['min_fps']} min FPS · native {s['native_fps']:.2f} {s['region']}")
    return "\n".join(lines)
