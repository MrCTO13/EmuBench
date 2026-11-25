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
