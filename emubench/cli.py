import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from . import campaign, details, engines, journal, scores


def main(argv=None):
    parser = argparse.ArgumentParser(prog="emubench", description="Emu Bench presented by Carts")
    parser.add_argument("--version", action="version", version="Emu Bench 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    versions = commands.add_parser("versions", help="List stable mGBA releases")
    install = commands.add_parser("install", help="Download an upstream release and build its core")
    for p in (versions, install):
        p.add_argument("emulator", choices=["mgba"], nargs="?", default="mgba")
    install.add_argument("--version", default=engines.REFERENCE, metavar="TAG|latest")
    run = commands.add_parser("run", help="Measure a local GBA ROM")
    run.add_argument("--rom", type=Path, help="Unpacked .gba file (prompt if omitted)")
    run.add_argument("--emulator", choices=["mgba"], default="mgba")
    build = run.add_mutually_exclusive_group()
    build.add_argument("--version", "--emulator-version", metavar="TAG|latest")
    build.add_argument("--core", type=Path, help="Installed mGBA libretro library")
    run.add_argument("--warmup-frames", type=int, default=120)
    run.add_argument("--frames", type=int, default=1800)
    run.add_argument("--timeout", type=int, default=300, help="Worker timeout in seconds")
    run.add_argument("--out", type=Path, help="Private result JSON destination")
    publish = commands.add_parser("publish", help="Review and publish a score on GitHub")
    publish.add_argument("result", type=Path)
    publish.add_argument("--game", default="Personal GBA ROM", help="Optional public display title")
    publish.add_argument("--preview", action="store_true", help="Print the public fields and exit offline")
    publish.add_argument("--yes", action="store_true", help="Approve public submission without a prompt")
    hist = commands.add_parser("history", help="Show this device's private run log")
    hist.add_argument("--game", default="")
    hist.add_argument("--limit", type=int, default=20)
    report = commands.add_parser("details", help="Write an offline interactive FPS chart")
    report.add_argument("result", type=Path)
    report.add_argument("--out", required=True, type=Path)
    campaign.arguments(commands)
    args = parser.parse_args(argv)
    try:
        if args.command == "campaign":
            campaign.execute(args)
        elif args.command == "history":
            journal.history(args.game, args.limit)
        elif args.command == "details":
            trace = json.loads(args.result.read_text(encoding="utf-8"))
            public = scores.public_fields(trace, "Personal GBA ROM")
            print(details.write_report(trace, public, args.out))
        elif args.command == "versions":
            print("\n".join(engines.releases()))
        elif args.command == "install":
            path, meta = engines.install(args.version)
            print(f"Installed mGBA {meta['tag']} at {path}")
        elif args.command == "run":
            if not args.rom and not sys.stdin.isatty():
                parser.error("supply --rom when running without a terminal")
            rom = args.rom or Path(input("Path to your GBA ROM: ").strip().strip('"'))
            with journal.attempt(rom, str(args.core.name if args.core else args.version or engines.REFERENCE)) as (run_id, start):
                result = scores.measure(rom.expanduser(), args.version, args.core, args.warmup_frames,
                                        args.frames, args.timeout)
                result.update(id=run_id, local_name=rom.name, started_utc=start, finished_utc=journal.now())
                path = scores.save(result, args.out)
                journal.complete(result, path)
            print(f"mGBA {result['version']} · {result['rendered_frames']} rendered frames\n"
                  f"Average FPS   {result['average_fps']:.0f}\n"
                  f"1% low FPS    {result['low_1pct_fps']:.0f}\n"
                  f"1% high FPS   {result['high_1pct_fps']:.0f}\nPrivate result: {path}")
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
    except (scores.InterruptedWindow, sqlite3.Error, OSError, ValueError, KeyError, TypeError, EOFError, subprocess.SubprocessError) as error:
        print(f"Emu Bench: {error}", file=sys.stderr)
        return 1
