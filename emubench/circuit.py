"""Source-built Carter Circuit. All program instructions and pixel artwork are original MIT code."""
import hashlib
import struct
from dataclasses import dataclass

from . import engines, video

LEVELS = ("easy", "normal", "hard")
# Original eight-pixel runner, trail and landscape tiles. Zero is transparent.
TILES = (
    ("00000000",)*8,
    ("00022000","00222200","00012000","00233000","00333320","00033000","00300300","03300030"),
    ("00000000","00000000","00000000","00000000","00000022","00000232","00002332","00023332"),
    ("22222222","33333333","31333313","33331333","13333333","33313331","33333333","31333133"),
    ("00000000","00000000","00010000","00111000","00010000","00000000","00000000","00000000"),
)
COLORS = (0x1042, 0x77ff, 0x7e83, 0x3189)
DESCRIPTIONS = ("Scroll a single trail layer", "Scroll the trail and moving scenery",
                "Animate the trail, scenery and a denser field of runners")


def scene_tile(x, y, level):
    if y >= 19 + ((x // 6) % 2):
        return 3
    if y == 18 and x % (9 - 3 * level) == 1:
        return 1
    if y > 12 and (x+y) % 8 < 2:
        return 2
    return 4 if (7*x + 13*y) % (39 - 9*level) == 0 else 0


def snes_image(level, revision=2):
    code = bytearray.fromhex("78 d8 a2 ff 9a")  # SEI, CLD, initialize emulation-mode stack.
    def store(address, value):
        code.extend((0xa9, value, 0x8d, address & 255, address >> 8))
    def vram(address, data):
        store(0x2116, address & 255)
        store(0x2117, address >> 8)
        for off, byte in enumerate(data):
            store(0x2118 + off % 2, byte)
    store(0x2100, 0x80)
    store(0x2115, 0x80)
    store(0x2105, 0)
    store(0x2107, 4)
    store(0x2108, 8)
    store(0x210b, 0)
    tiles = bytearray()
    for tile in TILES:
        for line in tile:
            for bit in (0, 1):
                tiles.append(sum(((int(pixel) >> bit) & 1) << (7-i) for i,pixel in enumerate(line)))
    vram(0, tiles)
    for layer in range(1 if level == 0 else 2):
        cells = bytearray()
        for y in range(32):
            for x in range(32):
                tile = scene_tile(x, y, level) if layer == 0 else (4 if (x*5+y*7)%19==0 else 0)
                cells.extend((tile, 0))
        vram(0x400*(layer+1), cells)
    for start in (0,32):
        store(0x2121, start)
        for color in COLORS:
            store(0x2122, color & 255)
            store(0x2122, color >> 8)
    store(0x212c, 1 if level==0 else 3)
    if level == 2 and revision == 2:
        # Four backgrounds plus the subscreen in 512-pixel pseudo-hires.
        store(0x2109, 4)
        store(0x210a, 8)
        store(0x212c, 15)
        store(0x212d, 15)
        store(0x2130, 2)
        store(0x2131, 0x3f)
        store(0x2133, 8)
    store(0x2100, 15)
    code.extend((0xa2,0))  # X is the frame/scroll counter.
    start = len(code)
    code.extend(bytes.fromhex("2c 12 42 10 fb e8 8a 8d 0d 21 a9 00 8d 0d 21"))
    if level:
        code.extend(bytes.fromhex("8a 4a 8d 0f 21 a9 00 8d 0f 21"))
    if level==2:
        # Update a palette entry each VBlank as the runners pass the scenery.
        store(0x2121, 2)
        code.extend(bytes.fromhex("8a 8d 22 21 a9 78 8d 22 21"))
    code.extend(bytes.fromhex("2c 12 42 30 fb"))
    code.extend((0x4c, start & 255, 0x80 + (start >> 8)))
    image = bytearray(32768)
    assert len(code)<0x7fc0
    image[:len(code)] = code
    image[0x7fc0:0x7fd5] = b"CARTER CIRCUIT V1".ljust(21)
    image[0x7fd5:0x7fdc] = bytes((0x20,0,5,0,1,0,0))
    struct.pack_into("<H", image, 0x7ffc, 0x8000)
    checksum = (sum(image) + 510) & 0xffff
    struct.pack_into("<HH", image, 0x7fdc, checksum ^ 0xffff, checksum)
    return bytes(image)


def gba_image(level, revision=2):
    image = bytearray(0x400)
    struct.pack_into("<I", image, 0, 0xea00002e)  # ARM branch to cartridge entry.
    image[0xa0:0xac] = b"CARTERCIRCUT"
    image[0xac:0xb0] = b"CE01"
    image[0xb2] = 0x96
    image[0xbd] = (-sum(image[0xa0:0xbd])-0x19) & 255
    words, literals = [], []
    def load(reg, value):
        literals.append((len(words), reg, value))
        words.append(0)
    load(0,0x04000000)
    load(1,0x05000000)
    load(4,0x08000400)
    load(7,0x06000000)
    load(5,240*160//4)
    words.extend((0xe4946004,0xe4876004,0xe2555001,0x1afffffb))  # Copy packed pixels to VRAM.
    for idx,color in enumerate(COLORS):
        load(6,color)
        words.append(0xe1c160b0 + (idx*2))
    load(6,0x404)
    words.append(0xe1c060b0)
    load(6,256)
    words.extend((0xe1c062b0,0xe1c062b6))  # Identity BG2 affine transform.
    if level == 2 and revision == 2:
        # Semitransparent 64x64 objects overlap across all 160 visible scanlines.
        load(8,0x07000000)
        load(9,0xc0000400)
        load(10,30<<16)
        load(11,8)
        row=len(words)
        words.extend((0xe1a06009,0xe3a05008))
        column=len(words)
        words.extend((0xe4886004,0xe3a07c02,0xe4887004,0xe086600a,0xe2555001))
        words.append(0x1a000000 | ((column-len(words)-2) & 0xffffff))
        words.extend((0xe2899014,0xe25bb001))
        words.append(0x1a000000 | ((row-len(words)-2) & 0xffffff))
        load(8,0x06014000)
        load(6,0x11111111)
        load(5,512)
        words.extend((0xe4886004,0xe2555001,0x1afffffc))
        load(6,0x7fff)
        load(8,0x05000202)
        words.append(0xe1c860b0)
        load(6,0x1444)  # Mode 4, BG2, OBJ, linear sprite character mapping.
        words.append(0xe1c060b0)
        load(6,0x0440)
        words.append(0xe1c065b0)
        load(6,0x0808)
        words.append(0xe1c065b2)
    words.append(0xe3a02000)
    top=len(words)
    words.extend((0xe1d030b6,0xe35300a0,0x1afffffc,0xe2822001))
    words.extend((0xe202600f,0xe1a06406,0xe5806028))  # Horizontal origin in 24.8 format.
    if level:
        words.extend((0xe202603f,0xe1c160b4))
    if level==2:
        words.extend((0xe202600f,0xe1a06406,0xe580602c))
    words.extend((0xe1d030b6,0xe35300a0,0x0afffffc))
    words.append(0xea000000 | ((top-len(words)-2) & 0xffffff))
    for index,reg,value in literals:
        words[index]=0xe59f0000 | reg<<12 | ((len(words)-index-2)*4)
        words.append(value)
    struct.pack_into("<"+"I"*len(words),image,0xc0,*words)
    for y in range(160):
        for x in range(240):
            tile=scene_tile(x//8,y//8,level)
            image.append(int(TILES[tile][y%8][x%8]))
    return bytes(image)


def cartridge(console, level):
    index=LEVELS.index(level)
    data = gba_image(index) if console=="gba" else snes_image(index)
    digest=hashlib.sha256(data).hexdigest()
    suffix="gba" if console=="gba" else "sfc"
    path=engines.home()/"circuit"/digest/f"carter-circuit-{level}.{suffix}"
    from .accuracy import atomic_write
    if not path.is_file() or engines.digest(path)!=digest:
        atomic_write(path,data)
    return path


FRAMES = 600
WARMUP = 120


@dataclass(frozen=True)
class Scene:
    console: str
    level: str
    digest: str
    references: tuple
    revision: int = 1
    warmup = WARMUP

    @property
    def profile(self):
        return f"{self.console}-circuit-{self.level}-v{self.revision}"

    @property
    def description(self):
        if self.revision == 2 and self.level == 'hard':
            return 'Composite 64 translucent objects over an affine bitmap' if self.console=='gba' else 'Composite four backgrounds and the subscreen in pseudo-hires'
        return DESCRIPTIONS[LEVELS.index(self.level)]

    @property
    def title(self):
        return f"Carter Circuit ({self.console.upper()} {self.level})"

    @property
    def playback(self):
        return bytes(2 * (self.warmup + FRAMES))

    def validate(self, digest, warmup, frames, checkpoints):
        if (digest, warmup, frames) != (self.digest, self.warmup, FRAMES):
            raise ValueError("Circuit cartridge or frame window differs from the published profile")
        pair = tuple(video.fingerprint(frame) for frame in checkpoints)
        if pair not in self.references:
            raise ValueError(f"{self.title} missed a visual checkpoint")
        return pair


# Paired software reference frames from the fixed scene. SNES conversions differ by core.
LEGACY_SCENES = (
    Scene("snes", "easy", "0637b15195e7c819a2ca695817478c696ec7d09b9f62e9d361aa912d266fa5f0", (
        ("2271f3b1f5fc6c52d180ff8810b793ea5f29036b88a9bc1419462ddc938790c1",
         "ab5a44244155c8563e74cb96b76baa9751e451b17647090925037f9ee4b841e3"),
        ("22b32eb7fddf196ba2dfef9bf2440655cfc1bdf00e21ffbb7a157a739845ce6f",
         "1c9b4697b1af342ce565eee67d29d4b9010c9a032cbc096cd6c499573251820c"),
    )),
    Scene("snes", "normal", "476387044c40922cdd34a3c33477675b337250e9ccabe2ec8677a0e6633a3edc", (
        ("04a4f65245b5a69301e7f9e5f4ef0c288e4739d1d30833011d5cb33555c9bd26",
         "2cb0b074002353b7083a002010c0b8f2487a98fa206db510fc83445a9dab7632"),
        ("962d2e5a72e31957ee82edad571068e15d647fe3fba2e56e0a3133581cb1d3ae",
         "a90eec147be7ac3dc9ce7f66375d58cfa14d383a964e631dfcaa91283fb3cba4"),
    )),
    Scene("snes", "hard", "c838208c59b5e2a80c8a7d6c63ceb357645fa120a735d886977b2cc046c76c6e", (
        ("94c17692115df28b8780b147bba755c5c5e512b1a60dc99d7a2c5a1c28c048df",
         "659946ef1ee80920a2e8894d41b2040d425049ee0902fb3ac1f16de14f24f00c"),
        ("5e62710eb7e0496cfc22f8c23da1ae5bcaa0f11391005aac6d54b439b9a4eff5",
         "4275c070b07fa9f42b9e2c0a0aa4b9afc9965f3a22df4fdd2152fea2f21e1aa2"),
    )),
    Scene("gba", "easy", "245b9ef0fab8037162b80629c608101fc83e0eeba8644a4f6166e800e854a484", (
        ("db883a09ad4e1dece0bf604d9d2592c8134d910de23de71a38438bdf648ae9bb",
         "be51a7f2bb63e8e69bcf3966ce4b07aeedeb0077f4047a7dd4598409042074d0"),
    )),
    Scene("gba", "normal", "cfe21454565459d2e68c3cb5e25871144258f67c1aa75c3e95a444e5758d7edb", (
        ("43bd287c8c53f9a9e4ab20a87369963a453b6af8d12475ffb2316076adfd33d3",
         "d66569fb81135abeac580810df0de9d93463eaeefcc8bc1bcdbdd17b02431444"),
    )),
    Scene("gba", "hard", "17e13bdbcf15088e2dc43e889fcf6003617e059b57cccdfab2939427212c4f45", (
        ("6001ddaeb57b70315903d9f2ac549b4f9e6f1fb9318b1407b44f52bbf069a4fd",
         "53883cbf076df8818003d957573cb973e66c9109b10666e967ef334d2ae44cb7"),
    )),
)
# Easy and normal retain the v1 program and checkpoints.
from dataclasses import replace
SCENES = tuple(replace(s, revision=2) for s in LEGACY_SCENES if s.level!="hard") + (
    Scene("snes", "hard", "376cff6f9cbacc9c746f94f9851cf17606e1513a0e6805dfbf20c6cfbc8ce004", (
        ("2964cc40686a5af8740aa7f6b58e71effbc1539e244e1efd967d90765d19d04e",
         "bec65d9ee95cac48ad926856d996f32a53620f6a461e7aab1cfd1dda775baacd"),
        ("2f0772c5403870b61942008ab0e31f9736664d320f4bc69c49f73866f5110732",
         "c244f350afd2c538c5c5e38932b12fae97646c81927c98704d42128a20e83d07"),
    ), revision=2),
    Scene("gba", "hard", "f25e57ecf290bb5e1b69d61d802511c1c066915a0b8b12c55503204a0df07b23", (
        ("031b39e63995332f7ef3d269f3ce7182902139b41c37d5ad52e99eaacaa278cd",
         "cf092a70d060e38bd47310fe3cc7d941b2286e91ffd047438f6e79112a018737"),
    ), revision=2),
)
PROFILES = {scene.profile: scene for scene in (*LEGACY_SCENES, *SCENES)}
