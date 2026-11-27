"""Private frame traces and an explicit allowlist for public score submissions."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
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

from . import adapters, carter, circuit, conditions, telemetry, hardware, details, engines, identify, journal, library, fsutil

REPOSITORY = "MrCTO13/EmuBench"
PROFILE = "gba-boot-no-input-v1"
# Schema 2: frame hashing outside the timed region, 10 s minimum window, 3% gate.
# Schema 1 results are kept locally but never published or compared with schema 2.
SCHEMA = 2


ADAPTERS = {key:(name, adapters.profile(adapters.CONSOLES[name][0])) for key,name in adapters.NAMES.items()}


def validate_file(rom, emulator):
    if not rom.is_file():
        raise ValueError("Choose a regular cartridge file")
    library.check_size(rom.name, rom.stat().st_size, emulator)


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
            "high_1pct_fps": round(1e9 / ordered[(n + 99) // 100 - 1]),
            "min_fps": round(1e9 / ordered[-1])}


class InterruptedWindow(InterruptedError):
    """The device became busy or another worker owns the measurement slot."""


HEADER = 9  # EB3 evidence header lines before the frame times.


def run_worker(worker, core, data, warmup, frames, timeout, ready, emulator, playback=None, diagnostic=False, paced=False, filename=None, external=None, expected_digest=None, force_color=False, video_mode=None, min_window_ms=0, no_state=False, phase=None):
    engines.home().mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "EMUBENCH_CORE_PATH": str(core),
           "EMUBENCH_WORKER_LOCK": str(engines.home() / "measure.lock")}
    from .standalone import slot
    # File handles avoid pipe back-pressure while the parent watches idle state.
    with slot(), tempfile.TemporaryDirectory() as folder, tempfile.TemporaryFile() as source, \
         tempfile.TemporaryFile() as errors:
        root = Path(folder)
        env.pop("EMUBENCH_STAGED",None)
        env.pop("EMUBENCH_CONTENT_NAME",None)
        env.pop("EMUBENCH_FORCE_COLOR",None)
        env.pop("EMUBENCH_SAMPLE_PHASE",None)
        env.pop("EMUBENCH_NO_STATE",None)
        env["EMUBENCH_MIN_WINDOW_MS"] = str(int(min_window_ms))
        if no_state:
            env["EMUBENCH_NO_STATE"] = "1"
        if phase is not None:
            env["EMUBENCH_SAMPLE_PHASE"] = str(int(phase))
        if force_color:
            env["EMUBENCH_FORCE_COLOR"]="1"
        if filename:
            env["EMUBENCH_CONTENT_NAME"] = filename
        if external:
            import shutil
            staged = root / filename
            shutil.copyfile(external, staged)
            if engines.digest(staged) != expected_digest:
                raise ValueError("Content changed while staging")
            env["EMUBENCH_STAGED"] = "1"
        source.write(data)
        source.seek(0)
        if ready and not ready():
            raise InterruptedWindow("Waiting for idle")
        args = [worker, str(len(data)), str(warmup), str(frames), next((adapters.CORE_NAMES[k] for k,v in adapters.NAMES.items() if v==emulator),emulator)]
        root = Path(folder)
        if paced:
            args.append("paced")
        elif playback is not None:
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
                    end = errors.seek(0, os.SEEK_END)
                    errors.seek(max(0, end - 1000))
                    raise ValueError(f"{emulator} worker exited {proc.returncode}. "
                                     + errors.read(1000).decode(errors="replace").strip())
                if ready and not ready():
                    raise InterruptedWindow("Device became busy during timing")
            finally:
                if proc.poll() is None:
                    proc.kill()
        if video_mode is not None:
            region, rate = (root / "video-rate").read_text().split()
            video_mode.update(region={"0":"NTSC","1":"PAL"}[region], refresh_hz=float(rate))
        evidence = (root / "frame-evidence").read_text(encoding="ascii").splitlines()
        if paced:
            return evidence, (root / "paced-result").read_text().split()
        if playback is None:
            return evidence, ()
        names = ["final-frame"] if diagnostic else ["scene-start", "scene-end"]
        return evidence, tuple((root / name).read_bytes() for name in names)


def measure(rom, requested, core, warmup, frames, timeout, ready=None, expected_rom=None, emulator="mgba", scene=None, member=None):
    from . import repeats, standalone
    with standalone.slot("score-series.lock"):
        runs = []
        for index in range(repeats.COUNT):
            if index:
                repeats.cool_down()
            run = _measure_once(rom,requested,core,warmup,frames,timeout,ready,expected_rom,emulator,scene,member)
            if runs and any(run[k]!=runs[0][k] for k in ("core_sha256","worker_sha256","rom_sha256","video_mode","profile")):
                raise ValueError("Emulator, ROM or video mode changed between passes")
            runs.append(run)
    report = repeats.summarize([sum(r["frame_ns"]) for r in runs], [len(r["frame_ns"]) for r in runs],
                               [r["conditions"] for r in runs])
    selected = runs[report["selected"]]
    selected["hardware"] = hardware.fingerprint()
    selected["conditions"] = [r["conditions"] for r in runs]
    selected["repeatability"] = report
    selected["idle"] = max((r["idle"] for r in runs), key=lambda i:i["cpu_percent"])
    return selected


def _measure_once(rom, requested, core, warmup, frames, timeout, ready, expected_rom, emulator, scene, member):
    if not 100 <= frames <= 1_000_000 or not 0 <= warmup <= 1_000_000 or timeout <= 0:
        raise ValueError("Use 100–1,000,000 measured frames, 0–1,000,000 warm-up frames and a positive timeout")
    name, profile = ADAPTERS[emulator]
    suffix = Path(member or rom.name).suffix.lower()
    console = adapters.content_console(suffix,emulator)
    external = rom if member is None and suffix in library.EXTERNAL else None
    if member is None:
        validate_file(rom, emulator)
        data = b"" if external else rom.read_bytes()
    else:
        data = library.read_pinned_member(rom, member, emulator)
    rom_hash = engines.digest(rom) if external else hashlib.sha256(data).hexdigest()
    if expected_rom is not None and expected_rom != rom_hash:
        raise ValueError("ROM changed since the campaign was created")
    library.check_header(data, emulator)
    if suffix == ".exe" and not data.startswith(b"PS-X EXE"):
        raise ValueError("Expected a PlayStation PS-X EXE image")
    profile = adapters.profile(console)
    if console == "snes" and len(data) % 32768 == 512:
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
    worker,translated = engines.timing_worker(core)
    worker_hash = engines.digest(worker)
    video_mode = {}
    before = telemetry.snapshot()
    idle = conditions.idle()
    from .repeats import min_window_ms
    MIN_WINDOW_MS = min_window_ms()
    def attempt(no_state=False, phase=None):
        return run_worker(worker, core, data, warmup, frames, timeout, ready, name,
                          scene.playback if scene else None, filename=rom.name if console=="arcade" else "workload"+suffix,
                          external=external, expected_digest=rom_hash, video_mode=video_mode,
                          min_window_ms=MIN_WINDOW_MS, no_state=no_state, phase=phase)
    method = "state" if scene else "continue"  # Non-replay workloads keep running new frames.
    try:
        output, checkpoints = attempt()
    except ValueError as exc:
        # A core whose save state crashes on this platform: repeat the replay in fresh
        # processes instead. Each process boots and replays identically.
        if not scene or "worker exited" not in str(exc):
            raise
        method = "process"
        output, checkpoints = attempt(no_state=True)
    output = _evidence(output, frames)
    if scene and output["loops"] == 1 and sum(output["times"]) < MIN_WINDOW_MS * 1_000_000:
        method = "process"
        while sum(output["times"]) < MIN_WINDOW_MS * 1_000_000 and len(output["times"]) + frames <= 1_000_000:
            more, more_checkpoints = attempt(no_state=True, phase=output["phase"])
            more = _evidence(more, frames)
            identical = (more["fingerprint"] == output["fingerprint"] and more_checkpoints == checkpoints
                         and more["version"] == output["version"])
            output.update(times=output["times"] + more["times"], loops=output["loops"] + more["loops"],
                          samples=output["samples"] + more["samples"], changes=output["changes"] + more["changes"],
                          audio=output["audio"] + more["audio"], consistent=output["consistent"] and more["consistent"] and identical)
    if core_hash != engines.digest(core) or worker_hash != engines.digest(worker):
        raise ValueError("Core or timing worker changed during measurement")
    scene_evidence = {'idle':idle,'conditions':telemetry.window(before)}
    if not scene and console in identify.CATALOGS:
        edition = identify.match(console, data)
        if edition:
            scene_evidence["catalog_match"] = edition
    if scene:
        scene_evidence["scene_checkpoints"] = scene.validate(rom_hash, warmup, frames, checkpoints)
        profile = scene.profile
    version, audio, fingerprint, visual_changes = output["version"], output["audio"], output["fingerprint"], output["changes"]
    loops, samples, phase, consistent = output["loops"], output["samples"], output["phase"], output["consistent"]
    if scene and not consistent:
        raise ValueError("Repeated scene passes rendered different frames (non-deterministic core or save state)")
    if tag and version != tag:
        raise ValueError(f"Core reported {version}, expected upstream release {tag}")
    times = output["times"]
    video_mode = reference_mode(console, video_mode)
    scene_evidence.update(frame_check=dict(method="copy-fnv64-17r", samples=samples, changes=int(visual_changes), signature=fingerprint, phase=int(phase)),
                          window=dict(loops=loops, timed_ns=sum(times), minimum_ns=MIN_WINDOW_MS*1_000_000, loops_identical=consistent, repeat=method), mode="libretro", video_mode=video_mode, speed_x=speed(times, video_mode))
    return {**({"execution":"x64-on-arm64"} if translated else {}), **({"build_recipe":"mgba-libretro-cmake-v1"} if tag else {}), **scene_evidence, "schema": SCHEMA, "id": str(uuid.uuid4()), "profile": profile,
            "comparison_id": journal.comparison_id(rom_hash), "device_id": journal.comparison_id("installation"),
            "emulator": name, "version": version, "source_commit": commit,
            "core_sha256": core_hash, "worker_sha256": worker_hash,
            "rom_sha256": rom_hash,
            "system": platform.system(), "arch": platform.machine(), "cpu": cpu_model(),
            "warmup_frames": warmup, "frames": frames, "rendered_frames": len(times),
            "sampled_frame_changes": int(visual_changes), "audio_sample_frames": int(audio), "pixel_sample_signature": fingerprint,
            "frame_ns": times, **stats(times)}


def _evidence(lines, frames):
    if len(lines) < HEADER + frames or lines[0] != "EB3":
        raise ValueError("Incomplete frame evidence")
    version, audio, fingerprint, changes, loops, consistent, phase, samples = lines[1:HEADER]
    loops = int(loops)
    if len(lines) != HEADER + frames * loops:
        raise ValueError("Incomplete frame evidence")
    return dict(version=version, audio=int(audio), fingerprint=fingerprint, changes=int(changes), loops=loops,
                consistent=consistent == "1", phase=int(phase), samples=int(samples), times=list(map(int, lines[HEADER:])))


def paced_pass(result, core, rom, timeout):
    worker,_ = engines.timing_worker(core)
    suffix = rom.suffix.lower()
    external = rom if suffix in library.EXTERNAL else None
    data = b"" if external else rom.read_bytes()
    if engines.digest(core) != result["core_sha256"] or engines.digest(worker) != result["worker_sha256"] or (engines.digest(rom) if external else hashlib.sha256(data).hexdigest()) != result["rom_sha256"]:
        raise ValueError("Workload, core or worker changed before the paced test")
    if result["profile"].startswith("snes-") and len(data) % 32768 == 512:
        data = data[512:]
    _, fields = run_worker(worker, core, data, result["warmup_frames"], result["frames"], timeout,
                           None, result["emulator"], paced=True, filename=rom.name if suffix==".zip" else "workload"+suffix, external=external, expected_digest=result["rom_sha256"])
    frames, late, missing, fps, audio = fields
    return {"frames":int(frames), "missed_deadlines":int(late), "audio_underrun_frames":int(missing),
            "refresh_hz":float(fps), "sample_rate":float(audio)}


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
        fsutil.publish_new(stage, destination)
    finally:
        stage.unlink(missing_ok=True)
    return destination


def reference_mode(console, mode):
    rate = mode["refresh_hz"]
    if not 20 <= rate <= 240:
        raise ValueError("Emulator did not report a usable console refresh rate")
    if console in ("gb", "gbc", "gba"):
        return {"region":"handheld", "refresh_hz":4194304 / 70224, "source":"lcd-clock"}
    if console=="snes":
        # Progressive display modes from upstream Snes9x snes9x.h. Cores can
        # round their return value differently for the same physical mode.
        ref={"NTSC":60.09881389744051,"PAL":50.006977968}[mode["region"]]
        if abs(rate-ref)<0.03:
            return {"region":mode["region"],"refresh_hz":ref,"source":"snes-progressive"}
    return {"region":mode["region"], "refresh_hz":rate, "source":"emulator-av"}


def speed(times, mode):
    return 1e9 * len(times) / (sum(times) * mode["refresh_hz"])


def public_title(title):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 90 or any(
            not (c.isalnum() or c in " .,'’()+&!_-") for c in title):
        raise ValueError("Use a public game title of 1–90 letters, numbers, spaces or common punctuation")
    return title.strip()


def public_fields(result, title):
    if result.get('mode')=='standalone-process-v1':
        from . import standalone
        return standalone.public_fields(result,title)
    from .accuracy import validated
    official = circuit.PROFILES.get(result["profile"])
    scene = official or carter.PROFILES.get(result["profile"])
    allowed = any(result["profile"]==adapters.profile(c) for c in adapters.CONSOLES.get(result["emulator"], ()))
    if scene:
        expected_console = {"mGBA":"gba","Snes9x":"snes","bsnes":"snes","CartsSNES":"snes"}.get(result["emulator"])
        allowed = (scene.console == expected_console and result.get("rom_sha256") == (official.digest if official else carter.GAMES[scene.console].digest)
                   and result["warmup_frames"] == scene.warmup and result["frames"] == (circuit.FRAMES if official else carter.FRAMES)
                   and tuple(result.get("scene_checkpoints", ())) in scene.references)
        title = scene.title
    if result["schema"] != SCHEMA or not allowed:
        raise ValueError("Unknown result format")
    edition = result.get("catalog_match") if result.get("share_title") is True and not scene else None
    if edition:
        if not re.fullmatch(r"[a-f0-9]{64}", edition["edition"]):
            raise ValueError("Invalid catalog edition")
        title = edition["title"]
    title = public_title(title)
    if (result["system"] not in ("Darwin", "Linux", "Windows") or
        not re.fullmatch(r"[A-Za-z0-9_-]{1,24}", result["arch"]) or
        not re.fullmatch(r"[A-Za-z0-9 ()._+-]{1,80}", result["version"]) or
        not re.fullmatch(r"[0-9a-f]{64}", result["core_sha256"]) or
        not re.fullmatch(r"[0-9a-f]{64}", result["worker_sha256"]) or
        (result["source_commit"] is not None and not engines.SHA.fullmatch(result["source_commit"]))):
        raise ValueError("Invalid build metadata")
    n = len(result["frame_ns"])
    loops = result.get("window", {}).get("loops")
    if (type(loops) is not int or loops < 1 or result["frames"] * loops != n or result["rendered_frames"] != n or
        type(result["warmup_frames"]) is not int or not 0 <= result["warmup_frames"] <= 1_000_000 or
        type(result["audio_sample_frames"]) is not int or result["audio_sample_frames"] <= 0):
        raise ValueError("Incomplete frame evidence")
    cpu = result.get("cpu", "Unknown")
    if not isinstance(cpu, str) or not 1 <= len(cpu) <= 160 or not cpu.isprintable():
        raise ValueError("Invalid processor model")
    cohort = {"edition":edition["edition"]} if edition else {}
    if "video_mode" in result:
        cohort.update(mode="libretro",video_mode=result["video_mode"], speed_x=speed(result["frame_ns"], result["video_mode"]))
    if "hardware" in result:
        cohort["hardware"] = result["hardware"]
    if "conditions" in result:
        cohort["conditions"] = result["conditions"]
    if "repeatability" in result:
        cohort["repeatability"] = result["repeatability"]
    if "idle" in result:
        cohort["idle"] = result["idle"]
    if "frame_check" in result:
        cohort["frame_check"] = result["frame_check"]
    cohort["window"] = {k: result["window"][k] for k in ("loops", "timed_ns", "minimum_ns", "loops_identical", "repeat") if k in result["window"]}
    if "attestation" in result:
        cohort["attestation"]=result["attestation"]
    if "execution" in result:
        if result["execution"]!="x64-on-arm64" or result["system"]!="Windows" or result["arch"].lower() not in ("arm64","aarch64"):
            raise ValueError("Invalid emulator execution architecture")
        cohort["execution"]=result["execution"]
    if "build_recipe" in result:
        if result["build_recipe"]!="mgba-libretro-cmake-v1" or result["emulator"]!="mGBA" or not result["source_commit"]:
            raise ValueError("Invalid source build recipe")
        cohort["build_recipe"]=result["build_recipe"]
    if "accuracy" in result:
        cohort["accuracy"] = validated(result["accuracy"], result["profile"].split("-")[0],
                                       result["core_sha256"], result["worker_sha256"])
    if scene:
        cohort["scene_checkpoints"] = list(result["scene_checkpoints"])
        cohort["scene_description"] = scene.description
    for field in ("device_id", "campaign_id"):
        if field in result:
            cohort[field] = str(uuid.UUID(result[field]))
    if "chips" in result:
        from .chips import NAMES, LEGACY
        data = result["chips"]
        if result["emulator"] not in ("Snes9x","bsnes","CartsSNES") or set(data) not in (set(NAMES),set(LEGACY)) or any(v not in ("pass","fail","unresolved") for v in data.values()):
            raise ValueError("Invalid coprocessor check results")
        cohort["chips"] = {name:data[name] for name in NAMES if name in data}
    if "paced" in result:
        data = result["paced"]
        if (data["frames"] != result["frames"] or type(data["missed_deadlines"]) is not int or not 0 <= data["missed_deadlines"] <= data["frames"]
                or type(data["audio_underrun_frames"]) is not int or not 0 <= data["audio_underrun_frames"] <= 10**10
                or not 45 <= data["refresh_hz"] <= 75 or not 8000 <= data["sample_rate"] <= 192000):
            raise ValueError("Invalid paced results")
        cohort["paced"] = {k:data[k] for k in ("frames","missed_deadlines","audio_underrun_frames","refresh_hz","sample_rate")}
    if "comparison_id" in result:
        cohort["comparison_id"] = str(uuid.UUID(result["comparison_id"]))
    return {**cohort, "run_id": str(uuid.UUID(result["id"])), "game": title, "profile": result["profile"],
            "emulator": result["emulator"], "version": result["version"], "source_commit": result["source_commit"],
            "core_sha256": result["core_sha256"], "worker_sha256": result["worker_sha256"],
            "os": result["system"], "arch": result["arch"], "cpu": cpu, "warmup_frames": result["warmup_frames"],
            "rendered_frames": n, **stats(result["frame_ns"]), "timing": details.timeline(result["frame_ns"])}


def find_submission(run_id, since, gh):
    # Search covers older manually shared scores. The issues list also covers a
    # successful POST that lost its response before GitHub Search indexed it.
    prefix = f"[Score {run_id}]"
    query = f'repo:{REPOSITORY} is:issue in:title "{run_id}"'
    found = json.loads(subprocess.check_output([*gh, "--method", "GET", "search/issues", "-f", "q=" + query], timeout=30))
    items = found["items"]
    page = 0
    while True:
        match = next((item["html_url"] for item in items if item["title"].startswith(prefix)), None)
        if match or (page and len(items) < 100):
            return match
        page += 1
        items = json.loads(subprocess.check_output([*gh, "--method", "GET", f"repos/{REPOSITORY}/issues",
                            "-f", "state=all", "-f", "since=" + since, "-F", "per_page=100", "-F", f"page={page}"], timeout=30))


def publish(public):
    directory = engines.home()
    directory.mkdir(parents=True, exist_ok=True)
    gh = ["gh", "api", "--hostname", "github.com"]
    with closing(sqlite3.connect(directory / "published.sqlite", timeout=60)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, url TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS submissions (id TEXT PRIMARY KEY, since TEXT NOT NULL)")
        db.execute("BEGIN IMMEDIATE")
        seen = db.execute("SELECT url FROM receipts WHERE id=?", (public["run_id"],)).fetchone()
        if seen:
            return seen[0]
        since = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.execute("INSERT OR IGNORE INTO submissions VALUES (?,?)", (public["run_id"], since))
        db.commit()  # Keep the recovery window even if the process stops during the POST.
        db.execute("BEGIN IMMEDIATE")
        seen = db.execute("SELECT url FROM receipts WHERE id=?", (public["run_id"],)).fetchone()
        if seen:
            return seen[0]
        since = db.execute("SELECT since FROM submissions WHERE id=?", (public["run_id"],)).fetchone()[0]
        prefix = f"[Score {public['run_id']}]"
        url = find_submission(public["run_id"], since, gh)
        if not url:
            kind = "Carter FPS suite" if public["profile"] in carter.PROFILES else "Personal ROM"
            body = (f"{kind} · self-reported · {public['profile']}\n\n"
                    "| Average FPS | 1% low FPS | 1% high FPS |\n| ---: | ---: | ---: |\n"
                    f"| {public['average_fps']:.0f} | {public['low_1pct_fps']:.0f} | {public['high_1pct_fps']:.0f} |\n\n"
                    + "\x60\x60\x60json\n" + json.dumps(public, ensure_ascii=False, indent=2) + "\n\x60\x60\x60")
            payload = {"title": f"{prefix} {public['game']} · {public['emulator']} {public['version']}", "body": body}
            response = subprocess.run([*gh, "--method", "POST", f"repos/{REPOSITORY}/issues",
                                       "--input", "-"], input=json.dumps(payload).encode(), check=True,
                                      stdout=subprocess.PIPE, timeout=40)
            url = json.loads(response.stdout)["html_url"]
        if not re.fullmatch(r"https://github\.com/MrCTO13/EmuBench/issues/[1-9][0-9]*", url, re.I):
            raise ValueError("Unexpected score URL from GitHub")
        db.execute("INSERT INTO receipts VALUES (?, ?)", (public["run_id"], url))
        db.execute("DELETE FROM submissions WHERE id=?", (public["run_id"],))
    return url
