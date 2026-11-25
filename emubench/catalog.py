"""Public upstream packages and Libretro Buildbot IDs for the Emu Bench shortlist."""
from dataclasses import dataclass, field
import platform


@dataclass(frozen=True)
class Emulator:
    name: str
    core: str | None
    repo: str = ""
    # Case-insensitive whole-filename patterns, in preference order.
    assets: dict = field(default_factory=dict)


MAC = ("macos-arm64", "macos-x64")
WIN, LINUX = "windows-x64", "linux-x64"
TARGETS = {
    "macos-arm64": ("apple/osx/arm64", "dylib"),
    "macos-x64": ("apple/osx/x86_64", "dylib"),
    WIN: ("windows/x86_64", "dll"),
    "windows-arm64": (None, "dll"),
    "linux-arm64": ("linux/aarch64", "so"),
    LINUX: ("linux/x86_64", "so"),
}


def mac(pattern):
    return dict.fromkeys(MAC, pattern)


CATALOG = {
    "nestopia": Emulator("Nestopia UE", "nestopia", "0ldsk00l/nestopia", {
        MAC[0]: r"nestopia-[\w.-]+-macos-arm64\.dmg", WIN: r"nestopia-[\w.-]+-windows-x86_64\.zip",
        LINUX: r"nestopia_[\w.-]+_amd64\.deb"}),
    "fceumm": Emulator("FCEUmm", "fceumm"),
    "snes9x": Emulator("Snes9x", "snes9x", "snes9xgit/snes9x", {
        **mac(r"snes9x-[\w.]+-mac\.zip"), WIN: r"snes9x-[\w.]+-win32-x64\.zip",
        LINUX: r"snes9x-[\w.]+-x86_64\.appimage"}),
    "bsnes": Emulator("bsnes", "bsnes", "bsnes-emu/bsnes", {WIN: r"bsnes_[\w.]+-windows\.zip"}),
    "sameboy": Emulator("SameBoy", "sameboy", "LIJI32/SameBoy", {
        **mac(r"sameboy_cocoa_[\w.]+\.zip"), WIN: r"sameboy_winsdl_[\w.]+\.zip"}),
    "gambatte": Emulator("Gambatte", "gambatte"),
    "mgba": Emulator("mGBA", "mgba", "mgba-emu/mgba", {
        **mac(r"mgba-[\w.]+-macos\.dmg"), WIN: r"mgba-[\w.]+-win64\.7z",
        LINUX: r"mgba-[\w.]+-appimage-x64\.appimage"}),
    "gpsp": Emulator("gpSP", "gpsp"),
    "gearsystem": Emulator("Gearsystem", "gearsystem", "drhelius/Gearsystem", {
        MAC[0]: r"gearsystem-[\w.]+-desktop-macos-arm64\.zip",
        MAC[1]: r"gearsystem-[\w.]+-desktop-macos-intel\.zip",
        WIN: r"gearsystem-[\w.]+-desktop-windows-x64\.zip",
        LINUX: r"gearsystem-[\w.]+-desktop-ubuntu24\.04-x64\.zip"}),
    "genesis-plus-gx": Emulator("Genesis Plus GX", "genesis_plus_gx"),
    "picodrive": Emulator("PicoDrive", "picodrive"),
    "stella": Emulator("Stella", "stella", "stella-emu/stella", {
        **mac(r"stella-[\w.]+-macos\.dmg"), WIN: r"stella-[\w.]+-x64\.exe",
        LINUX: r"stella_[\w.]+_amd64\.deb"}),
    "beetle-pce-fast": Emulator("Beetle PCE Fast", "mednafen_pce_fast"),
    "beetle-supergrafx": Emulator("Beetle SuperGrafx", "mednafen_supergrafx"),
    "duckstation": Emulator("DuckStation", None, "stenzek/duckstation", {
        **mac(r"duckstation-mac-release\.zip"), WIN: r"duckstation-windows-x64-release\.zip",
        LINUX: r"duckstation-x64\.appimage"}),
    "pcsx-rearmed": Emulator("PCSX-ReARMed", "pcsx_rearmed"),
    "finalburn-neo": Emulator("FinalBurn Neo", "fbneo", "finalburnneo/FBNeo", {
        WIN: r"windows-x86_64\.zip", LINUX: r"linux-sdl2-x86_64\.zip"}),
    "mame": Emulator("MAME", "mame", "mamedev/mame", {WIN: r"mame\d+b_x64\.exe"}),
}


def host_target():
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    system = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(platform.system(), platform.system())
    target = system + "-" + arch
    if target not in TARGETS:
        raise ValueError(f"No package catalog for {target}. Select --target explicitly to download for another machine.")
    return target
