"""Score all requested public scenes, preserving individual failures and cohort identity."""
import json
import platform
import sys
import uuid

from . import accuracy, chips, circuit, engines, journal, scores, uploads


def run(args, core, release):
    digest=engines.digest(core)
    if args.expect_core and digest!=args.expect_core:
        raise ValueError("Selected core differs from the requested binary digest")
    console="gba" if args.emulator=="mgba" else "snes"
    extra={"chips":chips.run(args.emulator,core)} if console=="snes" else {}
    if args.checks:
        extra["accuracy"]=accuracy.run(args.emulator,core)
    group=str(uuid.uuid4())
    worker=engines.digest(engines.worker())
    if args.expect_worker and args.expect_worker!=worker:
        raise ValueError("Timing worker differs from requested binary digest")
    failed=False
    for scene in circuit.SCENES:
        if scene.console!=console or args.scene not in ("all",scene.level):
            continue
        rom=circuit.cartridge(console,scene.level)
        try:
            with journal.attempt(rom,core.name,scene.title) as (run_id,start):
                result=scores.measure(rom,None,core,scene.warmup,circuit.FRAMES,120,
                                      expected_rom=scene.digest,emulator=args.emulator,scene=scene)
                if result["core_sha256"]!=digest or result["worker_sha256"]!=worker:
                    raise ValueError("Core or worker changed during suite")
                if release:
                    if result["core_sha256"]!=release["sha256"] or result["version"]!=release["tag"]:
                        raise ValueError("Measured core differs from the requested release")
                    result["source_commit"]=release["commit"]
                result.update(extra)
                if args.paced:
                    result["paced"]=scores.paced_pass(result,core,rom,120)
                result.update(id=run_id,started_utc=start,finished_utc=journal.now(),local_name=scene.title,campaign_id=group)
                dest=args.out_dir/(scene.profile+"-"+run_id+".json") if args.out_dir else None
                path=scores.save(result,dest)
                journal.complete(result,path)
            print(f"{scene.title} · {result['average_fps']} avg / {result['low_1pct_fps']} low / "
                  f"{result['high_1pct_fps']} high FPS\nPrivate result: {path}")
        except scores.InterruptedWindow:
            raise
        except (TimeoutError,ValueError) as exc:
            failed=True
            reason="timeout" if isinstance(exc,TimeoutError) else "checkpoint" if "checkpoint" in str(exc) else "measurement"
            record=dict(run_id=run_id,campaign_id=group,device_id=journal.comparison_id("installation"),outcome="failed",
                        reason=reason,game=scene.title,profile=scene.profile,emulator=scores.ADAPTERS[args.emulator][0],
                        core_sha256=digest,worker_sha256=worker,os=platform.system(),arch=platform.machine(),cpu=scores.cpu_model())
            with journal.database() as db:
                if uploads.destination_for(db)=="service" and db.execute("SELECT 1 FROM upload_settings WHERE enabled=1").fetchone():
                    db.execute("INSERT OR IGNORE INTO score_outbox VALUES(?,?)",(run_id,json.dumps(record)))
            print(f"{scene.title} failed ({reason}): {exc}",file=sys.stderr)
        uploads.flush(limit=3)
    if uploads.enabled():
        with journal.database() as db:
            if uploads.destination_for(db)=="service":
                print("Campaign:",uploads.service.ORIGIN+"/campaign/"+group)
    return int(failed)
