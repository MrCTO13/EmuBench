"""Private frame traces and an explicit allowlist for public score submissions."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import tempfile
import time
import uuid

from . import carter, details, engines, journal

REPOSITORY = "MrCTO13/EmuBench"
PROFILE = "gba-boot-no-input-v1"


ADAPTERS = {"mgba": ("mGBA", PROFILE), "snes9x": ("Snes9x", "snes-boot-no-input-v1"),
            "bsnes": ("bsnes", "snes-boot-no-input-v1")}


def validate_file(rom, emulator):
    if emulator == "mgba":
        extensions, minimum = (".gba",), 192
    else:
        extensions, minimum = (".sfc", ".smc"), 32768
    if rom.suffix.lower() not in extensions or not rom.is_file() or not minimum <= rom.stat().st_size <= 32 * 1024**2:
        raise ValueError("Choose an unpacked " + " or ".join(extensions) + " cartridge image up to 32 MiB")


def cpu_model():
    try:
        if platform.system() == "Darwin":
            return subprocess.check_output(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
                                           text=True, timeout=3).strip()
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            key, _, value = line.partition(":")
            if key.strip() in ("model name", "Hardware") and value.strip():
                return value.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "Unknown"


def stats(times):
    if not isinstance(times, list) or not 100 <= len(times) <= 1_000_000:
        raise ValueError("Expected 100 to 1,000,000 measured frames")
    if any(type(t) is not int or t <= 0 for t in times):
        raise ValueError("Invalid frame interval")
    ordered = sorted(times)
    n = len(times)
    return {"average_fps": round(1e9 * n / sum(times)),
            "low_1pct_fps": round(1e9 / ordered[(99 * n + 99) // 100 - 1]),
            "high_1pct_fps": round(1e9 / ordered[(n + 99) // 100 - 1])}


class InterruptedWindow(InterruptedError):
    """The device became busy or another worker owns the measurement slot."""


def run_worker(worker, core, data, warmup, frames, timeout, ready, emulator, playback=None, diagnostic=False):
    engines.home().mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "EMUBENCH_CORE_PATH": str(core),
           "EMUBENCH_WORKER_LOCK": str(engines.home() / "measure.lock")}
    # File handles avoid pipe back-pressure while the parent watches idle state.
    with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryFile() as source, \
         tempfile.TemporaryFile() as errors:
        source.write(data)
        source.seek(0)
        if ready and not ready():
            raise InterruptedWindow("Waiting for idle")
        args = [worker, str(len(data)), str(warmup), str(frames), emulator]
        root = Path(folder)
        if playback is not None:
            if len(playback) != 2 * (warmup + frames):
                raise ValueError("Controller recording has the wrong length")
            (root / "controller.bin").write_bytes(playback)
            args.append("diagnostic" if diagnostic else "replay")
        start = time.monotonic()
        with subprocess.Popen(args, cwd=folder, env=env, stdin=source, stdout=subprocess.DEVNULL, stderr=errors) as proc:
            try:
                while True:
                    before_wait = time.time()
                    remaining = timeout - (time.monotonic() - start)
                    if remaining <= 0:
                        raise TimeoutError("Measurement timed out")
                    try:
                        proc.wait(timeout=min(1, remaining) if ready else remaining)
                        if ready and time.time() - before_wait > 5:
                            raise InterruptedWindow("Host monitoring gap during timing")
                        break
                    except subprocess.TimeoutExpired:
                        if ready and (time.time() - before_wait > 5 or not ready()):
                            raise InterruptedWindow("Device became busy during timing")
                if proc.returncode == 75:
                    raise InterruptedWindow("Another measurement is active on this device")
                if proc.returncode:
                    errors.seek(0)
                    raise ValueError(f"{emulator} worker exited {proc.returncode}. "
                                     + errors.read(1000).decode(errors="replace").strip())
                if ready and not ready():
                    raise InterruptedWindow("Device became busy during timing")
            finally:
                if proc.poll() is None:
                    proc.kill()
        evidence = (root / "frame-evidence").read_text(encoding="ascii").splitlines()
        if playback is None:
            return evidence, ()
        names = ["final-frame"] if diagnostic else ["scene-start", "scene-end"]
        return evidence, tuple((root / name).read_bytes() for name in names)


def measure(rom, requested, core, warmup, frames, timeout, ready=None, expected_rom=None, emulator="mgba", scene=None):
    if not 100 <= frames <= 1_000_000 or not 0 <= warmup <= 1_000_000 or timeout <= 0:
        raise ValueError("Use 100–1,000,000 measured frames, 0–1,000,000 warm-up frames and a positive timeout")
    name, profile = ADAPTERS[emulator]
    validate_file(rom, emulator)
    data = rom.read_bytes()
    rom_hash = hashlib.sha256(data).hexdigest()
    if expected_rom is not None and expected_rom != rom_hash:
        raise ValueError("ROM changed since the campaign was created")
    if emulator == "mgba" and data[3:4] != b"\xea":
        raise ValueError("This file does not have the expected GBA cartridge header")
    if emulator != "mgba" and len(data) % 32768 == 512:
        data = data[512:]  # Strip the copier header before handing the cartridge to the core.
    if core:
        core = core.expanduser().resolve(strict=True)
        tag, commit = None, None
    else:
        if emulator != "mgba":
            raise ValueError("Select a SNES core using --latest-core or --core")
        core, meta = engines.install(requested or engines.REFERENCE)
        tag, commit = meta["tag"], meta["commit"]
    core_hash = engines.digest(core)
    worker = engines.worker()
    output, checkpoints = run_worker(worker, core, data, warmup, frames, timeout, ready, name,
                                     scene.playback if scene else None)
    scene_evidence = {}
    if scene:
        scene_evidence["scene_checkpoints"] = scene.validate(rom_hash, warmup, frames, checkpoints)
        profile = scene.profile
    if len(output) != frames + 5 or output[0] != "EB2":
        raise ValueError("Incomplete frame evidence")
    version, audio, fingerprint, visual_changes = output[1:5]
    if tag and version != tag:
        raise ValueError(f"Core reported {version}, expected upstream release {tag}")
    times = list(map(int, output[5:]))
    return {**scene_evidence, "schema": 1, "id": str(uuid.uuid4()), "profile": profile,
            "comparison_id": journal.comparison_id(rom_hash),
            "emulator": name, "version": version, "source_commit": commit,
            "core_sha256": core_hash, "worker_sha256": engines.digest(worker),
            "rom_sha256": rom_hash,
            "system": platform.system(), "arch": platform.machine(), "cpu": cpu_model(),
            "warmup_frames": warmup, "frames": frames, "rendered_frames": len(times),
            "sampled_frame_changes": int(visual_changes), "audio_sample_frames": int(audio), "pixel_sample_signature": fingerprint,
            "frame_ns": times, **stats(times)}


def save(result, destination):
    destination = destination or engines.home() / "results" / (result["id"] + ".json")
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Stage on the same filesystem and create the destination without overwriting.
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False, mode="w", encoding="utf-8") as f:
        stage = Path(f.name)
        try:
            json.dump(result, f, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            f.close()
            stage.unlink(missing_ok=True)
            raise
    try:
        os.link(stage, destination)
    finally:
        stage.unlink(missing_ok=True)
    return destination


def public_fields(result, title):
    from .accuracy import validated
    scene = carter.PROFILES.get(result["profile"])
    allowed = (result["emulator"], result["profile"]) in ADAPTERS.values()
    if scene:
        expected_console = {"mGBA":"gba","Snes9x":"snes","bsnes":"snes"}.get(result["emulator"])
        allowed = (scene.console == expected_console and result.get("rom_sha256") == carter.GAMES[scene.console].digest
                   and result["warmup_frames"] == scene.warmup and result["frames"] == carter.FRAMES
                   and tuple(result.get("scene_checkpoints", ())) in scene.references)
        title = scene.title
    if result["schema"] != 1 or not allowed:
        raise ValueError("Unknown result format")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 90 or any(
            not (c.isalnum() or c in " .,'’()+&!_-") for c in title):
        raise ValueError("Use a public game title of 1–90 letters, numbers, spaces or common punctuation")
    if (result["system"] not in ("Darwin", "Linux", "Windows") or
        not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", result["arch"]) or
        not re.fullmatch(r"[A-Za-z0-9 ._+-]{1,80}", result["version"]) or
        not re.fullmatch(r"[0-9a-f]{64}", result["core_sha256"]) or
        not re.fullmatch(r"[0-9a-f]{64}", result["worker_sha256"]) or
        (result["source_commit"] is not None and not engines.SHA.fullmatch(result["source_commit"]))):
        raise ValueError("Invalid build metadata")
    n = len(result["frame_ns"])
    if (result["frames"] != n or result["rendered_frames"] != n or
        type(result["warmup_frames"]) is not int or not 0 <= result["warmup_frames"] <= 1_000_000 or
        type(result["audio_sample_frames"]) is not int or result["audio_sample_frames"] <= 0):
        raise ValueError("Incomplete frame evidence")
    cpu = result.get("cpu", "Unknown")
    if not isinstance(cpu, str) or not 1 <= len(cpu) <= 160 or not cpu.isprintable():
        raise ValueError("Invalid processor model")
    cohort = {}
    if "accuracy" in result:
        cohort["accuracy"] = validated(result["accuracy"], "gba" if result["emulator"] == "mGBA" else "snes",
                                       result["core_sha256"], result["worker_sha256"])
    if scene:
        cohort["scene_checkpoints"] = list(result["scene_checkpoints"])
    if "comparison_id" in result:
        cohort["comparison_id"] = str(uuid.UUID(result["comparison_id"]))
    return {**cohort, "run_id": str(uuid.UUID(result["id"])), "game": title.strip(), "profile": result["profile"],
            "emulator": result["emulator"], "version": result["version"], "source_commit": result["source_commit"],
            "core_sha256": result["core_sha256"], "worker_sha256": result["worker_sha256"],
            "os": result["system"], "arch": result["arch"], "cpu": cpu, "warmup_frames": result["warmup_frames"],
            "rendered_frames": n, **stats(result["frame_ns"]), "timing": details.timeline(result["frame_ns"])}


def publish(public):
    directory = engines.home()
    directory.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(directory / "published.sqlite", timeout=60)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, url TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        seen = db.execute("SELECT url FROM receipts WHERE id=?", (public["run_id"],)).fetchone()
        if seen:
            return seen[0]
        # Match the run ID if a previous request reached GitHub before local commit.
        prefix = f"[Score {public['run_id']}]"
        query = f'repo:{REPOSITORY} is:issue in:title "{public["run_id"]}"'
        found = json.loads(subprocess.check_output(["gh", "api", "--method", "GET", "search/issues",
                                                    "-f", "q=" + query], timeout=40))
        url = next((item["html_url"] for item in found["items"] if item["title"].startswith(prefix)), None)
        if not url:
            kind = "Carter FPS suite" if public["profile"] in carter.PROFILES else "Personal ROM"
            body = (f"{kind} · self-reported · {public['profile']}\n\n"
                    "| Average FPS | 1% low FPS | 1% high FPS |\n| ---: | ---: | ---: |\n"
                    f"| {public['average_fps']:.0f} | {public['low_1pct_fps']:.0f} | {public['high_1pct_fps']:.0f} |\n\n"
                    + "\x60\x60\x60json\n" + json.dumps(public, ensure_ascii=False, indent=2) + "\n\x60\x60\x60")
            payload = {"title": f"{prefix} {public['game']} · {public['emulator']} {public['version']}", "body": body}
            response = subprocess.run(["gh", "api", "--method", "POST", f"repos/{REPOSITORY}/issues",
                                       "--input", "-"], input=json.dumps(payload).encode(), check=True,
                                      stdout=subprocess.PIPE, timeout=40)
            url = json.loads(response.stdout)["html_url"]
        if not re.fullmatch(r"https://github\.com/MrCTO13/EmuBench/issues/[1-9][0-9]*", url, re.I):
            raise ValueError("Unexpected score URL from GitHub")
        db.execute("INSERT INTO receipts VALUES (?, ?)", (public["run_id"], url))
    return url
