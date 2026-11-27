"""Fetch upstream artifacts into a per-user content-addressed cache."""
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from hashlib import sha256
from html.parser import HTMLParser
from http.client import HTTPException, IncompleteRead
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote
from urllib.request import Request
from zipfile import BadZipFile, ZipFile

from . import engines
from .catalog import CATALOG, TARGETS, host_target

MAX_BYTES = 1024**3
BUILD_SERVER = "https://buildbot.libretro.com/nightly"


@dataclass(frozen=True)
class Package:
    emulator: str
    target: str
    channel: str
    version: str
    name: str
    url: str
    identity: str
    checksum: str = ""
    size: int = 0
    member: str = ""


def fetch_bytes(url, limit):
    with engines.open_upstream(Request(url, headers={"User-Agent": "EmuBench/0.2"})) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Unexpectedly large upstream metadata")
        return data


class AssetLinks(HTMLParser):
    """Read GitHub's public release assets when shared API quotas are exhausted."""
    def __init__(self, prefix):
        super().__init__()
        self.prefix, self.items, self.current = prefix, [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href", "").startswith(self.prefix):
            path = attrs["href"]
            self.current = {"name": unquote(path[len(self.prefix):]), "browser_download_url": "https://github.com" + path}
            self.items.append(self.current)
        elif tag == "clipboard-copy" and self.current is not None:
            value = attrs.get("value", "")
            if re.fullmatch(r"sha256:[a-f0-9]{64}", value):
                self.current["digest"] = value

    def handle_endtag(self, tag):
        if tag == "li":
            self.current = None


def release(repo, requested):
    suffix = "latest" if requested == "latest" else "tags/" + quote(requested, safe="")
    try:
        result = json.loads(fetch_bytes(f"https://api.github.com/repos/{repo}/releases/{suffix}", 8*1024**2))
        if result.get("draft") or (requested == "latest" and result.get("prerelease")):
            raise ValueError("Upstream has no current public release")
        return result["tag_name"], result["assets"]
    except HTTPError as exc:
        if exc.code not in (403, 429):
            raise
    tag = requested
    if tag == "latest":
        prefix = f"https://github.com/{repo}/releases/tag/"
        with engines.open_upstream(Request(f"https://github.com/{repo}/releases/latest", method="HEAD")) as page:
            if not page.url.lower().startswith(prefix.lower()):
                raise ValueError("Unexpected upstream release redirect")
            tag = unquote(page.url[len(prefix):])
    quoted = quote(tag, safe="")
    parser = AssetLinks(f"/{repo}/releases/download/{quoted}/")
    parser.feed(fetch_bytes(f"https://github.com/{repo}/releases/expanded_assets/{quoted}", 8*1024**2).decode())
    if not parser.items:
        raise ValueError("Could not read the upstream release asset list")
    return tag, parser.items


@lru_cache(maxsize=4)
def core_index(target, refresh=None):
    path, _ = TARGETS[target]
    url = f"{BUILD_SERVER}/{path}/latest/.index-extended"
    if refresh is not None:
        url += f"?refresh={refresh}"
    raw = fetch_bytes(url, 2*1024**2)
    entries = {}
    for line in raw.decode().splitlines():
        fields = line.split()
        if len(fields) == 3 and re.fullmatch(r"[0-9a-fA-F]{8}", fields[1]):
            entries[fields[2]] = (fields[0], fields[1].lower())
    return entries


def resolve(key, target, channel="auto", version="latest", index_refresh=None):
    if key == "cartssnes":
        raise ValueError("Select your CartsSNES libretro build with --core PATH")
    item = CATALOG[key]
    if not re.fullmatch(r"[A-Za-z0-9][\w.+-]{0,79}", version):
        raise ValueError("Invalid release tag")
    if channel != "core" and target in item.assets:
        tag, assets = release(item.repo, version)
        matches = [a for a in assets if re.fullmatch(item.assets[target], a["name"], re.I)]
        if len(matches) > 1:
            raise ValueError("Multiple upstream packages match this target")
        if matches:
            a = matches[0]
            name = a["name"]
            url = a["browser_download_url"]
            if url != f"https://github.com/{item.repo}/releases/download/{quote(tag,safe='')}/{quote(name)}":
                raise ValueError("Unexpected upstream asset URL")
            digest = a.get("digest") or ""
            if digest and not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError("Unsupported upstream checksum")
            ident = digest or (str(a["id"]) + ":" + a["updated_at"] if "id" in a else "")
            return Package(key, target, "desktop", tag, name, url, ident, digest, a.get("size", 0))
    if channel == "desktop" or version != "latest":
        raise ValueError(f"No matching desktop package for {item.name} {version} on {target}")
    if not item.core:
        raise ValueError(f"No published libretro core for {item.name} on {target}")
    path, ext = TARGETS[target]
    if path is None:
        raise ValueError(f"No upstream {target} prebuilt for {item.name}. Use a native --core or install mgba --version latest.")
    member = f"{item.core}_libretro.{ext}"
    name = member + ".zip"
    info = core_index(target, index_refresh).get(name)
    if not info:
        raise ValueError(f"{name} is absent from the current {target} build index")
    date, crc = info
    return Package(key, target, "core", f"{date}+{crc}", name, f"{BUILD_SERVER}/{path}/latest/{name}",
                   date + ":" + crc, "crc32:" + crc, member=member)


def check_arch(path, target):
    with path.open("rb") as f:
        head = f.read(4096)
        if target.startswith("macos"):
            cpu = 0x100000c if target.endswith("arm64") else 0x1000007
            if head[:4] == b"\xcf\xfa\xed\xfe" and int.from_bytes(head[4:8], "little") == cpu:
                return
            if head[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
                stride = 20 if head[3] == 0xbe else 32
                count = int.from_bytes(head[4:8], "big")
                if 0 < count <= (len(head)-8)//stride and any(
                        int.from_bytes(head[8+i*stride:12+i*stride], "big") == cpu for i in range(count)):
                    return
        elif target in ("linux-x64", "linux-arm64"):
            if head[:6] == b"\x7fELF\x02\x01" and int.from_bytes(head[18:20], "little") == (183 if target.endswith("arm64") else 62):
                return
        elif target in ("windows-arm64", "windows-x64") and head.startswith(b"MZ") and len(head) >= 64:
            offset, = struct.unpack_from("<I", head, 60)
            f.seek(offset)
            if f.read(4) == b"PE\0\0" and int.from_bytes(f.read(2), "little") == (0xaa64 if target.endswith("arm64") else 0x8664):
                return
    raise ValueError(f"Downloaded executable does not match {target}")


class CoreIndexMismatch(ValueError):
    """A moving nightly archive differs from its rolling index."""


def prepare_file(spec, archive, stage):
    if spec.member:
        with ZipFile(archive) as z:
            matches = [m for m in z.infolist() if m.filename == spec.member]
            if len(matches) != 1 or not 0 < matches[0].file_size <= MAX_BYTES:
                raise ValueError("Missing or invalid core in ZIP")
            if spec.checksum.startswith("crc32:"):
                if f"crc32:{matches[0].CRC:08x}" != spec.checksum:
                    raise CoreIndexMismatch("Core CRC differs from the published build index")
            elif not spec.checksum.startswith("member-sha256:"):
                raise ValueError("Missing core fingerprint")
            out = stage / spec.member
            with z.open(matches[0]) as src, out.open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024*1024)
        if spec.checksum.startswith("member-sha256:") and engines.digest(out) != spec.checksum.split(":")[1]:
            raise ValueError("Core SHA-256 differs from its signed Libretro release")
        check_arch(out, spec.target)
        return out
    with archive.open("rb") as f:
        head = f.read(8)
        ext = Path(spec.name).suffix.lower()
        if ext == ".dmg":
            f.seek(-512, os.SEEK_END)
            valid = f.read(4) == b"koly"
        elif ext == ".zip":
            with ZipFile(archive) as z:
                valid = bool(z.infolist()) and sum(i.file_size for i in z.infolist()) <= 4*MAX_BYTES and z.testzip() is None
        elif ext == ".appimage":
            check_arch(archive, spec.target)
            valid = True
        else:
            magic = {".7z": b"7z\xbc\xaf\x27\x1c", ".deb": b"!<arch>\n", ".exe": b"MZ"}
            valid = ext in magic and head.startswith(magic[ext])
        if not valid:
            raise ValueError("File contents do not match the advertised package format")
    return archive


