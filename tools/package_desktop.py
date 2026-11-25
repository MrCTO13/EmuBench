"""Build a native GUI around the same verified CLI distributed at emubench.games."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from emubench import catalog, downloads, engines, games

RELEASE = "v0.8.0-rc.1"
ENGINES = {
    "macos-arm64": "8231574295f6889bbbe9b22d690f8281707bee08a4fb6cea0ccec1cc2196d6ea",
    "macos-x64": "b68d5ed53c2a8cbaaea17eee635ebdc5631d04d2cb8f4291fdd2ec8090104c79",
    "windows-arm64": "eb353a66899a1bcc285a2b23b8d14595783db81597bb02473f8bf9b2c686cf24",
    "windows-x64": "1c3f34847d48fba4eaa2b5f4e72eba754773b6a417e77a06410469f473eb0d01",
}


def bundle():
    target=catalog.host_target()
    mac=target.startswith("macos")
    assets=ROOT/"emubench"/"assets"
    cache=ROOT/"build"/"desktop"
    cache.mkdir(parents=True,exist_ok=True)
    name="emubench-"+target+".zip"
    archive=cache/name
    if not archive.is_file() or engines.digest(archive)!=ENGINES[target]:
        url=f"https://github.com/MrCTO13/EmuBench/releases/download/{RELEASE}/{name}"
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            checked=Path(tmp)/name
            with urlopen(url,timeout=120) as src,checked.open("wb") as dest:
                shutil.copyfileobj(src,dest)
            if engines.digest(checked)!=ENGINES[target]:
                raise ValueError("Unexpected digest for the published measurement engine")
            os.replace(checked,archive)
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
    with ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if member.is_dir():
                continue
            if member.filename==exe or member.filename in ("LICENSE","THIRD-PARTY.md","libretro-header.h") or member.filename.startswith(("games/","third-party/")):
                zipped.extract(member,engine_dir)
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
