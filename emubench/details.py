import json
from pathlib import Path


def timeline(times):
    # Keep at least eight frames per bin wherever possible, and show the true
    # worst frame in every bin. The x-axis is elapsed host time, in milliseconds.
    width = max(8, (len(times) + 119) // 120)
    elapsed = 0
    bins = []
    for offset in range(0, len(times), width):
        group = times[offset:offset + width]
        duration = sum(group)
        peak = max(group)
        worst = group.index(peak)
        bins.append({"start_ms": round(elapsed / 1e6, 6), "end_ms": round((elapsed + duration) / 1e6, 6),
                     "avg_fps": round(1e9 * len(group) / duration),
                     "worst_fps": round(1e9 / peak), "worst_ms": round(peak / 1e6, 6),
                     "worst_frame": offset + worst + 1,
                     "worst_at_ms": round((elapsed + sum(group[:worst + 1])) / 1e6, 6)})
        elapsed += duration
    return bins


def template_html():
    root = Path(__file__).parent
    return (root / "report.html").read_text(encoding="utf-8").replace(
        "/* CHART_JS */", (root / "chart.js").read_text(encoding="utf-8"))


def write_report(result, public, destination):
    data = {**public, "game": result.get("local_name", "Personal GBA ROM"),
            "when": result.get("started_utc", ""), "finished": result.get("finished_utc", "")}
    template = template_html()
    # Embedded JSON is data, including any locally supplied filename.
    safe_json = json.dumps(data, ensure_ascii=True).replace("<", r"\u003c").replace(">", r"\u003e")
    html = template.replace('id="run-data"></script>', 'id="run-data">' + safe_json + '</script>', 1)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as f:
        f.write(html)
    return destination.resolve()
