"""Assemble a portable desktop release without emulator binaries."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from emubench import engines
from emubench.catalog import host_target

target=host_target()
dest=Path("distribution")
if (dest/"reference").exists():
    raise ValueError("Use a fresh distribution directory without legacy emulator binaries")
dest.mkdir(exist_ok=True)
binary="emubench"+engines.EXE
for path in (Path("dist")/binary,Path("dist/scores.html"),Path("LICENSE"),Path("README.md"),Path("THIRD-PARTY.md")):
    shutil.copy2(path,dest)
shutil.copytree("dist/third-party",dest/"third-party",dirs_exist_ok=True)
shutil.copy2("emubench/native/libretro.h",dest/"libretro-header.h")
if target.startswith("macos"):
    launcher=dest/"Open Emu Bench.command"
    launcher.write_text('#!/bin/sh\nexec "$(dirname "$0")/emubench" desktop\n')
    launcher.chmod(0o755)
shutil.make_archive("emubench-"+target,"zip",dest)
