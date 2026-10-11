"""Seal first reporting attachments beside immutable X/Y raw manifests."""
import argparse
import hashlib
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser()
parser.add_argument("prefix", choices=("x0", "y0"))
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
domain = "suspended_pair" if args.prefix == "x0" else "damped_suspended_pair"
root = repo / "results/cpu_validation" / ("2026-10-12_"+domain+"_engineering")
output = root / "reporting"
output.mkdir(exist_ok=False)
began, cpu = time.perf_counter(), time.process_time()
cost = {"file_reads": 0, "read_bytes": 0, "file_writes": 0, "write_bytes": 0}
files = {}

def read(path):
    data = path.read_bytes()
    cost["file_reads"] += 1
    cost["read_bytes"] += len(data)
    return data

def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def bind_base():
    return {name: identity(read(root / name)) for name in ("manifest.json", "raw/manifest.json")}

before = bind_base()
names = [f"c4_{args.prefix}_reporting_summary.json", f"c4_{args.prefix}_reporting_reads.json",
         f"check_{args.prefix}_once.py", "seal_suspended_reporting_once.py"]
if args.prefix == "x0":
    names += ["c4_x_engineering_links_01.json", "check_suspended_links_once.py",
              "read_suspended_reporting_once.py"]
else:
    names += ["c4_y_engineering_links_01.json", "check_damped_suspended_links_once.py",
              "read_damped_suspended_reporting_once.py"]
sources = [(repo / "external" / name, Path(name)) for name in names]
contract = repo / "external" / f"c4_{args.prefix}_output_contract_01"
sources += [(path, Path("output_contract") / path.relative_to(contract)) for path in sorted(contract.rglob("*")) if path.is_file()]
for source, relative in sources:
    if source.is_symlink() or not source.is_file():
        raise ValueError("regular reporting attachment required")
    data = read(source)
    dest = output / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as stream:
        stream.write(data)
    cost["file_writes"] += 1
    cost["write_bytes"] += len(data)
    if read(dest) != data:
        raise ValueError("attachment copy mismatch")
    files[relative.as_posix()] = {**identity(data), "source": source.relative_to(repo).as_posix()}
after = bind_base()
if before != after:
    raise ValueError("raw/root manifest changed")
record = {"files": files, "base_manifests": before, "base_manifests_after": after,
          "root_raw_manifests_unchanged": True, "cost_before_manifest_write": dict(cost),
          "wall_seconds_before_manifest_write": time.perf_counter()-began,
          "cpu_seconds_before_manifest_write": time.process_time()-cpu,
          "model_physics_scientific_metric_or_checker_calls": 0, "automatic_retry": False}
data = (json.dumps(record, indent=2, allow_nan=False)+"\n").encode()
with (output / "reporting_manifest.json").open("xb") as stream:
    stream.write(data)
cost["file_writes"] += 1
cost["write_bytes"] += len(data)
print(json.dumps({"cost": cost, "wall_seconds": time.perf_counter()-began,
                  "cpu_seconds": time.process_time()-cpu, "root_raw_manifests_unchanged": True}))
