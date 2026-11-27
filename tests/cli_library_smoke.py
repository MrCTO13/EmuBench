"""Run a mixed library with all compatible cores and inspect the offline upload queue."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from zipfile import ZipFile

import snes_workload
import workload


def main():
    executable = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="EmuBench mixed library ") as folder:
        work = Path(folder)
        library = work / "games"
        nested = library / "collections" / "SNES"
        nested.mkdir(parents=True)
        gba = library/"Private GBA.GBA"
        workload.write(gba)
        snes = work/"Private SNES.smc"
        snes_workload.write(snes)
        with ZipFile(nested/"Private pack.zip","w") as pack:
            pack.write(snes,"titles/Private SNES.smc")
            pack.write(gba,"duplicate.gba")
        (nested/"Ignored.nes").write_bytes(b"test")
        home = work/"device"
        env = {**os.environ,"EMUBENCH_HOME":str(home),"GH_CONFIG_DIR":str(work/"no-login"),
               "GH_TOKEN":"","GITHUB_TOKEN":""}
        def cli(*args, offline=False):
            run_env = {**env, "PATH":str(work/"empty")} if offline else env
            proc = subprocess.run([executable,*args], env=run_env, cwd=work, capture_output=True, timeout=180)
            assert proc.returncode==0, (proc.stdout,proc.stderr)
            return proc.stdout.decode(errors="replace")

        queue = work/"folder.sqlite"
        created = cli("campaign","create",queue,"--rom-dir",library,"--frames","120","--dedicated")
        assert "4 jobs" in created and "1 duplicate" in created, created
        cli("uploads","enable","--destination","github",offline=True)
        cli("campaign","resume",queue,offline=True)
        cli("campaign","resume",queue,offline=True)
        assert "done: 4" in cli("campaign","status",queue,offline=True)
        with closing(sqlite3.connect(home/"history.sqlite")) as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT payload FROM score_outbox")]
        with closing(sqlite3.connect(queue)) as db:
            results = [json.loads(row[0]) for row in db.execute("SELECT result FROM jobs")]
        assert {r["run_id"] for r in records}=={r["id"] for r in results if r["repeatability"]["accepted"]}
        assert {r["emulator"] for r in results}=={"mGBA","gpSP","Snes9x","bsnes"}
        assert all(r["rendered_frames"]==120*r["window"]["loops"] and r["game"]=="Personal ROM" for r in records)
        assert "Private " not in json.dumps(records) and str(work) not in json.dumps(records)
        with closing(sqlite3.connect(queue)) as db:
            results = [json.loads(row[0]) for row in db.execute("SELECT result FROM jobs")]
        assert all(r["sampled_frame_changes"]>0 for r in results)
        assert {r["local_name"] for r in results}=={"Private GBA.GBA","Private SNES.smc"}
        print("Four native measurements from a nested mixed library, eligible upload summaries and restart verified.")


if __name__ == "__main__":
    main()
