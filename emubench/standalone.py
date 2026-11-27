"""External monotonic timing of upstream headless executables, including launch and exit."""
from contextlib import contextmanager
import csv
import io
import json
import os
import platform
import sys
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from . import conditions, engines, journal, telemetry, hardware


@contextmanager
def slot(name="measure.lock"):
    # A loopback socket gives all users and data directories on this host the same
    # OS-owned exclusion slot. No listener or external network access is needed.
    import socket
    from .scores import InterruptedWindow
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as lock:
        if os.name=="nt":
            lock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        port=47258 if name=="score-series.lock" else 47257
        try:
            lock.bind(("127.0.0.1",port))
            lock.listen(1)
        except OSError as exc:
            raise InterruptedWindow("Another measurement owns the device timing slot") from exc
        yield


def timed(command, directory, timeout):
    with slot():
        before = telemetry.snapshot()
        idle = conditions.idle()
        start = time.perf_counter_ns()
        output = subprocess.run(command, cwd=directory, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        elapsed = time.perf_counter_ns() - start
        readings = telemetry.window(before)
    if output.returncode or elapsed <= 0:
        raise ValueError("The selected standalone runner did not complete the workload")
    return output, elapsed, idle, readings


def receipt(emulator, version, digest, frames, elapsed, hz, checkpoints, idle, conditions_window, content_sha256):
    fps = 1e9 * frames / elapsed
    data = dict(id=str(uuid.uuid4()), finished_utc=journal.now(), emulator=emulator, version=version,
                mode="standalone-process-v1", runner_sha256=digest, frames=frames, elapsed_ns=elapsed,
                conditions=conditions_window,content_sha256=content_sha256,idle=idle, refresh_hz=hz, average_fps=round(fps), speed_x=fps/hz, render_checkpoints=checkpoints)
    return data


def run_series(measure, args):
    from . import repeats
    with slot("score-series.lock"):
        runs = []
        for index in range(repeats.COUNT):
            if index:
                repeats.cool_down()
            runs.append(measure(args))
    for key in ("emulator","runner_sha256","frames","refresh_hz","content_sha256"):
        if len({r[key] for r in runs}) != 1:
            raise ValueError("Standalone workload changed between passes")
    report = repeats.summarize([r["elapsed_ns"] for r in runs], args.frames, [r["conditions"] for r in runs])
    data = runs[report["selected"]]
    from . import attest, scores, uploads
    console = "psx" if data["emulator"]=="DuckStation" else "gba"
    data.update(profile=console+"-standalone-process-v1", schema=1, system=platform.system(),
                arch=platform.machine(), cpu=scores.cpu_model(), core_sha256=data["runner_sha256"],
                device_id=journal.comparison_id("installation"),comparison_id=journal.comparison_id(data["content_sha256"]))
    if getattr(sys,"frozen",False):
        data["worker_sha256"]=engines.digest(Path(sys.executable))
    else:
        parts=[Path(__file__),Path(__file__).with_name("duckstation.py"),Path(__file__).with_name("repeats.py")]
        data["worker_sha256"]=hashlib.sha256(b"".join(p.read_bytes() for p in parts)).hexdigest()
    data["hardware"] = hardware.fingerprint()
    data["conditions"] = [r["conditions"] for r in runs]
    data["repeatability"] = report
    data["idle"] = max((r["idle"] for r in runs),key=lambda i:i["cpu_percent"])
    attest.complete(data)
    dest = engines.home() / "standalone" / (data["id"]+".json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    if data["render_checkpoints"] is not None:
        with journal.database() as db:
            uploads.enqueue(db,data,"Personal ROM")
        uploads.flush(limit=3)
    status="accepted" if report["accepted"] else "rejected"
    print(f"{data['emulator']} standalone · {data['speed_x']:.2f}× · {data['average_fps']} FPS · accuracy untested "
          f"· spread {report['relative_spread']:.1%} ({status})\nPrivate report: {dest}")


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
        output, elapsed, idle, window = timed([runner, "-P", "-s", "0", "-C", "useBios=0", "-C", "idleOptimization=ignore",
                                 "-F", str(args.frames), game], root, args.timeout)
        rows = list(csv.DictReader(io.StringIO(output.stdout.decode())))
        if len(rows)!=1 or rows[0].get("renderer")!="software" or int(rows[0]["frames"])!=args.frames:
            raise ValueError("mGBA did not confirm software rendering for the requested frames")
        return receipt("mGBA",match[1],digest,args.frames,elapsed,4194304/70224,None,idle,window,engines.digest(game))

def public_fields(data,title):
    from .scores import public_title
    shared = ("device_id","comparison_id","profile","mode","emulator","version","core_sha256","worker_sha256","arch",
              "cpu","average_fps","speed_x","idle","repeatability","conditions","hardware","render_checkpoints","elapsed_ns")
    region = "handheld" if data["emulator"]=="mGBA" else ("PAL" if data["refresh_hz"]<55 else "NTSC")
    return {**{k:data[k] for k in shared}, **({"attestation":data["attestation"]} if "attestation" in data else {}),
            "video_mode":{"region":region,"refresh_hz":data["refresh_hz"],"source":"lcd-clock" if region=="handheld" else "psx-crtc"},
            "os":data["system"], "run_id":data["id"],"source_commit":None,"game":public_title(title),
            "warmup_frames":0,"rendered_frames":data["frames"]}
