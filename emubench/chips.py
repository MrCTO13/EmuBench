"""Original SA-1 and Super FX functional probes. Each cartridge displays its own verdict."""
import struct
from . import engines, scores, video

LEGACY = ("SA-1 multiply", "Super FX immediate")
NAMES = (*LEGACY, "DSP-1 fixed-point multiply")


def cartridge(name):
    # Both programs boot on the S-CPU in emulation mode, with 8-bit A/X.
    host=bytearray.fromhex("78 d8")
    def write(target,addr,value):
        target.extend((0xa9,value,0x8d,addr&255,addr>>8))
    def screen(out,color):
        for addr,val in ((0x2100,0x80),(0x212c,0),(0x2121,0),(0x2122,color&255),(0x2122,color>>8),(0x2100,15)):
            write(out,addr,val)
    screen(host,0x7c00)  # Blue while the cartridge is waiting for the coprocessor.
    # Copy the bus-handshake code from ROM to low WRAM. S-CPU keeps executing
    # even while the GSU owns the cartridge ROM bus.
    host.extend(bytes.fromhex("a2 00 bd 00 81 9d 00 02 e8 d0 f7 4c 00 02"))
    probe=bytearray()
    if name==NAMES[0]:
        for reg,val in ((0x2200,0x20),(0x2203,0),(0x2204,0x90),(0x2200,0)):
            write(probe,reg,val)
        probe.extend(bytes.fromhex("ad 00 23 29 0f f0 f9 c9 05"))
        # The SA-1 itself writes the signed operands (-7 and 9), starts multiplication
        # on the high byte write, and checks both result bytes of -63.
        remote=bytearray()
        for reg,val in ((0x2250,0),(0x2251,0xf9),(0x2252,0xff),(0x2253,9),(0x2254,0)):
            write(remote,reg,val)
        remote.extend(bytes.fromhex("ea ea ea ea ad 06 23 c9 c1 d0 09 ad 07 23 c9 ff d0 02 a9 05"))
        # Successful and failing paths both report through SCNT message bits.
        remote.extend(bytes.fromhex("80 02 a9 06 8d 09 22 80 fe"))
        # Branch offsets target the LDA #6 instruction.
        fail=remote.index(bytes.fromhex("a9 06 8d 09 22"))
        for pos in (remote.index(0xd0),remote.rindex(0xd0)):
            remote[pos+1]=fail-(pos+2)
        mapping,kind=0x23,0x34
    elif name==NAMES[1]:
        for reg,val in ((0x3034,0),(0x303a,0x18),(0x301e,0),(0x301f,0x90)):
            write(probe,reg,val)
        probe.extend(bytes.fromhex("ad 30 30 29 20 d0 f9"))
        write(probe,0x303a,0)
        probe.extend(bytes.fromhex("ad 00 30 c9 34 d0 05 ad 01 30 c9 12"))
        remote=bytes.fromhex("f0 34 12 00 01")  # IWT R0,#$1234; STOP; NOP.
        mapping,kind=0x20,0x13
    elif name==NAMES[2]:
        # Small LoROM maps the DSP-1 data port at $20:8000 and status at $20:C000.
        # Command $00 multiplies two signed Q15 operands. 0.5 * 0.5 = 0.25 ($2000).
        for val in (0,0,0x40,0,0x40):
            probe.extend(bytes.fromhex("af 00 c0 20 10 fa"))
            probe.extend((0xa9,val,0x8f,0,0x80,0x20))
        probe.extend(bytes.fromhex("af 00 c0 20 10 fa af 00 80 20 c9 00 d0 06 af 00 80 20 c9 20"))
        remote=b""
        mapping,kind=0x20,0x03
    else:
        raise ValueError("Unknown cartridge coprocessor check")
    green=bytearray()
    screen(green,0x03e0)
    green.extend((0x80,0xfe))
    probe.extend((0xd0,len(green)))
    probe.extend(green)
    screen(probe,0x001f)
    probe.extend((0x80,0xfe))
    image=bytearray(65536)
    image[:len(host)]=host
    image[0x100:0x100+len(probe)]=probe
    image[0x1000:0x1000+len(remote)]=remote
    image[0x7fc0:0x7fd5]=b"EMU BENCH CHIP PROBE".ljust(21)
    image[0x7fd5:0x7fdc]=bytes((mapping,kind,6,5,1,0,0))
    struct.pack_into("<H",image,0x7ffc,0x8000)
    checksum=(sum(image)+510)&65535
    struct.pack_into("<HH",image,0x7fdc,checksum^65535,checksum)
    return bytes(image)


def verdict(capture):
    width,height,rgb=video.rgb_frame(capture)
    if (width,height)!=(256,224):
        return "unresolved"
    palette=set(zip(*[iter(rgb)]*3))
    if palette=={(0,248,0)}:
        return "pass"
    if palette=={(248,0,0)}:
        return "fail"
    return "unresolved"


def run(emulator,core):
    if emulator=="mgba":
        raise ValueError("Choose a SNES emulator for the coprocessor checks")
    result={}
    for name in NAMES:
        try:
            _, (capture,)=scores.run_worker(engines.worker(),core,cartridge(name),0,120,30,None,
                                            scores.ADAPTERS[emulator][0],bytes(240),diagnostic=True)
            result[name]=verdict(capture)
        except (ValueError,TimeoutError):
            result[name]="unresolved"
    return result
