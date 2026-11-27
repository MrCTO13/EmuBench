"""An original PS-X EXE that fills the display with a changing color at VBlank."""
import struct
import sys
from pathlib import Path


def write(path):
    words = [0x3c08bf80, 0x35081810]  # t0 = GPU command port
    def load_t1(value):
        words.extend((0x3c090000 | value>>16, 0x35290000 | (value&65535)))
    for command in (0,0x03000000,0x05000000,0x06c60260,0x07042018,0x08000001):
        load_t1(command)
        words.append(0xad090004)
    words.extend((0x3c0abf80,0x354a1070,0x3c0b0200))  # interrupt status and GP0 fill command
    loop = len(words)
    words.extend((0x8d4c0000,0,0x318c0001,0x1180fffc,0))  # poll VBlank
    words.extend((0x240dfffe,0xad4d0000,0x256b0109,0xad0b0000,0xad000000))
    load_t1(240<<16 | 320)
    words.append(0xad090000)
    words.extend((0x10000000 | ((loop-len(words)-1)&65535),0))
    # Colors stay in the 24-bit argument for the duration of this fixture.
    image=bytearray(4096)
    image[:8]=b"PS-X EXE"
    struct.pack_into("<I",image,0x10,0x80010000)
    struct.pack_into("<II",image,0x18,0x80010000,2048)
    struct.pack_into("<"+"I"*len(words),image,2048,*words)
    path.write_bytes(image)


if __name__=="__main__":
    write(Path(sys.argv[1]))
