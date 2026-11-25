import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from . import accuracy, campaign, carter, details, downloads, engines, journal, scores, uploads
from .catalog import CATALOG, TARGETS, host_target
from http.client import HTTPException
from zipfile import BadZipFile


def main(argv=None):
    parser = argparse.ArgumentParser(prog="emubench", description="Emu Bench presented by Carts")
    parser.add_argument("--version", action="version", version="Emu Bench 0.5.0")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("emulators", help="List supported emulator downloads")
    dl = commands.add_parser("download", help="Fetch and verify the latest upstream packages")
    which = dl.add_mutually_exclusive_group(required=True)
    which.add_argument("emulator", nargs="?", type=downloads.emulator_id, choices=tuple(CATALOG))
    which.add_argument("--all", action="store_true", help="Fetch the complete third-party shortlist")
    dl.add_argument("--channel", choices=["auto", "desktop", "core"], default="auto")
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
    publish = commands.add_parser("publish", help="Review and publish a score on GitHub")
    publish.add_argument("result", type=Path)
    publish.add_argument("--game", default="Personal ROM", help="Optional public display title")
    publish.add_argument("--preview", action="store_true", help="Print the public fields and exit offline")
    publish.add_argument("--yes", action="store_true", help="Approve public submission without a prompt")
    sharing = commands.add_parser("uploads", help="Manage automatic uploads of public score summaries on this device")
    sharing.add_argument("action", choices=["enable", "disable", "status", "sync"],
                         help="Enable uploads of future scores to the public GitHub scoreboard, disable and discard pending uploads, show status, or retry pending scores")
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
    diag = commands.add_parser("accuracy", help="Run the named upstream CPU/memory conformance programs")
    diag.add_argument("--out", type=Path, help="Write the diagnostic results as JSON")
    diag.add_argument("--refresh", action="store_true", help="Re-run even if this build has a cached result")
    for command in (suites, diag):
        command.add_argument("--emulator", choices=tuple(scores.ADAPTERS), required=True)
        source = command.add_mutually_exclusive_group()
        source.add_argument("--core", type=Path, help="Pinned local core. By default fetch the latest prebuilt core.")
        source.add_argument("--version", metavar="TAG|latest", help="Build a specific mGBA release")
    campaign.arguments(commands)
    args = parser.parse_args(argv)
    try:
        if args.command == "emulators":
            for key, item in CATALOG.items():
                providers = (["desktop"] if item.assets else []) + (["core"] if item.core else [])
                print(f"{key:<20} {item.name:<19} {', '.join(providers)}")
        elif args.command == "uploads":
            if args.action in ("enable", "disable"):
                uploads.configure(args.action == "enable")
            if args.action == "sync" and not uploads.flush(force=True):
                uploads.status()
                return 1
            uploads.status()
        elif args.command == "download":
            return downloads.batch(CATALOG if args.all else [args.emulator], args.target or host_target(),
                                   args.channel, args.version, args.list_only)
        elif args.command in ("carter","accuracy"):
            release = None
            if args.version:
                if args.emulator != "mgba":
                    raise ValueError("For a specific SNES build, supply its libretro library with --core")
                core, release = engines.install(args.version)
            else:
                core = args.core.expanduser().resolve(strict=True) if args.core else downloads.latest_core(args.emulator)
            console = "gba" if args.emulator == "mgba" else "snes"
            if args.command == "carter":
                rom = carter.cartridge(console, args.rom)
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
                    path = scores.save(result,dest)
                    journal.complete(result,path)
                print(f"{scene.title} · {scene.description}\n"
                      f"{result['average_fps']} avg / {result['low_1pct_fps']} low / {result['high_1pct_fps']} high FPS"
                      f"\nPrivate result: {path}")
                uploads.flush(limit=3)
        elif args.command == "campaign":
            campaign.execute(args)
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
                result.update(id=run_id, local_name=rom.name, started_utc=start, finished_utc=journal.now())
                path = scores.save(result, args.out)
                journal.complete(result, path, args.game)
            print(f"{result['emulator']} {result['version']} · {result['rendered_frames']} rendered frames\n"
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
                if input(f"Publish to {scores.REPOSITORY} as a public issue under your GitHub account? [y/N] ").lower() != "y":
                    return 0
            print(scores.publish(public))
        return 0
    except (scores.InterruptedWindow, HTTPException, BadZipFile, sqlite3.Error, OSError, ValueError, KeyError, TypeError, EOFError, subprocess.SubprocessError) as error:
        print(f"Emu Bench: {error}", file=sys.stderr)
        return 1
