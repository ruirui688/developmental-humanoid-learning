"""Validate Y navigation links once in each changed-document phase."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote

parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=("preparation", "engineering"))
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
paths = ["README.md", "AGENTS.md", "docs/PROGRESS.md", "docs/CONTINUOUS_EXECUTION_PLAN.md",
         "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md", "docs/CONTROL_INTERFACE_ROUTE_REVIEW.md"]
if args.phase != "preparation":
    paths.append("docs/FAST_FEEDBACK_"+args.phase.upper()+"_RESULTS.md")
checks, read_bytes = [], 0
for name in paths:
    path = repo / name
    data = path.read_bytes()
    read_bytes += len(data)
    for match in re.finditer(r'!?\[[^\]]*\]\(([^\)]+)\)', data.decode("utf-8")):
        target = match.group(1).strip().split(' "')[0].strip("<>")
        if not any(key in target.lower() for key in ("fast_feedback", "control_interface_route")):
            continue
        target = unquote(target.split("#", 1)[0])
        checks.append({"source": name, "target": target, "exists": (path.parent / target).exists()})
record = {"checks": checks, "failed_checks": sum(not check["exists"] for check in checks),
          "file_reads": len(paths), "read_bytes": read_bytes, "old_links_reverified": False,
          "model_physics_or_scientific_metric_calls": 0}
with (repo / "external" / ("c4_z_"+args.phase+"_links_01.json")).open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2)
    stream.write("\n")
print(json.dumps({key: value for key, value in record.items() if key != "checks"}))
raise SystemExit(bool(record["failed_checks"]))
