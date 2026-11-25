"""Build native Windows ARM64 SNES cores directly from their upstream sources."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from . import engines

REPOS = {"snes9x":"https://github.com/libretro/snes9x.git","bsnes":"https://github.com/libretro/bsnes-libretro.git"}


def install(emulator, revision=None):
    """MSYS2 make and Zig are build tools only. Resulting DLLs are native ARM64."""
    from .downloads import check_arch
    repo=REPOS[emulator]
    commit=revision or subprocess.check_output(["git","ls-remote",repo,"HEAD"],text=True,timeout=45).split()[0]
    if not engines.SHA.fullmatch(commit):
        raise ValueError("Expected an immutable upstream commit")
    base=engines.home()/"engines"/"windows-arm64"/emulator
    dest=base/commit
    filename=emulator+"_libretro.dll"
    if not dest.is_dir():
        make=shutil.which("make") or next((str(p) for p in (Path("C:/msys64/usr/bin/make.exe"),
                    Path("D:/a/_temp/msys64/usr/bin/make.exe")) if p.is_file()),None)
        zig=shutil.which("zig")
        if not make or not zig:
            raise ValueError("Building a native Windows ARM64 SNES core requires Git, MSYS2 GNU make and Zig on PATH. You can also pass --core PATH.")
        base.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            source=Path(tmp)/"upstream"
            engines.call(["git","init","-q",source])
            engines.call(["git","-C",source,"fetch","--depth","1",repo,commit])
            engines.call(["git","-C",source,"checkout","--detach","FETCH_HEAD"])
            if subprocess.check_output(["git","-C",source,"rev-parse","HEAD"],text=True).strip()!=commit:
                raise ValueError("Upstream core revision changed")
            build=source/"libretro" if emulator=="snes9x" else source
            if emulator=="bsnes":
                # Select bsnes' existing Windows Fiber backend. Its generic AArch64
                # assembly backend uses the POSIX mprotect API on this revision.
                manifest=source/"Makefile.common"
                rules=manifest.read_text()
                if rules.count("libco/libco.c")!=1 or not (source/"libco/fiber.c").is_file():
                    raise ValueError("Review the upstream Windows Fiber build rule for this revision")
                manifest.write_text(rules.replace("libco/libco.c","libco/fiber.c"))
            env=os.environ.copy()
            env["PATH"]=str(Path(make).parent)+os.pathsep+env["PATH"]
            subprocess.run([make,"-j2","platform=win","IS_X86=0","LTO=","SHARED=-shared",
                            "CC=zig cc -w -target aarch64-windows-gnu","CXX=zig c++ -w -target aarch64-windows-gnu"],
                           cwd=build,env=env,check=True)
            artifact=build/filename
            check_arch(artifact,"windows-arm64")
            stage=Path(tmp)/"ready"
            stage.mkdir()
            shutil.copy2(artifact,stage/filename)
            (stage/"build.json").write_text(json.dumps({"commit":commit,"sha256":engines.digest(artifact)}))
            engines.promote(stage,dest)
    core=dest/filename
    meta=json.loads((dest/"build.json").read_text())
    if meta["commit"]!=commit or meta["sha256"]!=engines.digest(core):
        raise ValueError("Cached Windows core failed verification")
    return core,meta
