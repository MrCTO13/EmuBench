"""Exercise the release downloader against a real public, pinned homebrew test suite."""
import tempfile
from pathlib import Path
from emubench import accuracy, carter, engines
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/"test-suite.zip"
    carter.fetch_asset(accuracy.SNES_SOURCE,accuracy.SNES_ARCHIVE,path)
    assert engines.digest(path)==accuracy.SNES_ARCHIVE
    try:
        carter.fetch_asset(accuracy.SNES_SOURCE,"0"*64,path)
    except ValueError as exc:
        assert "SHA-256" in str(exc)
    else:
        raise AssertionError("accepted wrong digest")
    assert engines.digest(path)==accuracy.SNES_ARCHIVE

    import os
    os.environ.update(EMUBENCH_HOME=tmp,PATH="")
    for console,game in carter.GAMES.items():
        assert engines.digest(carter.cartridge(console,None))==game.digest

    from emubench import games
    root = games.install()
    assert len(games.PACK["games"]) == 12
    assert {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} == set(games.FILES)
    for console, game in carter.GAMES.items():
        assert carter.cartridge(console, None) == root / "roms" / console / game.filename
    first = root / games.PACK["games"][0]["path"]
    first.write_bytes(b"damaged")
    try:
        games.install()
    except ValueError as exc:
        assert first.name in str(exc)
    else:
        raise AssertionError("accepted a corrupted Carter game")