def transfer(spec, path, attempt=0):
    digest = sha256()
    length = 0
    url = spec.url
    if spec.member and spec.checksum.startswith("crc32:"):
        # Nightly archives and their index can reach an upstream CDN edge at different times.
        # Each URL must still produce the exact indexed CRC and native architecture.
        if attempt == 0:
            url += "?crc32=" + spec.checksum.removeprefix("crc32:")
        elif attempt > 1:
            url += "?refresh=" + str(time.time_ns())
    elif spec.member and spec.checksum.startswith("member-sha256:"):
        url += "?sha256=" + spec.checksum.split(":")[1]
    with engines.open_upstream(Request(url, headers={"User-Agent": "EmuBench/0.8"})) as response, path.open("wb") as f:
        if not response.url.startswith("https://"):
            raise ValueError("Insecure upstream redirect")
        header = response.headers.get("Content-Length")
        for block in iter(lambda: response.read(1024*1024), b""):
            length += len(block)
            if length > MAX_BYTES:
                raise ValueError("Package exceeds the download size limit")
            f.write(block)
            digest.update(block)
        if not length or (header is not None and int(header) != length) or (spec.size and spec.size != length):
            raise ValueError("Incomplete upstream download")
    result = digest.hexdigest()
    if spec.checksum.startswith("sha256:") and spec.checksum != "sha256:" + result:
        raise ValueError("Package SHA-256 differs from the upstream digest")
    return result


