"""Discover local cartridge images without extracting archives to disk."""
from collections import Counter
from hashlib import sha256
from pathlib import Path, PurePosixPath
import os
import stat
import sys
from zipfile import BadZipFile, ZipFile
import zlib
import lzma

from . import adapters, engines

SUPPORTED = {ext:adapters.ROUTES[console][1] for ext,console in adapters.SUFFIXES.items()}
EXTERNAL = {".pbp", ".chd", ".zip"}
MAX_SIZE = 32 * 1024**2
ARCHIVE_ERRORS = (BadZipFile, RuntimeError, EOFError, zlib.error, lzma.LZMAError)


def check_size(name, size, emulator):
    suffix = Path(name).suffix.lower()
    if ("snes9x" if emulator == "cartssnes" else emulator) not in SUPPORTED.get(suffix, ()):
        raise ValueError(f"Unsupported cartridge format for {emulator}")
    minimum = {".sfc":32768, ".smc":32768, ".nes":16}.get(suffix,192)
    if suffix in EXTERNAL:
        if size < minimum:
            raise ValueError("Empty or incomplete content file")
        return
    if not minimum <= size <= MAX_SIZE:
        raise ValueError(f"Expected a cartridge between {minimum} bytes and 32 MiB")


def check_header(data, emulator):
    if emulator in ("mgba","gpsp") and data[3:4] != b"\xea":
        raise ValueError("This file does not have the expected GBA cartridge header")


def read_member(archive, entry, emulator):
    check_size(entry.filename, entry.file_size, emulator)
    if entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
        raise ValueError("Encrypted and symbolic-link ZIP members are unsupported")
    try:
        with archive.open(entry) as stream:
            data = stream.read(MAX_SIZE + 1)
    except ARCHIVE_ERRORS as exc:
        raise ValueError(f"Unreadable ZIP member: {exc}") from exc
    if len(data) != entry.file_size:
        raise ValueError("ZIP member length changed")
    return data


def read_pinned_member(path, member, emulator):
    try:
        with ZipFile(path) as archive:
            return read_member(archive, archive.getinfo(member), emulator)
    except (KeyError, *ARCHIVE_ERRORS) as exc:
        raise ValueError(f"Cannot read the queued ZIP member: {exc}") from exc


def discover(roots, emulator):
    workloads = []
    seen = set()
    counts = Counter()

    def skipped(path, reason):
        counts["skipped"] += 1
        print(f"Skipped {path}: {reason}", file=sys.stderr)

    def add(path, member, data, peers):
        check_header(data, peers[0])
        digest = sha256(data).hexdigest()
        if (digest, peers) in seen:
            counts["duplicates"] += 1
            return
        seen.add((digest, peers))
        for peer in peers:
            item = dict(path=str(path), sha256=digest, emulator=peer)
            if member is not None:
                item["member"] = member
            workloads.append(item)

    def compatible(suffix):
        peers = SUPPORTED.get(suffix.lower(), ())
        if emulator == "cartssnes" and "snes9x" in peers:
            return ("cartssnes",)
        if suffix.lower() == ".zip":
            return peers if emulator=="arcade" else tuple(p for p in peers if p==emulator)
        return peers if emulator == "all" else tuple(peer for peer in peers if peer == emulator)

    def scan(path, explicit=False):
        peers = compatible(path.suffix)
        if not peers and path.suffix.lower() != ".zip":
            if explicit:
                raise ValueError(f"No compatible emulator for {path}")
            counts["other files"] += 1
            return
        try:
            if not path.is_file():
                raise ValueError("Expected a regular file")
            if peers and path.suffix.lower() in EXTERNAL:
                check_size(path.name, path.stat().st_size, peers[0])
                if path.suffix.lower()==".chd" and emulator=="all":
                    return  # Several systems share CHD. Require a selected emulator.
                digest = engines.digest(path)
                identity = (digest, peers, path.stem if path.suffix.lower()==".zip" else "")
                if identity in seen:
                    counts["duplicates"] += 1
                    return
                seen.add(identity)
                workloads.extend(dict(path=str(path), sha256=digest, emulator=p) for p in peers)
                return
            if peers:
                check_size(path.name, path.stat().st_size, peers[0])
                with path.open("rb") as stream:
                    if path.suffix.lower()==".exe" and stream.read(8)!=b"PS-X EXE":
                        return
                    stream.seek(0)
                    data = stream.read(MAX_SIZE + 1)
                check_size(path.name, len(data), peers[0])
                add(path, None, data, peers)
                return
            with ZipFile(path) as archive:
                entries = archive.infolist()
                names = Counter(entry.filename for entry in entries)
                for entry in entries:
                    name = PurePosixPath(entry.filename.replace("\\", "/"))
                    peers = compatible(name.suffix)
                    if name.suffix.lower() in EXTERNAL or not peers or entry.is_dir() or "__MACOSX" in name.parts or name.name.startswith("._"):
                        continue
                    try:
                        if names[entry.filename] != 1:
                            raise ValueError("Ambiguous duplicate member name")
                        data = read_member(archive, entry, peers[0])
                        add(path, entry.filename, data, peers)
                    except (OSError, ValueError) as exc:
                        skipped(f"{path} / {entry.filename}", exc)
        except (OSError, ValueError, *ARCHIVE_ERRORS) as exc:
            if explicit:
                raise ValueError(f"Cannot scan {path}: {exc}") from exc
            skipped(path, exc)

    def linked(path):
        entry = path.lstat()
        # A Windows junction can loop just like a symlink. Other reparse points include cloud files.
        return stat.S_ISLNK(entry.st_mode) or (
            os.name == "nt" and entry.st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT)

    visited = set()
    for root in roots:
        if not root.is_dir():
            scan(root, explicit=True)
            continue
        for directory, folders, files in os.walk(root, onerror=lambda exc: skipped(exc.filename, exc)):
            base = Path(directory)
            if base in visited:
                folders.clear()
                continue
            visited.add(base)
            children = []
            for folder in sorted(folders):
                try:
                    if folder not in (".git", "__MACOSX") and not linked(base / folder):
                        children.append(folder)
                except OSError as exc:
                    skipped(base / folder, exc)
            folders[:] = children
            for filename in sorted(files):
                path = base / filename
                try:
                    if not filename.startswith("._") and not linked(path):
                        scan(path)
                except OSError as exc:
                    skipped(path, exc)
    print(f"Scan found {len(seen)} unique compatible cartridges, {counts['duplicates']} duplicate copies, "
          f"{counts['skipped']} unreadable or invalid entries and {counts['other files']} other files.")
    if not workloads:
        raise ValueError("No compatible cartridges found in the supplied paths")
    return workloads
