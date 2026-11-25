"""Produce a downloadable single executable with the native timing worker embedded."""
from pathlib import Path
import os
import shutil
import sysconfig
from importlib import metadata
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emubench import engines
from emubench.catalog import host_target
from emubench.engines import worker
from emubench.details import template_html

native = worker()
entry = Path("build/entry.py")
entry.parent.mkdir(exist_ok=True)
entry.write_text("from emubench.cli import main\nraise SystemExit(main())\n", encoding="utf-8")
extra=[]
if host_target()=="windows-arm64":
    cross=Path("build/worker-x64").resolve()
    engines.compile_target(engines.NATIVE,cross,"emubench-worker",["-A","x64"])
    named=Path("build/emubench-worker-x64.exe")
    shutil.copy2(engines.artifact(cross,"emubench-worker.exe"),named)
    extra=["--add-binary",str(named)+os.pathsep+"emubench/native/bin"]
subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
                *extra, "--paths", ".", "--name", "emubench", "--hidden-import", "_cffi_backend",
                "--add-data", "emubench/carter_games.json" + os.pathsep + "emubench",
                "--add-data", "emubench/studies.json" + os.pathsep + "emubench",
                "--add-data", "emubench/desktop.html" + os.pathsep + "emubench",
                "--add-data", "emubench/report.html" + os.pathsep + "emubench",
                "--add-data", "emubench/chart.js" + os.pathsep + "emubench",
                "--add-data", "emubench/compare.js" + os.pathsep + "emubench",
                "--add-binary", str(native) + os.pathsep + "emubench/native/bin", str(entry)], check=True)

Path("dist/scores.html").write_text(template_html(), encoding="utf-8")

notices = Path("dist/third-party")
notices.mkdir(exist_ok=True)
python_licenses = [Path(sys.base_prefix) / "LICENSE.txt", Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"]
shutil.copy2(next(p for p in python_licenses if p.is_file()), notices / "Python-LICENSE.txt")
installer = metadata.distribution("pyinstaller")
license_path = next(p for p in installer.files if p.name == "COPYING.txt")
shutil.copy2(installer.locate_file(license_path), notices / "PyInstaller-COPYING.txt")

# Include upstream notices for the libraries carried in the single-file executable.
for name in ("PyNaCl", "pillow", "psutil", "cffi", "pycparser"):
    dist = metadata.distribution(name)
    for entry in dist.files or ():
        if entry.name.lower().startswith(("license","copying")) and ".dist-info" in str(entry):
            target = notices / name / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dist.locate_file(entry), target)
