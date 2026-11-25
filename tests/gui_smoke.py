"""Launch the packaged window and drive the same native widgets through a real GBA replay."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from emubench import engines, games
from emubench.gui import Desktop, WORKLOADS, LOCAL, tk


def wait(predicate, timeout, update=lambda: None):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        update()
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError("Timed out waiting for the desktop app")


def main():
    win=os.name=="nt"
    dist=Path("dist/gui")
    app=dist/("EmuBench" if win else "EmuBench.app")
    launcher=app/"EmuBench.exe" if win else app/"Contents/MacOS/EmuBench"
    resources=app if win else app/"Contents/Resources"
    engine=(resources/"benchmark"/("emubench"+engines.EXE)).resolve()
    games.verify(resources/"benchmark/games")
    with TemporaryDirectory() as tmp:
        os.environ["EMUBENCH_HOME"]=tmp
        gui=subprocess.Popen([launcher.resolve()])
        try:
            def ready():
                if gui.poll() is not None:
                    raise AssertionError(f"Packaged GUI exited with {gui.returncode}")
                return (Path(tmp)/"history.sqlite").is_file()
            wait(ready,45)
        finally:
            gui.terminate()
            gui.wait(timeout=20)
        root=tk.Tk()
        window=Desktop(root,[str(engine)])
        assert window.workload.get()==next(iter(WORKLOADS))
        if len(sys.argv)>1:
            window.source.set(LOCAL)
            window.source_changed()
            window.core.set(str(Path(sys.argv[1]).resolve(strict=True)))
        window.run_button.invoke()
        wait(lambda:not window.busy,360,root.update)
        assert window.status.get()=="Benchmark finished",window.log.get("1.0","end")[-3500:]
        assert float(window.metrics[0].get().rstrip("×"))>0
        assert all(int(x.get())>0 for x in window.metrics[1:])
        assert "checks" in window.accuracy.get()
        rows=tuple(window.rows.values())
        assert len(rows)==1 and Path(rows[0][6]).is_file()
        sample=next((resources/"benchmark/games/roms/gba").glob("*.gba"))
        window.workload.set("Local ROM file")
        window.workload_changed()
        window.path.set(str(sample))
        window.choose_peers()
        assert "mGBA" in window.peers and "bsnes" not in window.peers
        assert str(sample.resolve()) in window.plan()[0]
        window.tabs.select(1)
        window.history.selection_set(rows[0][0])
        assert window.selected_result()[0]==rows[0][0]
        print("Packaged window launched. A real Carter replay completed through the native Run button. FPS, accuracy, saved history, ROM selection and paths passed.",flush=True)
        window.close()


if __name__=="__main__":
    main()
