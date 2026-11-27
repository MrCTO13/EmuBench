"""Rendering polarity on original programs, using the actual selected mGBA core."""
import sys
import tempfile
from pathlib import Path
from emubench import scores
from workload import write

with tempfile.TemporaryDirectory() as root:
    path=Path(root)/"motion.gba"
    write(path)
    def run():
        return scores.measure(path,None,Path(sys.argv[1]),120,600,60)
    result=run()
    check=result["frame_check"]
    # Every 17th frame at a random phase, in each repeat of the 600-frame window.
    first=(17-check["phase"])%17
    per_loop=(600-1-first)//17+1
    assert check["samples"]==per_loop*result["window"]["loops"] and check["changes"]==check["samples"]-1, check
    image=bytearray(path.read_bytes())
    # Replace incrementing backdrop color with a fixed color.
    image[0xc0+7*4:0xc0+8*4]=(0xe3a02001).to_bytes(4,"little")
    path.write_bytes(image)
    try:
        run()
    except ValueError as exc:
        assert "No motion" in str(exc), exc
    else:
        raise AssertionError("A frozen rendering received a score")
