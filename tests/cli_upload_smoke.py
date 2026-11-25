"""Exercise durable offline uploads with native runs and an actual campaign DB."""
import json
import os
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

        assert "off" in cli("uploads","status")
        cli("uploads","enable")
        cli("run","--rom",rom.name,"--core",core,"--frames","120","--game","Public Game")
        queue = work/"my campaign.sqlite"
        cli("campaign","create",queue,"--rom",rom,"--core",core,"--frames","120","--dedicated")
        cli("campaign","resume",queue)
        cli("campaign","resume",queue)
        assert "2 queued" in cli("uploads","status")
        assert "2 queued" in cli("uploads","sync",expected=1)

        with sqlite3.connect(private_home/"history.sqlite") as db:
            payloads = [json.loads(row[0]) for row in db.execute("SELECT payload FROM score_outbox")]
            assert {r["game"] for r in payloads} == {"Public Game", "Personal ROM"}
            assert all(r["rendered_frames"] == 120 and "frame_ns" not in r for r in payloads)
            assert rom.name not in json.dumps(payloads) and str(work) not in json.dumps(payloads)
            assert db.execute("SELECT count(*) FROM attempts WHERE outcome='completed'").fetchone()[0] == 2
        assert "0 queued" in cli("uploads","disable")
        print("Local paths, public names, offline recovery, resumed campaigns and disable verified.")


if __name__ == "__main__":
    main()
