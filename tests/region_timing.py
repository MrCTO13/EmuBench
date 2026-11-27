"""Run both regional editions of our own SNES program on a real Snes9x core."""
import sys
import tempfile
from pathlib import Path
from emubench import circuit, scores

with tempfile.TemporaryDirectory() as tmp:
    for code, region, hz in [(1,"NTSC",60.1),(2,"PAL",50.0)]:
        image = bytearray(circuit.snes_image(1))
        image[0x7fd9] = code
        image[0x7fdc:0x7fe0] = bytes(4)
        checksum = (sum(image) + 510) & 65535
        image[0x7fdc:0x7fe0] = (checksum ^ 65535).to_bytes(2,"little") + checksum.to_bytes(2,"little")
        rom = Path(tmp) / "scene.sfc"
        rom.write_bytes(image)
        run = scores.measure(rom,None,Path(sys.argv[1]),120,600,30,emulator="snes9x")
        mode = run["video_mode"]
        assert mode["region"] == region and abs(mode["refresh_hz"]-hz)<0.1, mode
        assert run["speed_x"] == 1e9*len(run["frame_ns"])/(sum(run["frame_ns"])*mode["refresh_hz"])
        print(region, mode["refresh_hz"], "Hz")
