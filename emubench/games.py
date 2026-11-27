"""Verified, freely distributed Carter homebrew editions and their notices."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from zipfile import ZipFile

from . import downloads, engines

PACK = json.loads(Path(__file__).with_name("carter_games.json").read_text(encoding="utf-8"))
URL = "https://github.com/MrCTO13/EmuBench/releases/download/carter-games-v1/" + PACK["asset"]
FILES = {**PACK["notices"], **{game["path"]: game["sha256"] for game in PACK["games"]}}


def roots():
    if getattr(sys, "frozen", False):
        yield Path(sys.executable).resolve().parent / "games"
    yield engines.home() / "games" / PACK["sha256"]


def verify(root):
    for name, digest in FILES.items():
        path = root / name
        if not path.is_file() or engines.digest(path) != digest:
            raise ValueError(f"Missing or damaged Carter game pack file: {name}")
    return root


def install():
    for root in roots():
        if root.is_dir():
            return verify(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    data = downloads.fetch_bytes(URL, PACK["size"])
    if len(data) != PACK["size"] or hashlib.sha256(data).hexdigest() != PACK["sha256"]:
        raise ValueError("The Carter game pack failed its release SHA-256 check")
    with tempfile.TemporaryDirectory(dir=root.parent) as tmp:
        stage = Path(tmp) / "games"
        with ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (len(entries) != len(FILES) or set(archive.namelist()) != set(FILES)
                    or sum(i.file_size for i in entries) > 96 * 1024**2):
                raise ValueError("Unexpected Carter game pack contents")
            for name in FILES:
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, path.open("xb") as dest:
                    shutil.copyfileobj(src, dest)
        verify(stage)
        try:
            stage.rename(root)
        except OSError:
            if not root.is_dir():
                raise
            verify(root)
    return root


def list_games():
    from . import adapters, carter
    replay = {game.digest for game in carter.GAMES.values()}
    for game in PACK["games"]:
        if game["sha256"] in replay:
            mode = "Carter replay"
        elif game["console"] in adapters.ROUTES:
            mode = "Local ROM benchmark"
        else:
            mode = "Game only (timing unavailable)"
        print(f"{game['console'].upper():<10} {game['title']:<24} {game['edition']:<20} {mode}")
