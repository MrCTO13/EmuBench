"""Build SameBoy on Linux ARM where the Buildbot index lacks a native binary."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
from zipfile import ZipFile
from . import downloads, engines

def install(version="latest"):
    spec=downloads.resolve("sameboy","windows-x64","desktop",version)
    repo="https://github.com/LIJI32/SameBoy.git"
    ref="refs/tags/"+spec.version
    refs=subprocess.check_output(["git","ls-remote",repo,ref,ref+"^{}"],text=True,timeout=60)
    tags={name:commit for commit,name in (row.split() for row in refs.splitlines())}
    commit=tags.get(ref+"^{}",tags.get(ref,""))
    if not engines.SHA.fullmatch(commit):
        raise ValueError("Could not identify the upstream SameBoy release")
    parent=engines.home()/"engines"/"linux-arm64"/"sameboy"
    dest=parent/commit
    name="sameboy_libretro.so"
    if not dest.is_dir():
        parent.mkdir(parents=True,exist_ok=True)
        archive,_=downloads.obtain(spec)
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            temp=Path(folder)
            src=temp/"src"
            engines.call(["git","clone","--depth","1","--branch",spec.version,repo,src])
            if subprocess.check_output(["git","-C",src,"rev-parse","HEAD"],text=True).strip()!=commit:
                raise ValueError("SameBoy release tag changed during installation")
            boot=temp/"boot"
            boot.mkdir()
            # The official SDL release contains the project's cross-platform replacement boot programs.
            with ZipFile(archive) as z:
                for stem in ("dmg","mgb","sgb","sgb2","cgb","cgb0","agb"):
                    filename=stem+"_boot.bin"
                    item=z.getinfo(filename)
                    if not 128<=item.file_size<=16384:
                        raise ValueError("Invalid upstream boot program")
                    (boot/filename).write_bytes(z.read(item))
            engines.call(["make","-C",src/"libretro","-j2","platform=unix","BOOTROMS_DIR="+str(boot)])
            stage=temp/"ready"
            stage.mkdir()
            shutil.copy2(engines.artifact(src,name),stage/name)
            downloads.check_arch(stage/name,"linux-arm64")
            (stage/"build.json").write_text(json.dumps({"tag":spec.version,"commit":commit,"sha256":engines.digest(stage/name)}))
            engines.promote(stage,dest)
    meta=json.loads((dest/"build.json").read_text())
    if meta["commit"]!=commit or engines.digest(dest/name)!=meta["sha256"]:
        raise ValueError("Cached SameBoy build failed verification")
    return dest/name
