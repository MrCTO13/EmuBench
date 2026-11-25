"""Prepare a public receipt for maintainer review from a controlled local campaign."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import uuid
from . import adapters, identify, library, scores

def studies():
    return json.loads(Path(__file__).with_name("studies.json").read_text(encoding="utf-8"))

def select_jobs(console, workloads):
    import hashlib
    study=next(s for s in studies() if s["console"]==console)
    titles={g["edition"]:g["title"] for group in study["groups"] for g in group["games"]}
    identify.install(console)
    selected=[]
    found=set()
    editions={}
    for job in workloads:
        peer=job["emulator"]
        path=Path(job["path"])
        suffix=Path(job.get("member",path)).suffix.lower()
        if adapters.content_console(suffix,peer)!=console:
            continue
        key=job["sha256"]
        if key not in editions:
            data=library.read_pinned_member(path,job["member"],peer) if "member" in job else path.read_bytes()
            editions[key]=(identify.match(console,data) or {}).get("edition")
        edition=editions[key]
        if edition in titles and (edition,peer) not in found:
            found.add((edition,peer))
            selected.append((edition,job))
    missing=set(titles)-{edition for edition,_ in selected}
    if missing:
        raise ValueError("Study is missing these editions: "+", ".join(titles[k] for k in sorted(missing)))
    # Interleave builds and titles using an order fixed before observing any results.
    selected.sort(key=lambda pair:hashlib.sha256((study["id"]+"/"+pair[0]+"/"+pair[1]["emulator"]).encode()).digest())
    return [job for _,job in selected]


def arguments(commands):
    p=commands.add_parser("study",help="List the frozen sample or prepare a controlled campaign for review")
    p.add_argument("action",choices=("list","review"))
    p.add_argument("--console",choices=("gba","snes"),required=True)
    p.add_argument("--queue",type=Path)
    p.add_argument("--out",type=Path)

def review(study, plan, jobs):
    if plan.get("study")!=study["id"]:
        raise ValueError("The queue was not registered for this study before measurement")
    if not (plan.get("dedicated") or plan.get("idle_check") or plan.get("idle_seconds")):
        raise ValueError("Missing campaign timing gate")
    games={g["edition"] for group in study["groups"] for g in group["games"]}
    eligible={adapters.NAMES[k]:v["sha256"] for k,v in plan["cores"].items()
              if study["console"] in adapters.CONSOLES[adapters.NAMES[k]] and "sha256" in v}
    if len(eligible)<2 or any("error" in v for v in plan["cores"].values()):
        raise ValueError("Review requires two compatible pinned builds and successful installations")
    pairs={}
    cohort=None
    for status,attempts,raw in jobs:
        if status!="done" or not raw or attempts:
            raise ValueError("First round has missing, failed or retried measurements")
        result=json.loads(raw)
        if result["profile"]!=adapters.profile(study["console"]):
            continue
        game=result.get("catalog_match",{}).get("edition")
        if game not in games:
            continue
        if result.get("idle",{}).get("state")=="busy":
            raise ValueError("Busy host in lab campaign")
        public=scores.public_fields(result,"Personal ROM")
        peer=public["emulator"]
        if (eligible.get(peer)!=public["core_sha256"] or public.get("campaign_id")!=plan["campaign_id"] or
            (public["warmup_frames"],public["rendered_frames"])!=(study["warmup"],study["frames"])):
            raise ValueError("Build, campaign or measurement window mismatch")
        host=tuple(public[k] for k in ("device_id","os","arch","cpu","worker_sha256"))
        if cohort is not None and cohort!=host:
            raise ValueError("All runs must share one host and timing worker")
        cohort=host
        if (game,peer) in pairs:
            raise ValueError("Duplicate measurement for the same build and edition")
        pairs[game,peer]={k:public[k] for k in ("run_id","version","average_fps","low_1pct_fps","high_1pct_fps","speed_x") if k in public}
    missing=len(games)*len(eligible)-len(pairs)
    if missing:
        raise ValueError(f"Withheld aggregate: {missing} required game/build measurements missing")
    rows=[dict(edition=game,emulator=peer,**v) for (game,peer),v in sorted(pairs.items())]
    return {"study":study["id"],"campaign":str(uuid.UUID(plan["campaign_id"])),
            "host":dict(zip(("device","os","arch","cpu","worker_sha256"),cohort)),
            "gate":"dedicated" if plan["dedicated"] else "idle monitoring","builds":eligible,"rows":rows}

def execute(args):
    study=next(s for s in studies() if s["console"]==args.console)
    if args.action=="list":
        print(json.dumps(study,ensure_ascii=False,indent=2))
        return
    if not args.queue or not args.out:
        raise ValueError("Review requires a campaign --queue and a new --out receipt")
    with closing(sqlite3.connect(args.queue.resolve(strict=True).as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("BEGIN")
        plan=json.loads(db.execute("SELECT plan FROM campaign").fetchone()[0])
        if db.execute("SELECT 1 FROM failures JOIN jobs ON jobs.id=failures.job WHERE jobs.round=1 LIMIT 1").fetchone():
            raise ValueError("The first round contains a failed attempt; the aggregate is withheld")
        receipt=review(study,plan,db.execute("SELECT status,attempts,result FROM jobs WHERE round=1 ORDER BY id"))
    validate_receipt([study],receipt)
    with args.out.open("x",encoding="utf-8") as f:
        json.dump(receipt,f,indent=2,ensure_ascii=False)
    print("Review candidate saved for maintainer review in the project repository.")

def validate_receipt(study_list,receipt):
    """Only reviewed, public display fields can be compiled into the site."""
    import re
    study=next((s for s in study_list if s["id"]==receipt.get("study")),None)
    if not study or set(receipt)!={"study","campaign","host","gate","builds","rows"}:
        raise ValueError("Invalid study receipt")
    uuid.UUID(receipt["campaign"])
    host=receipt["host"]
    if set(host)!={"device","os","arch","cpu","worker_sha256"} or receipt["gate"] not in ("dedicated","idle monitoring"):
        raise ValueError("Invalid controlled cohort")
    uuid.UUID(host["device"])
    if host["os"] not in ("Darwin","Windows","Linux") or not re.fullmatch(r"[\w ().@+®,™-]{1,160}",host["cpu"]) or not re.fullmatch(r"(arm64|amd64|aarch64|x86_64)",host["arch"],re.I):
        raise ValueError("Unrecognized lab host")
    builds=receipt["builds"]
    if len(builds)<2 or any(study["console"] not in adapters.CONSOLES.get(k,()) for k in builds):
        raise ValueError("Incompatible study builds")
    if not all(re.fullmatch(r"[0-9a-f]{64}",h) for h in [*builds.values(),host["worker_sha256"]]):
        raise ValueError("Missing build fingerprint")
    expected={(g["edition"],p) for group in study["groups"] for g in group["games"] for p in builds}
    seen=set()
    for row in receipt["rows"]:
        if ("speed_x" in row and not (isinstance(row["speed_x"],(int,float)) and 0<row["speed_x"]<1e6)) or set(row)-{"speed_x"}!={"edition","emulator","run_id","version","average_fps","low_1pct_fps","high_1pct_fps"}:
            raise ValueError("Unexpected public game fields")
        pair=(row["edition"],row["emulator"])
        if pair not in expected or row["run_id"] in seen or not re.fullmatch(r"[a-zA-Z0-9 ()._+-]{1,80}",row["version"]):
            raise ValueError("Duplicate or mismatched measurement")
        uuid.UUID(row["run_id"])
        expected.remove(pair)
        seen.add(row["run_id"])
        if not all(type(row[k]) is int and 0<row[k]<=10**8 for k in ("average_fps","low_1pct_fps","high_1pct_fps")) or row["low_1pct_fps"]>row["high_1pct_fps"]:
            raise ValueError("Invalid study FPS")
    if expected:
        raise ValueError("Incomplete game/build matrix")
