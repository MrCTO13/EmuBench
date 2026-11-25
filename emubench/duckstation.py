"""Read the standalone regression runner's own average, separate from the frame-timed board."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
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
    version=subprocess.run([runner,"-version"],capture_output=True,text=True,timeout=15,check=True)
    identity=re.search(r"DuckStation Regression Test Runner Version ([^\r\n]+)",version.stdout+version.stderr)
    if not identity:
        raise ValueError("Executable did not identify as the DuckStation regression runner")
    with tempfile.TemporaryDirectory() as folder:
        command=[runner,"-console","-log","info","-renderer","Software","-frames",str(args.frames),
                 "-dumpdir",folder,"-dumpinterval",str(max(1,args.frames//2)),
                 "-setting","Folders/Bios="+str(firmware),"--",rom]
        # Keep the upstream log private. Only its total and checkpoint existence enter the receipt.
        output=subprocess.run(command,cwd=folder,capture_output=True,timeout=args.timeout)
        log=(output.stdout+output.stderr).decode(errors="replace")
        summary=re.search(r"Total execution time: ([0-9.]+)ms, average frame time [0-9.]+ms, ([0-9.]+) FPS",log)
        images=list(Path(folder).rglob("*.png"))
        if output.returncode or not summary or "GAME NOT STARTED" in log or not images or not all(
            valid_png(path) for path in images):
            raise ValueError("DuckStation did not confirm game startup, timing and a rendered checkpoint")
    result={"id":str(uuid.uuid4()),"finished_utc":journal.now(),"emulator":"DuckStation","version":identity[1],
            "profile":"duckstation-regtest-total-v1","frames":args.frames,"average_fps":round(float(summary[2])),
            "elapsed_ms":float(summary[1]),"render_checkpoints":len(images),"runner_sha256":engines.digest(runner)}
    dest=engines.home()/"regtest"/(result["id"]+".json")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(f"DuckStation · {result['average_fps']} average FPS · {len(images)} rendered checkpoints\nPrivate report: {dest}")

def valid_png(path):
    with path.open("rb") as f:
        return f.read(8)==bytes.fromhex("89504e470d0a1a0a")
