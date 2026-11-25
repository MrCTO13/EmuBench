"""External monotonic timing of upstream headless executables, including launch and exit."""
from contextlib import contextmanager
import csv
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from . import conditions, engines, journal


@contextmanager
def slot():
    directory = engines.home()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "measure.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Another measurement is active on this device") from exc
        yield


def timed(command, directory, timeout):
    with slot():
        idle = conditions.idle()
        start = time.perf_counter_ns()
        output = subprocess.run(command, cwd=directory, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        elapsed = time.perf_counter_ns() - start
    if output.returncode or elapsed <= 0:
        raise ValueError("The selected standalone runner did not complete the workload")
    return output, elapsed, idle


def receipt(emulator, version, digest, frames, elapsed, hz, checkpoints, idle):
    fps = 1e9 * frames / elapsed
    data = dict(id=str(uuid.uuid4()), finished_utc=journal.now(), emulator=emulator, version=version,
                mode="standalone-process-v1", runner_sha256=digest, frames=frames, elapsed_ns=elapsed,
                idle=idle, refresh_hz=hz, average_fps=round(fps), speed_x=fps/hz, render_checkpoints=checkpoints)
    dest = engines.home() / "standalone" / (data["id"]+".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"{emulator} standalone · {fps/hz:.2f}× · {round(fps)} average FPS (launch through exit)\nPrivate report: {dest}")
    return data


def arguments(commands):
    p = commands.add_parser("mgba-perf", help="Time the upstream mGBA standalone profiler")
    p.add_argument("--rom", required=True, type=Path)
    p.add_argument("--runner", type=Path, help="Path to upstream mgba-perf")
    p.add_argument("--frames", default=1800, type=int)
    p.add_argument("--timeout", default=300, type=int)


def mgba(args):
    runner = args.runner or shutil.which("mgba-perf")
    if not runner:
        raise ValueError("Install upstream mgba-perf or specify --runner")
    runner = Path(runner).resolve(strict=True)
    rom = args.rom.resolve(strict=True)
    if rom.suffix.lower() != ".gba" or not 100 <= args.frames <= 1000000 or args.timeout <= 0:
        raise ValueError("Choose a GBA image, 100–1,000,000 frames and a positive timeout")
    with tempfile.TemporaryDirectory() as root:
        game = Path(root) / "workload.gba"
        shutil.copyfile(rom, game)
        version = subprocess.check_output([runner, "--version", game], cwd=root, timeout=10, text=True)
        match = re.search(r" ([0-9][\w.+-]*) \(([^\r\n)]*)\)", version.strip())
        if not match:
            raise ValueError("The program did not identify its upstream mGBA version")
        digest = engines.digest(runner)
        output, elapsed, idle = timed([runner, "-P", "-s", "0", "-C", "useBios=0", "-C", "idleOptimization=ignore",
                                 "-F", str(args.frames), game], root, args.timeout)
        rows = list(csv.DictReader(io.StringIO(output.stdout.decode())))
        if len(rows)!=1 or rows[0].get("renderer")!="software" or int(rows[0]["frames"])!=args.frames:
            raise ValueError("mGBA did not confirm software rendering for the requested frames")
        return receipt("mGBA",match[1],digest,args.frames,elapsed,4194304/70224,None,idle)
