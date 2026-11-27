"""Which emulator builds may be ranked, and the conflict-of-interest disclosure.

A build is *verified* only when its exact core SHA-256 is listed in
verified_builds.json, which the lab fills after matching the file to an official
upstream release or signed nightly. Everything else is a custom build: it can be
measured and shared, but it is never ranked. Closed builds that nobody else can
download are never ranked, even if their hash is known.
"""
import json
from pathlib import Path

CLOSED_EMULATORS = ("CartsSNES",)

DISCLOSURE = ("EmuBench is built and run by Mr.CTO (GitHub account MrCTO13). The same person develops CARTS, "
              "a commercial emulator project that includes the CartsSNES core, and made the Carter homebrew "
              "games and Carter Circuit scenes used as official workloads. To keep that from tilting the "
              "results: the method and every workload are open source, every emulator runs in the same harness, "
              "CartsSNES is a closed build and is never ranked, and results where CARTS is slower are published "
              "the same way as results where it is faster.")


def builds():
    path = Path(__file__).with_name("verified_builds.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    for sha, entry in data["builds"].items():
        if len(sha) != 64 or set(entry) != {"emulator", "version", "source", "upstream_sha256_source"}:
            raise ValueError("Invalid verified build entry")
    return data["builds"]


def standing(emulator, version, core_sha256):
    if emulator in CLOSED_EMULATORS:
        return "closed"
    entry = builds().get(core_sha256)
    return "verified" if entry and entry["emulator"] == emulator and entry["version"] == version else "custom"
