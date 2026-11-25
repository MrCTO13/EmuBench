"""Game Boy Color tests with independent, published expected results."""
from hashlib import sha256
from urllib.parse import quote

from . import engines, scores, video

REV = "c240dd7d700e5c0b00a7bbba52b53e4ee67b5f15"
SOUND = "https://raw.githubusercontent.com/retrio/gb-test-roms/"+REV+"/cgb_sound/rom_singles/"
GRAPHICS = "CGB LCD window and sprite priority"
CHECKS = {
    GRAPHICS: ("https://github.com/mattcurrie/cgb-acid2/releases/download/v1.1/cgb-acid2.gbc",
               "197fb0bcec544f0400527fc707e0a94f55435974986e6986b424ace5de81720e"),
    "APU registers": ("01-registers.gb","8415d6c69f7954e9365a586bac235f5ce39270ece32c09cb8ebbbff043b9852c"),
    "APU length counter": ("02-len ctr.gb","a1ccf47375a2bede3077ac85a4903cb037dd8a4c7c85fc5d0c176af52915271f"),
    "APU trigger": ("03-trigger.gb","70173be396d14ac955c47aededcee90ba994206cc403273d0bb49ba163ae23ef"),
    "APU sweep": ("04-sweep.gb","abfd1f6fa9e6701e46135ac9f5bb5b10a46cde22d0fc34922636aa09a5647483"),
    "APU active wave RAM read": ("09-wave read while on.gb","9b101c68b2de1930df74c19aaf22cce74d37dd5aade93855c805ecb2e1e83fd3"),
}
# First-occurrence palette indices of every pixel in the author's v1.1 img/reference.png.
# This tests the entire color partition while allowing different display color corrections.
REFERENCE = "dd9ea2c83d55be2d7a5d26fa70ce1f42fce3e2464d44cdd9e54f7eb626125aaa"

def verdict(name, capture):
    w,h,rgb = video.rgb_frame(capture)
    if (w,h)!=(160,144):
        return "unresolved"
    if name != GRAPHICS:
        # The upstream console prints its verdict on a tile-aligned line.
        for y in range(0,h,8):
            for label,digest in (("pass","7bdc040aded072fa96fbf2abb9bb17acbd95772cf7c2b4a70bfe12f03c46b467"),
                                 ("fail","2ece11426317ca73047c1ace526e8b94bf146631eb37651f375c7b559300bc73")):
                mask = bytes(rgb[3*(w*row+x)]<128 for row in range(y,y+8) for x in range(48))
                if sha256(mask).hexdigest()==digest or sha256(bytes(1-i for i in mask)).hexdigest()==digest:
                    return label
        return "unresolved"
    colors = {}
    pixels = bytearray()
    for color in zip(*[iter(rgb)]*3):
        if len(colors)>8:
            return "fail"
        pixels.append(colors.setdefault(color,len(colors)))
    return "pass" if sha256(pixels).hexdigest()==REFERENCE else "fail"

def run(emulator, core):
    from .accuracy import checked_download
    worker,_ = engines.timing_worker(core)
    checks = {}
    for name,(source,digest) in CHECKS.items():
        graphics = name==GRAPHICS
        url = source if graphics else SOUND+quote(source)
        data = checked_download(engines.home()/"conformance"/"gbc-v1"/digest,digest,url)
        frames = 240 if graphics else 1200
        try:
            _,(capture,) = scores.run_worker(worker,core,data,120,frames,60,None,
                scores.ADAPTERS[emulator][0],bytes(2*(120+frames)),diagnostic=True,
                filename="workload.gbc")
            checks[name] = verdict(name,capture)
        except (TimeoutError,ValueError):
            checks[name] = "unresolved"
    return {"suite":"gbc-v1","core_sha256":engines.digest(core),"worker_sha256":engines.digest(worker),"checks":checks}
