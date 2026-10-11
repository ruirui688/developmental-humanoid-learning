"""Archive a bounded X stage exactly once; copy bytes, never rerun experiments."""
import argparse
import hashlib
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser()
parser.add_argument("stage", choices=("assembly", "engineering", "prediction", "control"))
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
stages = {
    "assembly": ("c4_x0_assembly_01", "suspended_pair_engineering_preparation"),
    "engineering": ("c4_x0_engineering_01", "suspended_pair_engineering"),
    "prediction": ("c4_x1_prediction_01", "suspended_pair_prediction"),
    "control": ("c4_x2_control_01", "suspended_pair_control"),
}
origin, name = stages[args.stage]
source = repo / "external" / origin
target = repo / "results/cpu_validation" / ("2026-10-12_" + name)
target.mkdir(exist_ok=False)
began, cpu = time.perf_counter(), time.process_time()
cost = {"file_reads": 0, "read_bytes": 0, "file_writes": 0, "write_bytes": 0}
files = {}

def read(path):
    data = path.read_bytes()
    cost["file_reads"] += 1
    cost["read_bytes"] += len(data)
    return data

def copy(path, relative):
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular stage file required: " + str(path))
    data = read(path)
    dest = target / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as stream:
        stream.write(data)
    cost["file_writes"] += 1
    cost["write_bytes"] += len(data)
    if read(dest) != data:
        raise ValueError("stage copy mismatch: " + str(path))
    files[relative.as_posix()] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                "source": path.relative_to(repo).as_posix()}

if source.is_symlink() or not source.is_dir():
    raise ValueError("regular first-stage output directory required")
for path in sorted(source.rglob("*")):
    if path.is_file():
        copy(path, path.relative_to(source))
for name in ("run_suspended_once.py", "archive_suspended_stage_once.py"):
    copy(repo / "external" / name, Path("execution") / name)
if args.stage == "assembly":
    for name in ("c4_x0_static_review.json", "c4_x_residual_controller_static_review.json",
                 "c4_x0_output_checker_static_review.json"):
        copy(repo / "external" / name, Path("reviews") / name)
    copy(repo / "external/check_x0_once.py", Path("checks/check_x0_once.py"))
    copy(repo / "external/c4_x0_assembly_reporting_summary.json", Path("reporting/assembly_summary.json"))
    checks = repo / "external/c4_x_pd_count_checks_01"
    for path in sorted(checks.rglob("*")):
        if path.is_file():
            copy(path, Path("controller_checks") / path.relative_to(checks))
record = {"status": "archived", "stage": args.stage, "files": files,
          "cost_before_manifest_write": dict(cost),
          "wall_seconds_before_manifest_write": time.perf_counter()-began,
          "cpu_seconds_before_manifest_write": time.process_time()-cpu,
          "physics_model_or_scientific_metric_calls": 0, "automatic_retry": False}
data = (json.dumps(record, indent=2, allow_nan=False)+"\n").encode()
with (target / "manifest.json").open("xb") as stream:
    stream.write(data)
cost["file_writes"] += 1
cost["write_bytes"] += len(data)
print(json.dumps({"target": target.relative_to(repo).as_posix(), "files": len(files), "cost": cost,
                  "wall_seconds": time.perf_counter()-began, "cpu_seconds": time.process_time()-cpu,
                  "automatic_retry": False}))
