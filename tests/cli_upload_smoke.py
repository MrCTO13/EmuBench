"""Exercise durable offline uploads with native runs and an actual campaign DB."""
import json
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from workload import write


def main():
    executable, core = (Path(value).resolve(strict=True) for value in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="EmuBench local ROMs ") as temporary:
        work = Path(temporary)
        private_home = work / "device"
        isolated_path = work / "empty-path"
        isolated_path.mkdir()
        env = {**os.environ, "PATH": str(isolated_path), "EMUBENCH_HOME": str(private_home),
               "GH_CONFIG_DIR": str(work / "no-gh-login"), "GH_TOKEN":"", "GITHUB_TOKEN":""}
        rom = work / "A Private File.gba"
        write(rom)

        def cli(*args, expected=0):
            completed = subprocess.run([executable, *args], env=env, cwd=work, text=True,
                                       capture_output=True, timeout=150)
            assert completed.returncode == expected, (completed.stdout, completed.stderr)
            return completed.stdout

        # A local core with the packaged worker can create a queue before the device
        # data directory exists. Verify the first resume, including a pre-folder plan.
        legacy = work/"legacy.sqlite"
        cli("campaign","create",legacy,"--rom",rom,"--core",core,"--frames","1800","--dedicated")
        with closing(sqlite3.connect(legacy)) as db, db:
            plan = json.loads(db.execute("SELECT plan FROM campaign").fetchone()[0])
            build = plan.pop("cores")["mgba"]
            jobs = plan.pop("workloads")
            plan.update(roms=[[job["path"],job["sha256"]] for job in jobs], core=build["path"],
                        core_hash=build["sha256"], commit=build["commit"], version=build["tag"], emulator="mgba")
            db.execute("UPDATE campaign SET plan=?", (json.dumps(plan),))
        cli("campaign","resume",legacy)
        assert "done: 1" in cli("campaign","status",legacy)
        assert "off" in cli("uploads","status")
        cli("uploads","enable","--destination","github")
        cli("run","--rom",rom.name,"--core",core,"--frames","1800","--game","Public Game")
        queue = work/"my campaign.sqlite"
        cli("campaign","create",queue,"--rom",rom,"--core",core,"--frames","1800","--dedicated")
        cli("campaign","resume",queue)
        cli("campaign","resume",queue)
        # Shared CI machines may legitimately reject a three-pass score. Check
        # that the outbox exactly matches the accepted runs, preserving all attempts.
        def accepted():
            with closing(sqlite3.connect(private_home/"history.sqlite")) as db:
                local=db.execute("SELECT id,result FROM attempts WHERE outcome='completed' AND context='single run'").fetchall()
            records=[json.loads(Path(path).read_text()) for _,path in local]
            with closing(sqlite3.connect(queue)) as campaign:
                records.extend(json.loads(row[0]) for row in campaign.execute("SELECT result FROM jobs"))
            return {r["id"] for r in records if r["repeatability"]["accepted"]}
        for window in (7200, 18000, 36000):
            if accepted():
                break
            cli("run","--rom",rom.name,"--core",core,"--frames",str(window),"--game","Public Game")
        eligible=accepted()
        assert eligible, "Host never produced a repeatable upload fixture"
        assert f"{len(eligible)} queued" in cli("uploads","status")
        assert f"{len(eligible)} queued" in cli("uploads","sync",expected=1)
        with closing(sqlite3.connect(private_home/"history.sqlite")) as db:
            payloads = [json.loads(row[0]) for row in db.execute("SELECT payload FROM score_outbox")]
            assert {r["run_id"] for r in payloads}==eligible
            assert all(r["game"] in ("Public Game", "Personal ROM") for r in payloads)
            assert all(r["rendered_frames"] in (1800,7200,18000,36000) and "frame_ns" not in r for r in payloads)
            assert rom.name not in json.dumps(payloads) and str(work) not in json.dumps(payloads)
            assert db.execute("SELECT count(*) FROM attempts WHERE outcome='completed'").fetchone()[0]>=3
        assert "0 queued" in cli("uploads","disable")
        print("Local paths, public names, offline recovery, resumed campaigns and disable verified.")


if __name__ == "__main__":
    main()
