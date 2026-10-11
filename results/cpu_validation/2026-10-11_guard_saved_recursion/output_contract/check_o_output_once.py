"""Finite saved-output contract only, without redoing the decomposition."""
import hashlib
import json
import math
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
root = repo / "results/cpu_validation/2026-10-11_guard_saved_recursion"
out = root / "output_contract"
if out.exists():
    raise SystemExit("first contract already exists; do not repeat it")
out.mkdir()
wall, cpu = time.perf_counter(), time.process_time()
reads, byte_count = 0, 0
def read(path):
    global reads, byte_count
    data = path.read_bytes()
    reads += 1
    byte_count += len(data)
    return data
raw_manifest = json.loads(read(root/"raw/manifest.json"))
loaded = {}
checks = []
def check(name, passed):
    checks.append({"name": name, "passed": bool(passed)})
for name, expected in raw_manifest["files"].items():
    raw = read(root/"raw"/name)
    check("payload_binding:"+name, expected == {"bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest()})
    if name.endswith(".json"):
        loaded[name] = json.loads(raw)
run, diag = loaded["run.json"], loaded["diagnostics.json"]
check("completed_clean_source", run["status"] == "completed" and run["source"]["clean_committed_bytes_verified"] is True)
check("fixed_saved_rows_and_groups", run["cost"]["record_rows_written"] == 11910 and len(diag["group_components"]) == 792 and len(diag["N_minus_K"]) == 264)
check("all_fixed_groups_complete", all(g["complete"] and g["unavailable_count"] == 0 for g in diag["group_components"]))
check("no_scientific_gate_release", all(run[k] is False and diag[k] is False for k in ("scientific_adoption", "c4_scientific_validation", "c5_scientific_dependency_released")))
check("zero_prohibited_computation", all(run["cost"][k] == 0 for k in ("physics_calls", "physics_substeps", "RLS_updates", "MPC_calls", "model_calls", "fits", "old_metric_or_gate_recalculations")))
check("finite_saved_identity_residuals", all(g["components"] is None or (math.isfinite(g["energy_identity_residual"]) and math.isfinite(g["max_point_identity_residual"])) for g in diag["group_components"]))
check("unavailable_guard_is_explicit", diag["guard_projection"] == "unavailable_not_saved")
source = read(Path(__file__))
(out/"check_o_output_once.py").write_bytes(source)
record = {"checks": checks, "check_count": len(checks), "failed": sum(not c["passed"] for c in checks),
          "file_reads": reads, "read_bytes": byte_count,
          "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu,
          "raw_manifest_sha256": hashlib.sha256((root/"raw/manifest.json").read_bytes()).hexdigest(),
          "no_scientific_recalculation": True}
# The final manifest hash read is explicitly counted separately.
record["file_reads"] += 1
record["read_bytes"] += (root/"raw/manifest.json").stat().st_size
(out/"check_01.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
print(json.dumps(record))
raise SystemExit(bool(record["failed"]))