def obtain(spec, attempt=0):
    root = engines.home() / "downloads" / spec.emulator / spec.target / spec.channel
    refs = root / "receipts"
    refs.mkdir(parents=True, exist_ok=True)
    identity = sha256(json.dumps(asdict(spec), sort_keys=True).encode()).hexdigest()
    receipt = refs / (identity + ".json")
    filename = spec.member or spec.name
    if spec.identity and receipt.exists():
        try:
            meta = json.loads(receipt.read_text(encoding="utf-8"))
            sha = meta["file_sha256"]
            if re.fullmatch(r"[0-9a-f]{64}", sha):
                cached = root / sha / filename
                if cached.is_file() and engines.digest(cached) == sha and (
                        not spec.checksum.startswith(("sha256:", "member-sha256:")) or spec.checksum.split(":")[1] == sha):
                    return cached, meta
        except (KeyError, TypeError, ValueError):
            pass
    with tempfile.TemporaryDirectory(dir=root) as folder:
        stage = Path(folder)
        archive = stage / "payload"
        archive_sha = transfer(spec, archive, attempt)
        payload = prepare_file(spec, archive, stage)
        file_sha = engines.digest(payload) if spec.member else archive_sha
        dest = root / file_sha / filename
        dest.parent.mkdir(exist_ok=True)
        if not dest.exists() or engines.digest(dest) != file_sha:
            try:
                os.replace(payload, dest)
            except PermissionError:
                # A parallel download already placed the same verified file (Windows).
                if not (dest.is_file() and engines.digest(dest) == file_sha):
                    raise
        meta = {**asdict(spec), "archive_sha256": archive_sha, "file_sha256": file_sha}
        staged_receipt = stage / "receipt.json"
        staged_receipt.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        _publish_receipt(staged_receipt, receipt)
        return dest, meta


def _publish_receipt(staged, receipt):
    """Windows refuses a replace while another download swaps the same receipt in.
    Two parallel downloads of one spec write identical receipts, so a receipt that
    already matches is fine; otherwise retry briefly."""
    for wait in (0.05, 0.1, 0.2, 0.4, 0.8, None):
        try:
            os.replace(staged, receipt)
            return
        except PermissionError:
            try:
                if receipt.read_bytes() == staged.read_bytes():
                    return
            except OSError:
                pass
            if wait is None:
                raise
            time.sleep(wait)


