"""Produce a downloadable single executable with the native timing worker embedded."""
from pathlib import Path
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from emubench.engines import worker

native = worker()
entry = Path("build/entry.py")
entry.parent.mkdir(exist_ok=True)
entry.write_text("from emubench.cli import main\nraise SystemExit(main())\n", encoding="utf-8")
subprocess.run([sys.executable, "-m", "PyInstaller", "--onefile", "--clean", "--noconfirm",
                "--paths", ".", "--name", "emubench", "--add-binary",
                str(native) + os.pathsep + "emubench/native/bin", str(entry)], check=True)
