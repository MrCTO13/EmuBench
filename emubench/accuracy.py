"""Small named conformance suite. Read each test program's own terminal message."""
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

from . import downloads, engines, scores, video

VERSION = "cpu-memory-v1"
GBA_SOURCE = "https://raw.githubusercontent.com/jsmolka/gba-tests/a7113b67e63f83a9b321696ddd7042ccfad6c881"
SNES_SOURCE = "https://github.com/gilyon/snes-tests/releases/download/v1.4/snes-tests.zip"
SNES_ARCHIVE = "c3a39e15a9f3789fe143e54dfa035c988204576eafacf97df8ff3546a917c5e9"
CHECKS = {
    "gba": {
        "ARM": ("arm/arm.gba", "77ee88662552bdc885c1080c0172ff119d54db791bd73b21808cf1ff1fe5b40e"),
        "Thumb": ("thumb/thumb.gba", "b5cb2291df4ab314b31c598acd9bff2ccfa0b38efff29daadfe97422ce369b67"),
        "Memory": ("memory/memory.gba", "21024fb6aae6343f5f0466dd54e3149de1fbeb23f78e7d85a015c983684d2f87"),
    },
    "snes": {
        "65C816 basic": ("cputest/cputest-basic.sfc", "d479bde706b9e16d76c0dfe98e2b2d3f5348f9dcb911e6a36b898f4201fc98bb"),
        "SPC700": ("spctest/spctest.sfc", "3909f03d55b07081a4e9ac437ba5179731ec6c8ac3c715f712daec0f398dde63"),
    },
}
# SHA-256 of one 0/1 byte per pixel of the upstream font for the literal result
# string at the position set by its source. Never learned from an emulator score.
MARKERS = {
    "gba": (("pass",56,76,128,"ab7813c5b4e4711846be4b7e6aa485830b14a1615751fad83b44439a5d13598e"),
            ("fail",60,76,96,"9c2f05c91f2e10fb3f9006bffd3e0d76b10153395ccd0fc3dff17031ab8a3e2a")),
    "snes": (("pass",144,8,56,"e7638bb3af783cf7fc83dd6b08a065e8795043502af0f4db7eda6fdd79feef9f"),
             ("fail",144,8,48,"e363b4b9c6104a5ec259ce5dfc57da02badb9b2478c793057437ee3b3b4daaf1")),
}


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as folder:
        staged = Path(folder) / "payload"
        staged.write_bytes(payload)
        os.replace(staged, path)


def checked_download(path, digest, source):
    if path.is_file() and engines.digest(path) == digest:
        return path.read_bytes()
    payload = downloads.fetch_bytes(source, 2 * 1024**2)
    if sha256(payload).hexdigest() != digest:
        raise ValueError("Upstream accuracy workload digest mismatch")
    atomic_write(path,payload)
    return payload


def test_image(console, member, digest):
    root = engines.home() / "conformance" / VERSION / "inputs"
    if console == "gba":
        return checked_download(root / member, digest, GBA_SOURCE + "/" + member)
    archive = checked_download(root/"snes-tests.zip", SNES_ARCHIVE, SNES_SOURCE)
    with ZipFile(BytesIO(archive)) as z:
        data = z.read(member)
    if sha256(data).hexdigest() != digest:
        raise ValueError("Unexpected SNES accuracy program in upstream archive")
    return data


def verdict(console, photo):
    width, height, rgb = video.rgb_frame(photo)
    if (width,height) != ((240,160) if console == "gba" else (256,224)):
        return "unresolved"
    for label, x, y, length, digest in MARKERS[console]:
        mask = bytearray()
        for row in range(y,y+8):
            for col in range(x,x+length):
                lit = rgb[3*(row*width+col)] >= 128
                mask.append(not lit if console == "gba" else lit)
        if sha256(mask).hexdigest() == digest:
            return label
    return "unresolved"


def validated(data, console, core_sha, worker_sha):
    from . import color_checks
    version="gbc-v1" if console=="gbc" else VERSION
    names=color_checks.CHECKS if console=="gbc" else CHECKS.get(console,{})
    if not names or not isinstance(data, dict) or (data.get("suite"),data.get("core_sha256"),data.get("worker_sha256")) != (version,core_sha,worker_sha):
        raise ValueError("Accuracy record does not match the selected build")
    cases = data.get("checks")
    if not isinstance(cases,dict) or set(cases) != set(names) or any(
            label not in ("pass","fail","unresolved") for label in cases.values()):
        raise ValueError("Incomplete accuracy record")
    return {"suite":version,"core_sha256":core_sha,"worker_sha256":worker_sha,
            "checks":{name:cases[name] for name in names}}


def run(emulator, core, refresh=False):
    if emulator in ("sameboy","gambatte"):
        from . import color_checks
        return color_checks.run(emulator, core)
    console = "gba" if emulator == "mgba" else "snes"
    worker = engines.worker()
    core_sha, worker_sha = engines.digest(core), engines.digest(worker)
    cache = engines.home() / "conformance" / VERSION / emulator / worker_sha / (core_sha+".json")
    if not refresh and cache.is_file():
        try:
            return validated(json.loads(cache.read_text(encoding="utf-8")),console,core_sha,worker_sha)
        except (ValueError, TypeError):
            pass
    frames = 120 if console == "gba" else 900
    cases = {}
    for name,(member,digest) in CHECKS[console].items():
        image = test_image(console,member,digest)
        try:
            _, captures = scores.run_worker(worker, core, image, 0, frames, 90, None,
                                            scores.ADAPTERS[emulator][0], bytes(2*frames), diagnostic=True)
            cases[name] = verdict(console,captures[0])
        except TimeoutError:
            cases[name] = "unresolved"
    record = {"suite":VERSION,"checks":cases,"core_sha256":core_sha,"worker_sha256":worker_sha}
    atomic_write(cache, json.dumps(record).encode())
    return record


def summary(record):
    checks = record["checks"]
    count = sum(value == "pass" for value in checks.values())
    return f"{count}/{len(checks)} diagnostic programs passed · " + ", ".join(f"{name} {value}" for name,value in checks.items())

def coverage(result):
    from . import chips, color_checks
    console = result.get("profile","").split("-")[0]
    expected = list(CHECKS.get(console, ())) if console!="gbc" else list(color_checks.CHECKS)
    if console=="snes":
        expected.extend(chips.NAMES)
    outcomes = {**result.get("accuracy",{}).get("checks",{}), **result.get("chips",{})}
    if not expected or not outcomes:
        return "Untested"
    return f"{sum(outcomes.get(k)=='pass' for k in expected)}/{len(expected)} checks passed"
