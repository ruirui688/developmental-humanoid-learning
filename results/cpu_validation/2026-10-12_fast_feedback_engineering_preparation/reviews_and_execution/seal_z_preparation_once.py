"""Seal new interface checks, source and narrow receipts once; no old assembly."""
import ast
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
target = repo / "results/cpu_validation/2026-10-12_fast_feedback_engineering_preparation"
target.mkdir(exist_ok=False)
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
def copy(source, relative):
    data = read(source)
    dest = target / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as stream:
        stream.write(data)
    cost["file_writes"] += 1
    cost["write_bytes"] += len(data)
    if read(dest) != data:
        raise ValueError("Z preparation copy mismatch")
    files[relative.as_posix()] = {**identity(data), "source": source.relative_to(repo).as_posix()}
    return data

protocol = copy(repo / "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md", Path("source/docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"))
runner = copy(repo / "scripts/validate_fast_feedback_engineering.py", Path("source/scripts/validate_fast_feedback_engineering.py"))
tree = ast.parse(runner)
pin = [node for node in tree.body if isinstance(node, ast.Assign) and
       any(isinstance(t, ast.Name) and t.id == "PROTOCOL_PIN" for t in node.targets)]
assert len(pin) == 1 and ast.literal_eval(pin[0].value) == identity(protocol)
checks = repo / "external/c4_z_interface_checks_01"
record = json.loads(read(checks / "execution.json"))
assert record["returncode"] == 0
for name in ("src/developmental_physics/fast_feedback_environment.py",
             "tests/test_fast_feedback_environment.py", "tests/test_fast_feedback_engineering.py",
             "docs/CONTROL_INTERFACE_ROUTE_REVIEW.md"):
    data = copy(repo / name, Path("source") / name)
    if name in record["source_files"]:
        assert identity(data) == record["source_files"][name]
assert identity(runner) == record["source_files"]["scripts/validate_fast_feedback_engineering.py"]
for path in sorted(checks.rglob("*")):
    if path.is_file():
        copy(path, Path("interface_checks") / path.relative_to(checks))
for name in ("c4_z_design_static_review.json", "fast_feedback_interface_preparation.json", "c4_z_runner_derivation.json",
             "prepare_fast_runner_once.py", "prepare_z_helpers_once.py", "run_z_checks_once.py",
             "run_fast_feedback_once.py", "archive_fast_feedback_stage_once.py", "check_z0_once.py",
             "read_fast_feedback_reporting_once.py", "check_fast_feedback_links_once.py",
             "seal_fast_reporting_once.py", "seal_z_preparation_once.py"):
    copy(repo / "external" / name, Path("reviews_and_execution") / name)
record = {"files": files, "final_protocol_pin_matches": True, "first_new_checks_passed": True,
          "physics_fit_model_RLS_or_scientific_recalculation_calls": 0,
          "assembly_repeated": False, "old_tests_repeated": False,
          "cost_before_manifest_write": dict(cost), "automatic_retry": False,
          "wall_seconds_before_manifest_write": time.perf_counter()-began,
          "cpu_seconds_before_manifest_write": time.process_time()-cpu}
data = (json.dumps(record, indent=2, allow_nan=False)+"\n").encode()
with (target / "manifest.json").open("xb") as stream:
    stream.write(data)
cost["file_writes"] += 1
cost["write_bytes"] += len(data)
print(json.dumps({"files": len(files), "cost": cost, "wall_seconds": time.perf_counter()-began,
                  "cpu_seconds": time.process_time()-cpu, "physics_calls": 0}))
