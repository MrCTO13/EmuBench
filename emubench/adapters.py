"""Timing routes. A suffix assigns the console, even for multi-system cores."""
from .catalog import CATALOG

SUITE_PEERS = ("mgba", "snes9x", "bsnes", "cartssnes")
ROUTES = {
    "nes": (("nes",), ("nestopia", "fceumm")),
    "snes": (("sfc", "smc"), ("snes9x", "bsnes")),
    "gb": (("gb",), ("sameboy", "gambatte")),
    "gbc": (("gbc",), ("sameboy", "gambatte")),
    "gba": (("gba",), ("mgba", "gpsp")),
    "sms": (("sms",), ("gearsystem", "genesis-plus-gx", "picodrive")),
    "gg": (("gg",), ("gearsystem", "genesis-plus-gx", "picodrive")),
    "genesis": (("md", "gen"), ("genesis-plus-gx", "picodrive")),
    "32x": (("32x",), ("picodrive",)),
    "atari2600": (("a26",), ("stella",)),
    "pce": (("pce",), ("beetle-pce-fast", "beetle-supergrafx")),
    "sgx": (("sgx",), ("beetle-supergrafx",)),
    "psx": (("exe", "pbp", "chd"), ("pcsx-rearmed",)),
    "arcade": (("zip",), ("finalburn-neo", "mame")),
}
SUFFIXES = {"."+ext:console for console,(extensions,_) in ROUTES.items() for ext in extensions}
NAMES = {key:emu.name for key,emu in CATALOG.items() if emu.core}
NAMES["cartssnes"] = "CartsSNES"
CORE_NAMES = {**NAMES, "nestopia":"Nestopia"}
CONSOLES = {name:[console for console,(_,peers) in ROUTES.items()
                  if key in peers or key=="cartssnes" and console=="snes"] for key,name in NAMES.items()}

def profile(console):
    return console+"-boot-no-input-v1"
