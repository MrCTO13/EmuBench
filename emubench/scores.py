"""Private frame traces and an explicit allowlist for public score submissions."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import tempfile
import uuid

from . import engines

REPOSITORY = "MrCTO13/EmuBench"
PROFILE = "gba-boot-no-input-v1"


def stats(times):
    if not isinstance(times, list) or not 100 <= len(times) <= 1_000_000:
        raise ValueError("Expected 100 to 1,000,000 measured frames")
    if any(type(t) is not int or t <= 0 for t in times):
        raise ValueError("Invalid frame interval")
    ordered = sorted(times)
    n = len(times)
    return {"average_fps": round(1e9 * n / sum(times), 2),
            "low_1pct_fps": round(1e9 / ordered[(99 * n + 99) // 100 - 1], 2),
            "high_1pct_fps": round(1e9 / ordered[(n + 99) // 100 - 1], 2)}


def measure(rom, requested, core, warmup, frames, timeout):
    if not 100 <= frames <= 1_000_000 or not 0 <= warmup <= 1_000_000 or timeout <= 0:
        raise ValueError("Use 100–1,000,000 measured frames, 0–1,000,000 warm-up frames and a positive timeout")
    if rom.suffix.lower() != ".gba" or not rom.is_file() or not 192 <= rom.stat().st_size <= 32 * 1024**2:
        raise ValueError("Choose an unpacked .gba file (192 bytes to 32 MiB)")
    data = rom.read_bytes()
    if data[3:4] != b"\xea":
        raise ValueError("This file does not have the expected GBA cartridge header")
    if core:
        core = core.expanduser().resolve(strict=True)
        tag, commit = None, None
    else:
        core, meta = engines.install(requested or engines.REFERENCE)
        tag, commit = meta["tag"], meta["commit"]
    core_hash = engines.digest(core)
    worker = engines.worker()
    with tempfile.TemporaryDirectory() as folder:
        env = {**os.environ, "EMUBENCH_CORE_PATH": str(core)}
        proc = subprocess.run([worker, str(len(data)), str(warmup), str(frames)], cwd=folder,
                              env=env, input=data, capture_output=True, timeout=timeout)
    if proc.returncode:
        message = proc.stderr.decode(errors="replace").strip()[-500:]
        raise ValueError(f"mGBA worker exited {proc.returncode}. {message}")
    output = proc.stdout.decode("ascii").splitlines()
    if len(output) != frames + 4 or output[0] != "EB1":
        raise ValueError("Incomplete frame evidence")
    version, audio, fingerprint = output[1:4]
    if tag and version != tag:
        raise ValueError(f"Core reported {version}, expected upstream release {tag}")
    times = list(map(int, output[4:]))
    return {"schema": 1, "id": str(uuid.uuid4()), "profile": PROFILE,
            "emulator": "mGBA", "version": version, "source_commit": commit,
            "core_sha256": core_hash, "worker_sha256": engines.digest(worker),
            "rom_sha256": hashlib.sha256(data).hexdigest(),
            "system": platform.system(), "arch": platform.machine(),
            "warmup_frames": warmup, "frames": frames, "rendered_frames": len(times),
            "audio_sample_frames": int(audio), "pixel_sample_signature": fingerprint,
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
    if result["schema"] != 1 or result["profile"] != PROFILE or result["emulator"] != "mGBA":
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
    return {"run_id": str(uuid.UUID(result["id"])), "game": title.strip(), "profile": PROFILE,
            "emulator": "mGBA", "version": result["version"], "source_commit": result["source_commit"],
            "core_sha256": result["core_sha256"], "worker_sha256": result["worker_sha256"],
            "os": result["system"], "arch": result["arch"], "warmup_frames": result["warmup_frames"],
            "rendered_frames": n, **stats(result["frame_ns"])}


def publish(public):
    directory = engines.home()
    directory.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(directory / "published.sqlite", timeout=60) as db:
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
            body = (f"Personal GBA ROM · self-reported · {PROFILE}\n\n"
                    "| Average FPS | 1% low FPS | 1% high FPS |\n| ---: | ---: | ---: |\n"
                    f"| {public['average_fps']:.2f} | {public['low_1pct_fps']:.2f} | {public['high_1pct_fps']:.2f} |\n\n"
                    + "\x60\x60\x60json\n" + json.dumps(public, ensure_ascii=False, indent=2) + "\n\x60\x60\x60")
            payload = {"title": f"{prefix} {public['game']} · mGBA {public['version']}", "body": body}
            response = subprocess.run(["gh", "api", "--method", "POST", f"repos/{REPOSITORY}/issues",
                                       "--input", "-"], input=json.dumps(payload).encode(), check=True,
                                      stdout=subprocess.PIPE, timeout=40)
            url = json.loads(response.stdout)["html_url"]
        if not re.fullmatch(r"https://github\.com/MrCTO13/EmuBench/issues/[1-9][0-9]*", url, re.I):
            raise ValueError("Unexpected score URL from GitHub")
        db.execute("INSERT INTO receipts VALUES (?, ?)", (public["run_id"], url))
    return url
