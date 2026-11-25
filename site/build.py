"""Bundle the native Sites worker with the exact protocol constants used by the CLI."""
import base64
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))
from emubench import games, adapters, carter, chips, circuit, color_checks, lab

out = Path(sys.argv[1])
profiles = {s.profile: dict(console=s.console, title=s.title, description=s.description, warmup=s.warmup,
                            frames=m.FRAMES, references=s.references) for m in (carter, circuit) for s in m.PROFILES.values()}
page = (root / "index.html").read_text()
page = page.replace("__EMU__", (root / "assets/emu-bench-wordmark.svg").read_text())
page = page.replace("__STYLES__", (root/"styles.css").read_text()).replace("__RELEASE__", "https://github.com/MrCTO13/EmuBench/releases/tag/v0.8.0-rc.1").replace("__SOURCE__", "https://github.com/MrCTO13/EmuBench/tree/d9289f7c1625a920b7dad006d5b06fd3769ed036")
assets = {p.name: base64.b64encode(p.read_bytes()).decode("ascii") for p in (root/"assets"/n for n in ["sunspill-orchard.png","bricolage.woff2","bricolage-license.txt","dm-sans.woff2","dm-sans-license.txt"])}
registry = {"studies":lab.studies(),"receipts":[]}
for path in sorted((root/"reviewed").glob("*.json")):
    receipt=json.loads(path.read_text())
    lab.validate_receipt(registry["studies"],receipt)
    registry["receipts"].append(receipt)
client = "const CARTER_GAMES="+json.dumps(games.PACK["games"])+";\nconst CORE_CONSOLES="+json.dumps({**adapters.CONSOLES,'DuckStation':['psx']})+";\nconst LAB="+json.dumps(registry)+";\n"+"\n".join(p.read_text() for p in (root.parent / "emubench/chart.js", root/"analysis.js", root/"lab.js", root/"demo.js", root/"library.js", root/"client.js"))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("const ASSETS="+json.dumps(assets)+";\nconst CORE_CONSOLES="+json.dumps({**adapters.CONSOLES,'DuckStation':['psx']})+";\nconst COLOR_CHECKS="+json.dumps(list(color_checks.CHECKS))+";\nconst CHIP_CHECKS="+json.dumps(chips.NAMES)+";\nconst LAB="+json.dumps(registry)+";\nconst PROFILES="+json.dumps(profiles)+";\nconst PAGE="+json.dumps(page)+";\nconst CLIENT="+json.dumps(client)+";\n"+(root/"auth.js").read_text()+"\n"+(root/"worker.mjs").read_text())
