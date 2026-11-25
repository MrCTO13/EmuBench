"""Paired, randomized duration pilot for a single fixed cartridge and core."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import time
from statistics import median
import tempfile
import os

from . import campaign, circuit, engines, scores


def metrics(times):
    ordered=sorted(times)
    return (1e9*len(times)/sum(times), 1e9/ordered[(99*len(times)+99)//100-1],
            1e9/ordered[(len(times)+99)//100-1])


def confidence(ratios, seed):
    rng=random.Random(seed)
    samples=sorted(median(rng.choices(ratios,k=len(ratios))) for _ in range(2000))
    return [samples[49],samples[1949]]


def assess(rows, candidates, repeats):
    result=[]
    for window in candidates:
        pairs=[]
        for idx in range(repeats):
            sample={r["frames"]:r["metrics"] for r in rows if r["block"]==idx}
            if window in sample and 10800 in sample:
                anchor=sample[10800]
                pairs.append([value/base for value,base in zip(sample[window],anchor)])
        passed=len(pairs)==repeats and repeats>=5
        intervals=[]
        if pairs:
            for k,tolerance in enumerate((.01,.05,.05)):
                interval=confidence([p[k] for p in pairs],4171+k)
                intervals.append(interval)
                passed=passed and interval[0]>=1-tolerance and interval[1]<=1+tolerance
        result.append(dict(frames=window,blocks=len(pairs),ratio_intervals=intervals,within_tolerance=passed))
    return result


def execute(args):
    ready=campaign.idle_gate({"dedicated":args.dedicated,"idle_seconds":300,
                              "idle_check":str(args.idle_check.resolve(strict=True)) if args.idle_check else None})
    candidates=sorted(set(args.windows))
    if not candidates or not all(100<=n<10800 for n in candidates) or not 5<=args.blocks<=100:
        raise ValueError("Use 100–10,799 candidate frames and 5–100 independent blocks")
    console="gba" if args.emulator=="mgba" else "snes"
    rom=args.rom or circuit.cartridge(console,args.scene)
    scores.validate_file(rom,args.emulator)
    core=args.core.resolve(strict=True)
    worker=engines.worker()
    data=rom.read_bytes()
    scores.library.check_header(data,args.emulator)
    settings=dict(version=1,rom=hashlib.sha256(data).hexdigest(),core=engines.digest(core),worker=engines.digest(worker),
                  emulator=args.emulator,windows=candidates,blocks=args.blocks,warmup=120,seed=args.seed,
                  device=scores.journal.comparison_id("installation"),anchor_frames=10800)
    if console=="snes" and len(data)%32768==512:
        data=data[512:]
    out=args.out.expanduser().resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        report=json.loads(out.read_text())
        if report["settings"]!=settings:
            raise ValueError("Choose a new output path for a different calibration")
    else:
        report={"settings":settings,"trials":[]}
    rows=report["trials"]
    done={(r["block"],r["frames"]) for r in rows}
    rng=random.Random(args.seed)
    for block in range(args.blocks):
        order=candidates+[10800]
        rng.shuffle(order)
        for frames in order:
            if (block,frames) in done:
                continue
            if engines.digest(core)!=settings["core"]:
                raise ValueError("Core changed during calibration")
            while True:
                if ready():
                    try:
                        output,_=scores.run_worker(worker,core,data,120,frames,600,ready,scores.ADAPTERS[args.emulator][0])
                        break
                    except scores.InterruptedWindow:
                        pass
                print("Waiting for an uninterrupted idle window",flush=True)
                time.sleep(15)
            times=list(map(int,output[5:]))
            if len(times)!=frames:
                raise ValueError("Incomplete calibration evidence")
            rows.append(dict(block=block,frames=frames,metrics=metrics(times),
                             finished_utc=datetime.now(timezone.utc).isoformat()))
            report["summary"]=assess(rows,candidates,args.blocks)
            # Shorter windows must also pass at each longer candidate.
            eligible=[i["frames"] for idx,i in enumerate(report["summary"]) if all(j["within_tolerance"] for j in report["summary"][idx:])]
            report["shortest_supported_frames"]=min(eligible,default=None)
            with tempfile.NamedTemporaryFile(dir=out.parent,delete=False,mode="w",encoding="utf-8") as staged:
                json.dump(report,staged)
            os.replace(staged.name,out)
            print(f"Block {block+1}/{args.blocks}, {frames} frames saved",flush=True)
    print("Shortest supported on this workload and device:",report["shortest_supported_frames"] or "inconclusive")
