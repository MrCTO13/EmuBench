"""Generate an original 32 KiB NTSC LoROM that changes backdrop colour each VBlank."""
from pathlib import Path
import struct
import sys


def write(path):
    image = bytearray(32768)
    program = bytes.fromhex("""
        78 d8 a2 ff 9a a9 0f 8d 00 21 a2 00
        2c 12 42 10 fb
        a9 00 8d 21 21 8a 8d 22 21 a9 00 8d 22 21 e8
        2c 12 42 30 fb 80 e5
    """)
    # Branch back to the rising-edge wait after the falling-edge wait.
    assert len(program) + int.from_bytes(program[-1:], "little", signed=True) == 12
    image[:len(program)] = program
    image[0x7fc0:0x7fd5] = b"EMUBENCH COLOR TEST".ljust(21)
    image[0x7fd5:0x7fdc] = bytes((0x20, 0, 5, 0, 1, 0, 0))
    struct.pack_into("<H", image, 0x7ffc, 0x8000)
    checksum = (sum(image) + 510) & 0xffff
    struct.pack_into("<HH", image, 0x7fdc, checksum ^ 0xffff, checksum)
    path.write_bytes(image)


if __name__ == "__main__":
    write(Path(sys.argv[1]))
