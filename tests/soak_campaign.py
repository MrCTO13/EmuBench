"""Run 1,001 distinct generated cartridges, crash/restart and retry a lost upload receipt."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from emubench import circuit, cli, engines, uploads


def child(queue, receipts):
    def publish(payload):
        with closing(sqlite3.connect(receipts)) as db,db:
            db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?)",(payload["run_id"],json.dumps(payload)))
            lose=db.execute("UPDATE faults SET n=n+1 WHERE n=0").rowcount
        if lose:
            raise ConnectionError("simulated connection loss after a successful POST")
        return "offline-test/"+payload["run_id"]
    uploads.service.publish=publish
    if cli.main(["campaign","resume",queue]):
        raise RuntimeError("Unexpected campaign failure")
    assert uploads.flush(force=True)


def main():
    core=engines.install(engines.REFERENCE)[0]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        os.environ["EMUBENCH_HOME"]=str(root/"data")
        directory=root/"games"
        directory.mkdir()
        data=circuit.gba_image(0)
        for idx in range(1001):
            (directory/f"{idx}.gba").write_bytes(data+idx.to_bytes(4,"little"))
        queue,receipts=root/"queue.sqlite",root/"server.sqlite"
        with closing(sqlite3.connect(receipts)) as db,db:
            db.execute("CREATE TABLE receipts(id TEXT PRIMARY KEY,payload TEXT)")
            db.execute("CREATE TABLE faults(n INTEGER)")
            db.execute("INSERT INTO faults VALUES(0)")
        assert cli.main(["campaign","create",str(queue),"--rom-dir",str(directory),"--emulator","mgba","--core",str(core),
                         "--dedicated","--frames","100","--warmup-frames","0"])==0
        uploads.configure(True,"service")
        run=[sys.executable,__file__,"child",str(queue),str(receipts)]
        with subprocess.Popen(run,stdout=subprocess.DEVNULL) as first:
            deadline=time.monotonic()+180
            try:
                while time.monotonic()<deadline:
                    with closing(sqlite3.connect(queue)) as db:
                        if db.execute("SELECT COUNT(*) FROM jobs WHERE status='done'").fetchone()[0]>=11:
                            break
                    if first.poll() is not None:
                        raise RuntimeError("Campaign exited before interruption")
                    time.sleep(.1)
                else:raise TimeoutError("No campaign progress")
            finally:
                first.kill()
        subprocess.run(run,stdout=subprocess.DEVNULL,check=True,timeout=900)
        subprocess.run(run,stdout=subprocess.DEVNULL,check=True,timeout=30)
        with closing(sqlite3.connect(queue)) as db:
            assert db.execute("SELECT status,count(*) FROM jobs GROUP BY status").fetchall()==[("done",1001)]
        with closing(sqlite3.connect(receipts)) as db:
            rows=[json.loads(row[0]) for row in db.execute("SELECT payload FROM receipts")]
            assert len(rows)==1001 and len({r["campaign_id"] for r in rows})==1
            assert all(r["game"]=="Personal ROM" and "rom_sha256" not in r for r in rows)
        print("Verified 1,001 completed workloads and 1,001 unique offline receipts after restart.")


if __name__=="__main__":
    if len(sys.argv)>1:child(*sys.argv[2:])
    else:main()
