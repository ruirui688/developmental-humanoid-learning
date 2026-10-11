"""Read saved X-stage reporting values once; never predict, fit, or integrate."""
import argparse
import hashlib
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser()
parser.add_argument("stage", choices=("engineering", "prediction", "control"))
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
stage = {"engineering": ("y0", "damped_suspended_pair_engineering"),
         "prediction": ("y1", "damped_suspended_pair_prediction"),
         "control": ("y2", "damped_suspended_pair_control")}[args.stage]
prefix, suffix = stage
root = repo / "results/cpu_validation" / ("2026-10-12_"+suffix)
began, cpu = time.perf_counter(), time.process_time()
data, reads = {}, []
for name in ("raw/run.json", "raw/metrics.json", "raw/manifest.json", "manifest.json", "execution.json"):
    raw = (root / name).read_bytes()
    reads.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    data[name] = json.loads(raw)
record = {"reads": reads, "file_reads": len(reads), "read_bytes": sum(row["bytes"] for row in reads),
          "json_parses": len(reads), "wall_seconds": time.perf_counter()-began,
          "cpu_seconds": time.process_time()-cpu, "scientific_recalculation": False}
summary = {"run": data["raw/run.json"], "metrics": data["raw/metrics.json"],
           "raw_manifest": data["raw/manifest.json"], "archive": data["manifest.json"],
           "execution": data["execution.json"], "report_reads": record}
for name, value in ((f"c4_{prefix}_reporting_reads.json", record),
                    (f"c4_{prefix}_reporting_summary.json", summary)):
    with (repo / "external" / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
print(json.dumps({"stage": args.stage, "report_reads": record,
                  "status": summary["run"]["status"],
                  "metric_flags": {key: value for key, value in summary["metrics"].items()
                                   if not isinstance(value, (dict, list))},
                  "windows": summary["metrics"].get("last20_post_step_windows")}, ensure_ascii=False))
