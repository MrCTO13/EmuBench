"""Verify the workload gradient using one real local core at a time."""
from pathlib import Path
from statistics import median
import sys
from emubench import circuit, scores

peer, core = sys.argv[1:]
rates = {}
console = "gba" if peer=="mgba" else "snes"
for scene in circuit.SCENES:
    if scene.console != console:
        continue
    values = []
    for _ in range(3):
        run = scores.measure(circuit.cartridge(console,scene.level),None,Path(core),scene.warmup,
                             circuit.FRAMES,60,emulator=peer,scene=scene)
        values.append(run["speed_x"])
    rates[scene.level] = median(values)
assert rates["hard"] < 0.90 * rates["normal"], rates
print(peer, rates)
