"""Assemble a portable desktop release with the exact, rebuildable reference mGBA core."""
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
dest.mkdir(exist_ok=True)
binary="emubench"+engines.EXE
for path in (Path("dist")/binary,Path("dist/scores.html"),Path("LICENSE"),Path("README.md"),Path("THIRD-PARTY.md")):
    shutil.copy2(path,dest)
shutil.copytree("dist/third-party",dest/"third-party",dirs_exist_ok=True)
shutil.copy2("emubench/native/libretro.h",dest/"libretro-header.h")
reference=dest/"reference"
reference.mkdir(exist_ok=True)
core,meta=engines.install(engines.REFERENCE)
shutil.copy2(core,reference/core.name)
(reference/"build.json").write_text(json.dumps(meta),encoding="utf-8")
with tempfile.TemporaryDirectory() as temp:
    upstream=Path(temp)/"mgba"
    subprocess.run(["git","clone","--depth","1","--branch",engines.REFERENCE,engines.UPSTREAM,upstream],check=True)
    commit=subprocess.check_output(["git","-C",upstream,"rev-parse","HEAD"],text=True).strip()
    if commit!=engines.REFERENCE_COMMIT:
        raise ValueError("Reference tag has changed")
    archive=(reference/"mgba-source.zip").resolve()
    # Cinema is an upstream regression corpus. It is independent of the libretro target.
    subprocess.run(["git","-C",upstream,"archive","--format=zip","-o",archive,"HEAD","--",".",":(exclude)cinema"],check=True)
    with ZipFile(archive) as z:
        if any(Path(n).suffix.lower() in {".gb",".gbc",".gba",".sfc",".smc",".nes",".rom",".bios",".nand"} for n in z.namelist()):
            raise ValueError("Unexpected cartridge in reference source")
    shutil.copy2(upstream/"LICENSE",reference/"LICENSE-mGBA.txt")
    shutil.copytree(upstream/"res/licenses",reference/"component-licenses",dirs_exist_ok=True)
if target.startswith("macos"):
    launcher=dest/"Open Emu Bench.command"
    launcher.write_text('#!/bin/sh\nexec "$(dirname "$0")/emubench" desktop\n')
    launcher.chmod(0o755)
shutil.make_archive("emubench-"+target,"zip",dest)
