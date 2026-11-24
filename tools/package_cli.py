"""Produce a downloadable single executable with the native timing worker embedded."""
from pathlib import Path
import os
import shutil
import sysconfig
from importlib import metadata
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emubench.engines import worker
from emubench.details import template_html

native = worker()
entry = Path("build/entry.py")
entry.parent.mkdir(exist_ok=True)
entry.write_text("from emubench.cli import main\nraise SystemExit(main())\n", encoding="utf-8")
subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
                "--paths", ".", "--name", "emubench",
                "--add-data", "emubench/report.html" + os.pathsep + "emubench",
                "--add-data", "emubench/chart.js" + os.pathsep + "emubench",
                "--add-binary", str(native) + os.pathsep + "emubench/native/bin", str(entry)], check=True)

Path("dist/scores.html").write_text(template_html(), encoding="utf-8")

notices = Path("dist/third-party")
notices.mkdir(exist_ok=True)
python_licenses = [Path(sys.base_prefix) / "LICENSE.txt", Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"]
shutil.copy2(next(p for p in python_licenses if p.is_file()), notices / "Python-LICENSE.txt")
installer = metadata.distribution("pyinstaller")
license_path = next(p for p in installer.files if p.name == "COPYING.txt")
shutil.copy2(installer.locate_file(license_path), notices / "PyInstaller-COPYING.txt")
