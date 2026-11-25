"""Build a native GUI around the same verified CLI distributed at emubench.games."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from emubench import catalog, downloads, engines, games

from distribute import stage_release


def bundle():
    target=catalog.host_target()
    mac=target.startswith("macos")
    assets=ROOT/"emubench"/"assets"
    cache=ROOT/"build"/"desktop"
    cache.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable, str(ROOT/"tools/package_cli.py")], cwd=ROOT, check=True)
    dist=ROOT/"dist"/"gui"
    entry=cache/"entry_gui.py"
    entry.write_text("from emubench.gui import main\nmain()\n",encoding="utf-8")
    icon=assets/("emubench.icns" if mac else "emubench.ico")
    args=[sys.executable,"-m","PyInstaller","--onedir","--windowed","--noconfirm","--clean","--name","EmuBench",
          "--distpath",str(dist),"--workpath",str(cache/"work"),"--specpath",str(cache),"--paths",str(ROOT),
          "--icon",str(icon),"--add-data",str(assets/"emubench.png")+os.pathsep+"emubench/assets"]
    if mac:
        args+=["--osx-bundle-identifier","games.emubench.desktop"]
    subprocess.run(args+[str(entry)],check=True)
    app=dist/("EmuBench.app" if mac else "EmuBench")
    engine_dir=(app/"Contents"/"Resources" if mac else app)/"benchmark"
    engine_dir.mkdir(parents=True,exist_ok=True)
    exe="emubench"+engines.EXE
    stage_release(engine_dir)
    binary=engine_dir/exe
    binary.chmod(0o755)
    downloads.check_arch(binary,target)
    games.verify(engine_dir/"games")
    subprocess.run([binary,"--version"],check=True)
    # GUI packaging adds Tcl/Tk on top of the notices already present for the CLI.
    from PyInstaller.utils.hooks.tcl_tk import tcltk_info
    for label,folder in (("tcl",tcltk_info.tcl_data_dir),("tk",tcltk_info.tk_data_dir)):
        source=Path(folder)
        notice=next((p for d in (source, source.parent, source.parent.parent/"Resources") for f in ("license.terms","license.txt","LICENSE") if (p:=d/f).is_file()),None)
        if notice:
            shutil.copy2(notice,engine_dir/"third-party"/(label+"-license.txt"))
        else:
            shutil.copy2(ROOT/"tools"/"artwork"/(label+"-license.txt"),engine_dir/"third-party"/(label+"-license.txt"))
    target_zip=dist/("EmuBench-Desktop-"+target+".zip")
    if mac:
        subprocess.run(["codesign","--force","--deep","--sign","-",app],check=True)
        subprocess.run(["codesign","--verify","--deep","--strict",app],check=True)
        subprocess.run(["ditto","-c","-k","--sequesterRsrc","--keepParent",app,target_zip],check=True)
    else:
        shutil.make_archive(str(target_zip.with_suffix("")),"zip",dist,app.name)
    print(target_zip)


if __name__=="__main__":
    bundle()