def get(key, target, channel="auto", version="latest", plan=False):
    index_refresh = None
    previous_checksum = None
    archive_attempt = 0
    for attempt in range(3):
        try:
            spec = resolve(key, target, channel, version, index_refresh)
            if plan:
                return spec, None
            if spec.checksum != previous_checksum:
                archive_attempt = 0
                previous_checksum = spec.checksum
            path, _ = obtain(spec, archive_attempt)
            return spec, path
        except (URLError, TimeoutError, ConnectionError, BadZipFile, EOFError, OSError, ValueError, HTTPException) as exc:
            transient = isinstance(exc, (URLError, TimeoutError, ConnectionError, IncompleteRead)) and not isinstance(exc, HTTPError)
            if isinstance(exc, HTTPError):
                transient = exc.code in (408, 429, 500, 502, 503, 504)
            # Rolling build index and file may change between two HTTPS requests.
            rotate = isinstance(exc, ValueError) and "differs from" in str(exc)
            if attempt == 2 and isinstance(exc, CoreIndexMismatch):
                from . import core_signature
                try:
                    signed = core_signature.resolve(spec)
                except HTTPError as missing:
                    if (missing.code != 404 or key not in ("bsnes","snes9x")
                            or target != host_target() or not target.startswith("macos-")):
                        raise
                    from . import snes_build
                    path, meta = snes_build.install(key, target=target)
                    built = replace(spec, channel="source", version=meta["commit"][:12], name=path.name,
                                    identity=meta["commit"], checksum="sha256:"+meta["sha256"], member="",
                                    url=snes_build.REPOS[key])
                    return built, path
                path, _ = obtain(signed)
                return signed, path
            if attempt == 2 or not (transient or rotate):
                raise
            core_index.cache_clear()
            if rotate:
                archive_attempt += 1
                index_refresh = time.time_ns()
            time.sleep(1 + attempt)


def latest_core(key):
    if host_target() == "windows-arm64":
        if key == "mgba":
            return engines.install("latest")[0]
        if key in ("snes9x","bsnes"):
            from . import winarm
            return winarm.install(key)[0]
        spec,path=get(key,"windows-x64","core")
        print(f"{CATALOG[key].name}: x64 core using Windows on Arm translation",file=sys.stderr)
        return path
    try:
        spec, path = get(key, host_target(), "core")
    except ValueError as exc:
        if key!="sameboy" or host_target()!="linux-arm64" or "absent from" not in str(exc):
            raise
        from . import sameboy_linux
        return sameboy_linux.install()

    print(f"{CATALOG[key].name} core {spec.version}: {path}", file=sys.stderr)
    return path


def emulator_id(text):
    value = re.sub(r"[^a-z0-9]", "", text.lower())
    for key, item in CATALOG.items():
        if value in {re.sub(r"[^a-z0-9]", "", v.lower()) for v in (key, item.name, item.core or key)}:
            return key
    return text


def describe(spec, path):
    kind = {"core":"libretro build","source":"upstream source build","desktop":"upstream desktop package"}[spec.channel]
    print(f"{CATALOG[spec.emulator].name} · {kind} · {spec.version} · {spec.target}\n  {path or spec.url}")


def batch(keys, target, channel, version, plan):
    failures = 0
    for key in keys:
        selected=("core" if CATALOG[key].core else "desktop") if channel=="bench" else channel
        try:
            if key=="sameboy" and target=="linux-arm64" and selected in ("core","auto") and "sameboy_libretro.so.zip" not in core_index(target):
                if plan:
                    print("SameBoy: native source build from the upstream release on Linux ARM64")
                elif target==host_target():
                    from . import sameboy_linux
                    print(sameboy_linux.install(version))
                else:
                    raise ValueError("Run the SameBoy source installer on the target Linux ARM64 machine")
            elif target == "windows-arm64" and selected != "desktop" and key in ("mgba","snes9x","bsnes"):
                if plan:
                    print(f"{CATALOG[key].name}: native upstream source build ({version})")
                elif target!=host_target():
                    raise ValueError("Run the native source installer on the target Windows ARM64 machine")
                elif key == "mgba":
                    print(engines.install(version)[0])
                else:
                    from . import winarm
                    print(winarm.install(key, None if version == "latest" else version)[0])
            else:
                actual="windows-x64" if target=="windows-arm64" and selected=="core" and key not in ("mgba","snes9x","bsnes") else target
                describe(*get(key, actual, selected, version, plan))
        except (OSError, ValueError, BadZipFile, EOFError, HTTPException) as exc:
            failures += 1
            print(f"{CATALOG[key].name}: {exc}", file=sys.stderr)
    return int(failures != 0)
