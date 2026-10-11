"""Seal new KD4 checks and final pin binding; no old assembly or mathematics."""
import ast
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
target = repo / "results/cpu_validation/2026-10-12_damped_suspended_pair_engineering_preparation"
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
        raise ValueError("preparation copy mismatch")
    files[relative.as_posix()] = {**identity(data), "source": source.relative_to(repo).as_posix()}
    return data

protocol = copy(repo / "docs/DAMPED_SUSPENDED_PAIR_PROTOCOL.md", Path("source/docs/DAMPED_SUSPENDED_PAIR_PROTOCOL.md"))
runner_path = "scripts/validate_damped_suspended_pair_engineering.py"
runner = copy(repo / runner_path, Path("source") / runner_path)
tree = ast.parse(runner)
pins = [node for node in tree.body if isinstance(node, ast.Assign) and
        any(isinstance(t, ast.Name) and t.id == "PROTOCOL_PIN" for t in node.targets)]
assert len(pins) == 1 and ast.literal_eval(pins[0].value) == identity(protocol)
review = json.loads(read(repo / "external/c4_y_design_static_review.json"))
original = read(repo / "external/c4_y_feedback_checks_01/source" / runner_path)
old_tree = ast.parse(original)
for body in (tree.body, old_tree.body):
    for node in body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROTOCOL_PIN" for t in node.targets):
            node.value = ast.Constant(None)
assert ast.dump(tree, include_attributes=False) == ast.dump(old_tree, include_attributes=False)
assert review["reviewed_snapshot"][1]["sha256"] == identity(original)["sha256"]
sources = ["src/developmental_physics/damped_residual_pd_pair_mpc.py",
           "tests/test_damped_suspended_feedback.py"]
for name in sources:
    copy(repo / name, Path("source") / name)
for path in sorted((repo / "external/c4_y_feedback_checks_01").rglob("*")):
    if path.is_file():
        copy(path, Path("feedback_checks") / path.relative_to(repo / "external/c4_y_feedback_checks_01"))
for name in ("c4_y_design_static_review.json", "check_y0_once.py", "run_damped_suspended_once.py",
             "archive_damped_suspended_stage_once.py", "seal_y_preparation_once.py"):
    copy(repo / "external" / name, Path("reviews_and_execution") / name)
record = {"files": files, "final_protocol_pin_matches": True,
          "only_runner_change_since_feedback_and_static_review": "PROTOCOL_PIN",
          "feedback_tests_repeated": False, "assembly_repeated": False,
          "physics_fit_model_RLS_or_scientific_recalculation_calls": 0,
          "cost_before_manifest_write": dict(cost),
          "wall_seconds_before_manifest_write": time.perf_counter()-began,
          "cpu_seconds_before_manifest_write": time.process_time()-cpu,
          "automatic_retry": False}
data = (json.dumps(record, indent=2, allow_nan=False)+"\n").encode()
with (target / "manifest.json").open("xb") as stream:
    stream.write(data)
cost["file_writes"] += 1
cost["write_bytes"] += len(data)
print(json.dumps({"files": len(files), "cost": cost,
                  "wall_seconds": time.perf_counter()-began,
                  "cpu_seconds": time.process_time()-cpu,
                  "final_protocol_pin_matches": True, "physics_calls": 0}))
