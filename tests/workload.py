"""Generate an original GBA test program in a caller-selected temporary folder."""
import struct
import sys
from pathlib import Path


def write(path):
    image = bytearray(512)
    struct.pack_into("<I", image, 0, 0xEA00002E)  # Branch to cartridge code at 0xC0.
    image[0xB2] = 0x96
    words = [
        0xE3A00301,  # mov r0, #0x04000000 (display registers)
        0xE3A01405,  # mov r1, #0x05000000 (background palette)
        0xE3A02000,  # mov r2, #0
        0xE1C020B0,  # strh r2, [r0] (enable display)
        0xE1D030B6,  # read VCOUNT
        0xE35300A0,  # cmp r3, #160
        0x1AFFFFFC,  # wait for first VBlank line
        0xE2822001,  # advance backdrop colour
        0xE1C120B0,  # write it to palette RAM
        0xE1D030B6,  # read VCOUNT
        0xE35300A0,
        0x0AFFFFFC,  # wait until scanline 160 ends
        0xEAFFFFF6,  # repeat on next frame
    ]
    struct.pack_into("<" + "I" * len(words), image, 0xC0, *words)
    path.write_bytes(image)


if __name__ == "__main__":
    write(Path(sys.argv[1]))
