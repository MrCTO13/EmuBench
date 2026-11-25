"""Bundle the native Sites worker with the exact protocol constants used by the CLI."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))
from emubench import adapters, carter, chips, circuit, color_checks, lab

out = Path(sys.argv[1])
profiles = {s.profile: dict(console=s.console, title=s.title, description=s.description, warmup=s.warmup,
                            frames=m.FRAMES, references=s.references) for m in (carter, circuit) for s in m.PROFILES.values()}
page = (root / "index.html").read_text()
page = page.replace("__EMU__", (root / "assets/emu-bench-wordmark.svg").read_text())
registry = {"studies":lab.studies(),"receipts":[]}
for path in sorted((root/"reviewed").glob("*.json")):
    receipt=json.loads(path.read_text())
    lab.validate_receipt(registry["studies"],receipt)
    registry["receipts"].append(receipt)
client = "const CORE_CONSOLES="+json.dumps(adapters.CONSOLES)+";\nconst LAB="+json.dumps(registry)+";\n"+"\n".join(p.read_text() for p in (root.parent / "emubench/chart.js", root/"analysis.js", root/"lab.js", root/"demo.js", root/"library.js", root/"client.js"))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("const CORE_CONSOLES="+json.dumps(adapters.CONSOLES)+";\nconst COLOR_CHECKS="+json.dumps(list(color_checks.CHECKS))+";\nconst CHIP_CHECKS="+json.dumps(chips.NAMES)+";\nconst LAB="+json.dumps(registry)+";\nconst PROFILES="+json.dumps(profiles)+";\nconst PAGE="+json.dumps(page)+";\nconst CLIENT="+json.dumps(client)+";\n"+(root/"auth.js").read_text()+"\n"+(root/"worker.mjs").read_text())
