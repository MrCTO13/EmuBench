"""Versioned controller-only scenes for two exact Carter homebrew releases."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from urllib.error import URLError

from . import downloads, engines, video


@dataclass(frozen=True)
class Cartridge:
    title: str
    digest: str
    filename: str


GAMES = {
    "gba": Cartridge("Cartervania", "817d58c35906a283d70bb220d05b18159b6473feb2bb74f1bb4e381f8b10de4e",
                     "Carts-Cartervania-GBA.gba"),
    "snes": Cartridge("Super Carter Bros. 3", "01e6f240178965f9d149e65ffeb8197bf460e9b9a6128467f4b012ff3d075ec9",
                      "Super-Carter-Bros-3.sfc"),
}
# Durations are console video frames. Masks use the standard libretro joypad IDs.
GBA_OPEN = ((180,0),(4,256),(20,0),(4,8),(80,0))
SNES_MAP = ((240,0),(5,1),(90,0),(5,8),(80,0))
SNES_STAGE = SNES_MAP + ((5,1),(220,0))
FRAMES = 180


@dataclass(frozen=True)
class Scene:
    console: str
    level: str
    description: str
    setup: tuple
    route: tuple
    references: tuple

    @property
    def profile(self):
        return f"{self.console}-carter-{self.level}-v1"

    @property
    def title(self):
        return f"{GAMES[self.console].title} ({self.level})"

    @property
    def warmup(self):
        return sum(n for n, _ in self.setup)

    @property
    def playback(self):
        return b"".join(struct.pack("<H", buttons)*frames for frames, buttons in self.setup+self.route)

    def validate(self, digest, warmup, frames, checkpoints):
        if (digest, warmup, frames) != (GAMES[self.console].digest, self.warmup, FRAMES):
            raise ValueError("Cartridge or frame window differs from the pinned Carter workload")
        signatures = tuple(video.fingerprint(frame) for frame in checkpoints)
        if signatures not in self.references:
            raise ValueError(f"{self.title} missed a visual checkpoint. Its FPS result is unscored.")
        return signatures


def cartridge(console, supplied):
    game = GAMES[console]
    if supplied:
        path = supplied.expanduser().resolve(strict=True)
        if engines.digest(path) != game.digest:
            raise ValueError(f"Choose the pinned {game.title} cartridge (SHA-256 {game.digest})")
        return path
    directory = engines.home() / "carter" / game.digest
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / game.filename
    if path.is_file() and engines.digest(path) == game.digest:
        return path
    url = f"https://github.com/MrCTO13/EmuBench/releases/download/carter-games-v1/{game.filename}"
    try:
        fetch_asset(url, game.digest, path)
    except (OSError, URLError) as exc:
        raise ValueError(f"Public asset unavailable for {game.title}. Use --rom for the pinned edition, "
                         "or run the source-built Carter Circuit using emubench suite.") from exc
    return path


def fetch_asset(url, digest, path):
    from .accuracy import atomic_write
    payload = downloads.fetch_bytes(url, 8*1024**2)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Public release asset failed its pinned SHA-256 check")
    atomic_write(path,payload)


# Paired start/end raster digests, observed in software. SNES cores use different color conversion.
SCENES = (
    Scene("gba", "easy", "Castle entrance, Carter standing with the idle animation",
          GBA_OPEN, ((180,0),), (
              ("091f0b971463bdeef104f4bae91e7e2cafdc7948230dfbae75cf642a34fa8d54",
               "6a44d536c978bac7b09ba41de13b7addc81c1f89afd218400dfd8354c4f11bdd"),
          )),
    Scene("gba", "normal", "Three standing jumps at the castle entrance",
          GBA_OPEN, ((14,256),(46,0))*3, (
              ("091f0b971463bdeef104f4bae91e7e2cafdc7948230dfbae75cf642a34fa8d54",
               "bf58bd4a8741bc44fc6c225bc1247429a4177821583a31086377957f9fdb2ccb"),
          )),
    Scene("gba", "hard", "Traverse the castle with two jump and dash sequences",
          GBA_OPEN, ((30,128),(12,384),(16,128),(15,385),(17,128))*2, (
              ("091f0b971463bdeef104f4bae91e7e2cafdc7948230dfbae75cf642a34fa8d54",
               "195f5d0646c1590ee0b7708be10a9436ab476fc44601c130f8b56246a4f27af7"),
          )),
    Scene("snes", "easy", "Sunlit Shores overworld map",
          SNES_MAP, ((180,0),), (
              ("74e838277fe99f56b6899d6ba5f2fcd71f16b0011dea12f5cfb24d07b106f2bc",
               "3eb5c8e75559b5b5658812b4ebcf0c9f1d7889ed294d25eeea0b7231b0c40a15"),
              ("1d235c2da10418797d4b9161b17b0a82523f8136541696b9bfe2b5e4c95973cc",
               "ce578ed098bf23a40e7a608ce926d0eb59fc13e1b011710f4366a0d4bb094333"),
          )),
    Scene("snes", "normal", "Walk through the opening of Sunspill Orchard",
          SNES_STAGE, ((180,128),), (
              ("902295134b920c9addfa48657ad1b685675e9b9361913e1040f9cb82a507a65a",
               "163ef8a6b17ae561789c76cc4bc50ed8256de9df29270a226a9868861886cdd9"),
              ("d41b0fc20b99af8c3f9d32336dcd2577cdcda6072ba4337a4ed18f2c76eb11b0",
               "15412d2a1e27aa89b41cab7d3ca19751e11d7f1d84b50e5287089d5dbf934071"),
          )),
    Scene("snes", "hard", "Run, jump and dash through Sunspill Orchard with scrolling and sprites",
          SNES_STAGE, ((25,130),(12,131),(18,130),(10,386),(25,130))*2, (
              ("902295134b920c9addfa48657ad1b685675e9b9361913e1040f9cb82a507a65a",
               "88a2b616c3530c7925d0681628d435c28775ccf76e95f04eac6025beec78546e"),
              ("d41b0fc20b99af8c3f9d32336dcd2577cdcda6072ba4337a4ed18f2c76eb11b0",
               "f523027c200f6e699f3d7a98e6adb10311df8c079c3e418140f758d671639ed8"),
          )),
)
PROFILES = {scene.profile: scene for scene in SCENES}
