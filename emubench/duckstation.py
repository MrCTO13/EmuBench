"""Read the standalone regression runner's own average, separate from the frame-timed board."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from . import standalone
from . import engines, journal

def arguments(commands):
    p=commands.add_parser("duckstation",help="Measure a local PlayStation image with the upstream regression runner")
    p.add_argument("--rom",required=True,type=Path)
    p.add_argument("--runner",type=Path,help="Path to duckstation-regtest (default: search PATH)")
    p.add_argument("--frames",type=int,default=1800)
    p.add_argument("--system-dir",required=True,type=Path,help="Directory containing your PlayStation BIOS")
    p.add_argument("--timeout",type=int,default=300)

def execute(args):
    runner=args.runner or shutil.which("duckstation-regtest")
    if not runner:
        raise ValueError("Select the upstream duckstation-regtest executable with --runner")
    runner=Path(runner).resolve(strict=True)
    rom=args.rom.resolve(strict=True)
    firmware=args.system_dir.resolve(strict=True)
    if not rom.is_file() or not firmware.is_dir() or not 100<=args.frames<=1000000 or args.timeout<=0:
        raise ValueError("Choose a local image, firmware directory and a valid measurement window")
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        local=root/runner.name
        shutil.copy2(runner,local)
        runner_hash=engines.digest(local)
        # Regtest establishes its BIOS and save folders before processing command-line settings.
        # A private portable layout also avoids changing the player's DuckStation data.
        (root/"portable.txt").touch()
        resources=runner.parent/"resources"
        if not resources.is_dir():
            resources=runner.parent.parent/"Resources"
        if not resources.is_dir():
            raise ValueError("The regression runner needs its upstream resources directory")
        try:
            (root/"resources").symlink_to(resources,target_is_directory=True)
        except OSError:
            shutil.copytree(resources,root/"resources")
        for sibling in runner.parent.iterdir():
            if sibling.is_file() and (sibling.suffix.lower() in (".dll",".dylib",".so") or ".so." in sibling.name):
                shutil.copy2(sibling,root/sibling.name)
        bios=root/"bios"
        bios.mkdir()
        for item in firmware.iterdir():
            if item.is_file() and item.stat().st_size in (524288,4194304):
                shutil.copyfile(item,bios/item.name)
        if not any(bios.iterdir()):
            raise ValueError("No supported PlayStation BIOS image in --system-dir")
        version=subprocess.run([local,"-version"],cwd=root,capture_output=True,text=True,timeout=15)
        identity=re.search(r"DuckStation Regression Test Runner Version ([^\r\n]+)",version.stdout+version.stderr)
        if version.returncode not in (0,1) or not identity:
            raise ValueError("Executable did not identify as the DuckStation regression runner")
        dumps=root/"checkpoints"
        dumps.mkdir()
        command=[local,"-console","-log","Verbose","-renderer","Software","-frames",str(args.frames),
                 "-dumpdir",dumps,"-dumpinterval",str(max(1,args.frames//2)),"--",rom]
        # Keep the upstream log private. Only its total and checkpoint existence enter the receipt.
        output,elapsed=standalone.timed(command,folder,args.timeout)
        log=(output.stdout+output.stderr).decode(errors="replace")
        summary=re.search(r"Total execution time: ([0-9.]+)ms, average frame time [0-9.]+ms, ([0-9.]+) FPS",log)
        images=list(dumps.rglob("frame_*.png"))
        if output.returncode or not summary or "GAME NOT STARTED" in log or not images or not all(
            valid_png(path) for path in images):
            raise ValueError("DuckStation did not confirm game startup, timing and a rendered checkpoint")
        rates = re.findall(r"Video frame rate changed from [0-9.]+ to ([0-9.]+) fps",log)
        if not rates:
            raise ValueError("DuckStation did not report a guest video mode")
        # Match the rounded upstream log to the CRTC clock and scan geometry from GPU.cpp.
        observed = float(rates[-1])
        candidates = [clock/(line/2)/lines for clock in (53693175,53203425)
                      for line, counts in ((6825,(263,262.5)),(6810,(314,312.5)))
                      for lines in counts]
        match = [hz for hz in candidates if abs(hz-observed)<0.0051]
        if len(match)!=1:
            raise ValueError("Unknown PlayStation refresh mode")
        standalone.receipt("DuckStation",identity[1],runner_hash,args.frames,elapsed,match[0],len(images))


def valid_png(path):
    with path.open("rb") as f:
        return f.read(8)==bytes.fromhex("89504e470d0a1a0a")
