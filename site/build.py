"""Bundle the native Sites worker with the exact protocol constants used by the CLI."""
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root.parent))
from emubench import carter, circuit

out = Path(sys.argv[1])
profiles = {s.profile: dict(console=s.console, title=s.title, description=s.description, warmup=s.warmup,
                            frames=m.FRAMES, references=s.references) for m in (carter, circuit) for s in m.SCENES}
page = (root / "index.html").read_text()
for tag, name in (("__EMU__", "emu-bench-wordmark"), ("__CARTS__", "carts-wordmark")):
    page = page.replace(tag, (root / "assets" / (name + ".svg")).read_text())
client = "\n".join(p.read_text() for p in (root.parent / "emubench/chart.js", root/"analysis.js", root/"demo.js", root/"client.js"))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("const PROFILES="+json.dumps(profiles)+";\nconst PAGE="+json.dumps(page)+";\nconst CLIENT="+json.dumps(client)+";\n"+(root/"worker.mjs").read_text())
