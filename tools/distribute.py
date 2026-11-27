"""Assemble a desktop release from the CLI, notices and original Carter games."""
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emubench import engines, games
from emubench.catalog import host_target


def stage_release(stage):
    binary = Path("dist") / ("emubench" + engines.EXE)
    pack = games.install()
    for path in (binary, Path("dist/scores.html"), Path("LICENSE"), Path("README.md"), Path("THIRD-PARTY.md")):
        shutil.copy2(path, stage)
    shutil.copytree("dist/third-party", stage / "third-party")
    shutil.copy2("emubench/native/libretro.h", stage / "libretro-header.h")
    for name in games.FILES:
        dest = stage / "games" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pack / name, dest)
    games.verify(stage / "games")


def distribute():
    target = host_target()
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        stage_release(stage)
        if target.startswith("macos"):
            launcher = stage / "Open Emu Bench.command"
            launcher.write_text('#!/bin/sh\nexec "$(dirname "$0")/emubench" desktop\n')
            launcher.chmod(0o755)
        shutil.make_archive("emubench-" + target, "zip", stage)
        shutil.copytree(stage, "distribution", dirs_exist_ok=True)


if __name__ == "__main__":
    distribute()
