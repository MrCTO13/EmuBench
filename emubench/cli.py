import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from . import attest
from . import duckstation, lab, adapters, accuracy, calibration, campaign, carter, chips, circuit, desktop, details, downloads, engines, identify, journal, scores, service, suite, uploads
from .catalog import CATALOG, TARGETS, host_target
from http.client import HTTPException
from zipfile import BadZipFile


def main(argv=None):
    if not (sys.argv[1:] if argv is None else argv):
        return desktop.launch()
    parser = argparse.ArgumentParser(prog="emubench", description="EmuBench")
    parser.add_argument("--version", action="version", version="Emu Bench 0.7.0")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("desktop", help="Open the local desktop launcher")
    commands.add_parser("emulators", help="List supported emulator downloads")
    dl = commands.add_parser("download", help="Fetch and verify the latest upstream packages")
    which = dl.add_mutually_exclusive_group(required=True)
    which.add_argument("emulator", nargs="?", type=downloads.emulator_id, choices=tuple(CATALOG))
    which.add_argument("--all", action="store_true", help="Fetch the complete third-party shortlist")
    dl.add_argument("--channel", choices=["auto", "desktop", "core", "bench"])
    dl.add_argument("--version", default="latest", help="Latest package, or a desktop release tag")
    dl.add_argument("--target", choices=tuple(TARGETS), help="Default to this computer")
    dl.add_argument("--list-only", action="store_true", help="Resolve upstream versions without downloading")
    versions = commands.add_parser("versions", help="List mGBA releases or resolve a peer's latest package")
    install = commands.add_parser("install", help="Download an upstream release and build its core")
    for p in (versions, install):
        p.add_argument("emulator", type=downloads.emulator_id, choices=tuple(CATALOG), nargs="?", default="mgba")
    install.add_argument("--version", default=None, metavar="TAG|latest")
    run = commands.add_parser("run", help="Measure a local GBA or SNES ROM")
    run.add_argument("--rom", type=Path, help="Unpacked .gba, .sfc or .smc file (prompt if omitted)")
    run.add_argument("--game", type=scores.public_title, default="Personal ROM",
                     help="Display title for automatic uploads when enabled")
    run.add_argument("--emulator", choices=tuple(scores.ADAPTERS), default="mgba")
    build = run.add_mutually_exclusive_group()
    build.add_argument("--version", "--emulator-version", metavar="TAG|latest")
    build.add_argument("--latest-core", action="store_true", help="Download the current prebuilt core for this host")
    build.add_argument("--core", type=Path, help="Installed libretro library for the selected emulator")
    run.add_argument("--warmup-frames", type=int, default=120)
    run.add_argument("--frames", type=int, default=1800)
    run.add_argument("--timeout", type=int, default=300, help="Worker timeout in seconds")
    run.add_argument("--out", type=Path, help="Private result JSON destination")
    publish = commands.add_parser("publish", help="Review and publish a public score")
    publish.add_argument("result", type=Path)
    publish.add_argument("--game", default="Personal ROM", help="Optional public display title")
    publish.add_argument("--preview", action="store_true", help="Print the public fields and exit offline")
    publish.add_argument("--destination", choices=("service","github"), default="service")
    publish.add_argument("--yes", action="store_true", help="Approve public submission without a prompt")
    sharing = commands.add_parser("uploads", help="Manage automatic uploads of public score summaries on this device")
    sharing.add_argument("action", choices=["enable", "disable", "status", "sync"],
                         help="Enable uploads of future scores to the selected public scoreboard, disable and discard pending uploads, show status, or retry pending scores")
    sharing.add_argument("--destination", choices=("service","github"), default="service", help="Destination for new enrollment")
    hist = commands.add_parser("history", help="Show this device's private run log")
    hist.add_argument("--game", default="")
    hist.add_argument("--limit", type=int, default=20)
    report = commands.add_parser("details", help="Write an offline interactive FPS chart")
    report.add_argument("result", type=Path)
    report.add_argument("--out", required=True, type=Path)
    compare = commands.add_parser("compare", help="Write an offline comparison of saved local runs")
    compare.add_argument("results", nargs="+", type=Path)
    compare.add_argument("--game", help="Display title for this comparison")
    compare.add_argument("--out", type=Path, required=True)
    suites = commands.add_parser("carter", help="Run deterministic Carter FPS scenes")
    suites.add_argument("--rom", type=Path, help="Pinned original cartridge, or fetch with authenticated gh")
    suites.add_argument("--scene", choices=("all","easy","normal","hard"), default="all")
    suites.add_argument("--out-dir", type=Path, help="Private directory for per-scene trace files")
    official = commands.add_parser("suite", help="Build and run the public Carter Circuit workload")
    for command in (run, official):
        command.add_argument("--paced", action="store_true", help="Also measure scheduled frame deadlines and audio supply")
    official.add_argument("--scene", choices=("all", *circuit.LEVELS), default="all")
    run.add_argument("--checks",action="store_true",help="Attach the matching named accuracy panel for a GBA, SNES or Game Boy Color build")
    official.add_argument("--checks", action="store_true", help="Also run the pinned upstream CPU/memory diagnostics")
    official.add_argument("--out-dir", type=Path)
    official.add_argument("--expect-worker", metavar="SHA256", help="Require the matching timing worker binary")
    official.add_argument("--expect-core", metavar="SHA256", help="Require an exact emulator binary")
    diag = commands.add_parser("accuracy", help="Run the named upstream CPU/memory conformance programs")
    diag.add_argument("--out", type=Path, help="Write the diagnostic results as JSON")
    diag.add_argument("--refresh", action="store_true", help="Re-run even if this build has a cached result")
    chipcmd = commands.add_parser("chips", help="Run original SA-1 and Super FX functional checks")
    for command in (suites, official, diag, chipcmd):
        command.add_argument("--emulator", choices=(*adapters.SUITE_PEERS,"sameboy","gambatte") if command is diag else adapters.SUITE_PEERS, required=True)
        source = command.add_mutually_exclusive_group()
        source.add_argument("--core", type=Path, help="Pinned local core. By default fetch the latest prebuilt core.")
        source.add_argument("--version", metavar="TAG|latest", help="Build a specific mGBA release")
    catalog = commands.add_parser("catalog", help="Install edition metadata or identify a cartridge locally")
    catalog.add_argument("action", choices=("install","match"))
    catalog.add_argument("console", choices=("gba","snes"))
    catalog.add_argument("--rom", type=Path)
    run.add_argument("--share-title", action="store_true", help="Include matched edition and catalog name in public scores")
    pilot = commands.add_parser("calibrate", help="Run or resume a randomized paired duration pilot")
    pilot.add_argument("--emulator", choices=adapters.SUITE_PEERS, required=True)
    pilot.add_argument("--core", type=Path, required=True)
    pilot.add_argument("--rom", type=Path, help="Default to the generated Circuit scene")
    pilot.add_argument("--scene", choices=circuit.LEVELS, default="hard")
    pilot.add_argument("--blocks", type=int, default=8)
    pilot.add_argument("--windows", type=int, nargs="+", default=[600,1800,3600])
    pilot.add_argument("--seed", type=int, default=4171)
    gate=pilot.add_mutually_exclusive_group()
    gate.add_argument("--idle-check", type=Path, help="Require this program to report an idle device throughout each trial")
    gate.add_argument("--dedicated", action="store_true", help="Reserve this host for the physical pilot")
    pilot.add_argument("--out", required=True, type=Path)
    bench=commands.add_parser("bench", help="Download compatible timing cores and benchmark a ROM or directory")
    bench.add_argument("rom", type=Path)
    bench.add_argument("--queue", type=Path, help="Location for the new resumable queue")
    bench.add_argument("--emulator", choices=(*adapters.NAMES,"all","arcade"),default="all")
    bench.add_argument("--core", type=Path)
    bench.add_argument("--carts-core",type=Path,help="Include CartsSNES in an all-emulator queue")
    bench.add_argument("--frames",type=int)
    bench.add_argument("--warmup-frames",type=int)
    bench.add_argument("--system-dir",type=Path,help="Local firmware directory")
    run.add_argument("--system-dir",type=Path,help="Local firmware directory")
    bench.add_argument("--dedicated",action="store_true")
    bench.add_argument("--idle-check",type=Path)
    bench.add_argument("--study",choices=("snes","gba"),help="Find and benchmark the 24 registered game editions")
    bench.add_argument("--share-title",action="store_true")
    from . import standalone
    standalone.arguments(commands)
    duckstation.arguments(commands)
    lab.arguments(commands)
    campaign.arguments(commands)
    args = parser.parse_args(argv)
    try:
        if getattr(args,"system_dir",None):
            import os
            if not args.system_dir.is_dir():
                raise ValueError("--system-dir requires a local directory")
            os.environ["EMUBENCH_SYSTEM_DIR"]=str(args.system_dir.resolve())
        if args.command=="mgba-perf":
            standalone.mgba(args)
            return 0
        if args.command=="duckstation":
            return duckstation.execute(args) or 0
        if args.command=="study":
            return lab.execute(args) or 0
        if args.command == "bench":
            import uuid
            args.queue = args.queue or engines.home()/"campaigns"/(str(uuid.uuid4())+".sqlite")
            args.rom = [args.rom]
            args.rom_dir=args.carter=args.circuit=args.version=args.days=None
            args.loop=args.wait_uploads=False
            args.latest_core=True
            args.timeout=args.idle_seconds=300
            campaign.create(args)
            args.action="resume"
            return campaign.execute(args) or 0
        if args.command == "calibrate":
            calibration.execute(args)
        elif args.command == "catalog":
            if args.action == "install":
                print(f"Installed {identify.install(args.console)} catalog entries")
            else:
                if not args.rom:
                    raise ValueError("Supply --rom PATH")
                scores.validate_file(args.rom, "mgba" if args.console == "gba" else "snes9x")
                match = identify.match(args.console, args.rom.read_bytes())
                print(match["title"] if match else "No match in installed catalog")
        elif args.command == "desktop":
            desktop.launch()
        elif args.command == "emulators":
            for key, item in CATALOG.items():
                providers = (["desktop"] if item.assets else []) + (["core"] if item.core else [])
                routes=", ".join(adapters.CONSOLES.get(item.name,["standalone regression runner"]))
                print(f"{key:<20} {item.name:<19} {', '.join(providers)} · {routes}")
        elif args.command == "uploads":
            if args.action in ("enable", "disable"):
                uploads.configure(args.action == "enable", args.destination)
            if args.action == "sync" and not uploads.flush(force=True):
                uploads.status()
                return 1
            uploads.status()
        elif args.command == "download":
            return downloads.batch(CATALOG if args.all else [args.emulator], args.target or host_target(),
                                   args.channel or ("bench" if args.all else "auto"), args.version, args.list_only)
        elif args.command in ("carter","suite","accuracy","chips"):
            release = None
            if args.command == "suite" and args.emulator == "mgba" and not args.core and not args.version and engines.bundled_reference():
                args.version = engines.REFERENCE
            if args.version:
                if args.emulator != "mgba":
                    raise ValueError("For a specific SNES build, supply its libretro library with --core")
                core, release = engines.install(args.version)
            else:
                core = args.core.expanduser().resolve(strict=True) if args.core else downloads.latest_core(args.emulator)
            console = "gba" if args.emulator == "mgba" else "snes"
            if args.command == "chips":
                record = chips.run(args.emulator, core)
                print(json.dumps(record,indent=2))
                return int(any(v != "pass" for v in record.values()))
            if args.command == "carter":
                rom = carter.cartridge(console, args.rom)
            if args.command == "suite":
                return suite.run(args, core, release)
            record = accuracy.run(args.emulator, core, getattr(args,"refresh",False))
            print(accuracy.summary(record))
            if args.command == "accuracy":
                if args.out:
                    with args.out.open("x",encoding="utf-8") as report_file:
                        json.dump(record,report_file,indent=2)
                return int(any(value != "pass" for value in record["checks"].values()))
            for scene in carter.SCENES:
                if scene.console != console or args.scene not in ("all",scene.level):
                    continue
                with journal.attempt(rom, core.name, scene.title) as (run_id,start):
                    result = scores.measure(rom,None,core,scene.warmup,carter.FRAMES,120,
                                            expected_rom=carter.GAMES[console].digest,emulator=args.emulator,scene=scene)
                    if result["core_sha256"] != record["core_sha256"] or result["worker_sha256"] != record["worker_sha256"]:
                        raise ValueError("Core or worker changed during the suite")
                    if release:
                        if result["version"] != release["tag"] or result["core_sha256"] != release["sha256"]:
                            raise ValueError("Measured core differs from the requested mGBA release")
                        result["source_commit"] = release["commit"]
                    result.update(id=run_id,local_name=scene.title,started_utc=start,finished_utc=journal.now(),accuracy=record)
                    dest = args.out_dir / (scene.profile + "-" + run_id + ".json") if args.out_dir else None
                    attest.complete(result)
                    path = scores.save(result,dest)
                    journal.complete(result,path)
                print(f"{scene.title} · {scene.description}\n"
                      f"{result['speed_x']:.2f}× · {result['average_fps']} avg / {result['low_1pct_fps']} low / {result['high_1pct_fps']} high FPS"
                      f"\nPrivate result: {path}")
                uploads.flush(limit=3)
        elif args.command == "campaign":
            return campaign.execute(args) or 0
        elif args.command == "history":
            journal.history(args.game, args.limit)
        elif args.command == "details":
            trace = json.loads(args.result.read_text(encoding="utf-8"))
            public = scores.public_fields(trace, "Personal ROM")
            print(details.write_report(trace, public, args.out))
        elif args.command == "compare":
            records = {}
            for source in args.results:
                trace = json.loads(source.read_text(encoding="utf-8"))
                entry = scores.public_fields(trace, args.game or "Personal ROM")
                if not entry.get("comparison_id"):
                    raise ValueError("This result predates matched runs. Use details to view it individually.")
                if not args.game and trace["profile"] not in carter.PROFILES:
                    entry["game"] = trace.get("local_name", "Personal ROM")
                records[entry["run_id"]] = entry
            print(details.write_embedded(list(records.values()), args.out))
        elif args.command == "versions":
            if args.emulator == "mgba":
                print("\n".join(engines.releases()))
            else:
                return downloads.batch([args.emulator], host_target(), "auto", "latest", True)
        elif args.command == "install":
            if args.emulator != "mgba":
                return downloads.batch([args.emulator], host_target(), "auto", args.version or "latest", False)
            path, meta = engines.install(args.version or engines.REFERENCE)
            print(f"Installed mGBA {meta['tag']} at {path}")
        elif args.command == "run":
            if not args.rom and not sys.stdin.isatty():
                parser.error("supply --rom when running without a terminal")
            rom = args.rom or Path(input("Path to your ROM: ").strip().strip('"'))
            if args.emulator != "mgba" and args.version:
                raise ValueError("For this emulator choose --latest-core or --core PATH to a pinned build")
            if args.latest_core or (args.emulator != "mgba" and not args.core):
                args.core = downloads.latest_core(args.emulator)
            with journal.attempt(rom, str(args.core.name if args.core else args.version or engines.REFERENCE)) as (run_id, start):
                result = scores.measure(rom.expanduser(), args.version, args.core, args.warmup_frames,
                                        args.frames, args.timeout, emulator=args.emulator)
                if args.checks:
                    if args.emulator not in (*adapters.SUITE_PEERS,"gambatte","sameboy") or result["profile"].split("-")[0] not in ("gba","snes","gbc"):
                        raise ValueError("No named diagnostic panel for this emulator and console")
                    core=args.core or engines.install(args.version or engines.REFERENCE)[0]
                    result["accuracy"]=accuracy.run(args.emulator,core.resolve())
                if args.paced:
                    core = args.core or engines.install(args.version or engines.REFERENCE)[0]
                    result["paced"] = scores.paced_pass(result, core.resolve(), rom.expanduser(), args.timeout)
                result["share_title"] = args.share_title
                result.update(id=run_id, local_name=rom.name, started_utc=start, finished_utc=journal.now())
                attest.complete(result)
                path = scores.save(result, args.out)
                journal.complete(result, path, args.game)
            print(f"{result['emulator']} {result['version']} · {result['rendered_frames']} rendered frames\n"
                  f"Console speed {result['speed_x']:.2f}× ({result['video_mode']['refresh_hz']:.6f} Hz)\n"
                  f"Average FPS   {result['average_fps']:.0f}\n"
                  f"1% low FPS    {result['low_1pct_fps']:.0f}\n"
                  f"1% high FPS   {result['high_1pct_fps']:.0f}\nPrivate result: {path}")
            uploads.flush(limit=3)
        else:
            public = scores.public_fields(json.loads(args.result.read_text(encoding="utf-8")), args.game)
            print(json.dumps(public, indent=2, ensure_ascii=False), flush=True)
            if args.preview:
                return 0
            if not args.yes:
                if not sys.stdin.isatty():
                    parser.error("use --preview to inspect, then --yes to submit from a script")
                if input(f"Publish this score to the {args.destination} scoreboard? [y/N] ").lower() != "y":
                    return 0
            print((service.publish if args.destination == "service" else scores.publish)(public))
        return 0
    except (scores.InterruptedWindow, HTTPException, BadZipFile, sqlite3.Error, OSError, ValueError, KeyError, TypeError, EOFError, subprocess.SubprocessError) as error:
        print(f"Emu Bench: {error}", file=sys.stderr)
        return 1
