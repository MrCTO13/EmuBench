"""Exercise both verdicts on actual coprocessor emulation."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from emubench import chips, downloads, engines, scores


def check(emulator,core):
    worker=engines.worker()
    for name in chips.NAMES:
        image=chips.cartridge(name)
        good,bad=(bytes.fromhex("c9 c1"),bytes.fromhex("c9 c2")) if name==chips.NAMES[0] else (bytes.fromhex("f0 34 12 00 01"),bytes.fromhex("f0 35 12 00 01"))
        if name=="DSP-1 fixed-point multiply":
            good,bad=bytes.fromhex("c9 20 d0"),bytes.fromhex("c9 21 d0")
            if chips.run(emulator,core)[name]=="unresolved":
                print("DSP-1 unresolved on this build")
                continue
        assert image.count(good)==1
        for program,expected in ((image,"pass"),(image.replace(good,bad),"fail")):
            _,(frame,)=scores.run_worker(worker,core,program,0,120,30,None,scores.ADAPTERS[emulator][0],
                                         bytes(240),diagnostic=True)
            assert chips.verdict(frame)==expected,(emulator,name,expected)
    print(emulator,"accepted correct results and rejected altered arithmetic/instruction results")


if __name__=="__main__":
    check(sys.argv[1],Path(sys.argv[2]) if len(sys.argv)>2 else downloads.latest_core(sys.argv[1]))
