"""Freeze IV1 preparation after first necessary checks; never run physics."""
from pathlib import Path
import hashlib
import json
import time

repo = Path(__file__).resolve().parents[1]
dest = repo / "results/cpu_validation/2026-10-12_instrumental_action_response_preparation"
assert not dest.exists(), "first preparation destination required"
wall, cpu = time.perf_counter(), time.process_time()
paths = ["docs/INSTRUMENTAL_ACTION_RESPONSE_PROTOCOL.md",
         "src/developmental_physics/instrumental_action_model.py",
         "scripts/develop_instrumental_action_response.py",
         "external/new_iv_action_checks_once.py",
         "external/freeze_iv1_preparation_once.py"]
blobs = {name: (repo / name).read_bytes() for name in paths}
for path in sorted((repo / "external/iv1_new_checks_first").iterdir()):
    if path.is_file():
        blobs[path.relative_to(repo).as_posix()] = path.read_bytes()
checks = json.loads(blobs["external/iv1_new_checks_first/checks.json"])
assert checks["status"] == "passed" and checks.get("first_failure") is None
assert checks["checks"] and all(c["passed"] for c in checks["checks"])

def ident(b):
    return {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}

for name in paths[:4]:
    found = [value for path, value in checks["source_identities"].items()
             if Path(path).resolve() == (repo / name).resolve()]
    # Checks pin executable sources; protocol is separately pinned by runner.
    if name.endswith(".py") and name != paths[-1]:
        assert found == [ident(blobs[name])], name

dest.mkdir(parents=True, exist_ok=False)
files = {}
for name, blob in blobs.items():
    path = dest / "inputs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(blob)
    files[path.relative_to(dest).as_posix()] = ident(blob)
manifest = {"experiment": "IV1", "status": "preparation_frozen", "files": files,
    "new_checks": {"status": "passed", "count": len(checks["checks"])},
    "new_check_cost": checks.get("cost", checks.get("synthetic_only_cost")),
    "historical_RLS_scalar_updates": 125652,
    "historical_controls": 514345, "historical_substeps": 2794018,
    "preparation_physics": 0, "preparation_fit": 0,
    "file_copy_IO": {"files_read": len(blobs), "files_written": len(blobs),
                     "bytes_read": sum(map(len, blobs.values())), "bytes_written": sum(map(len, blobs.values()))},
    "wall_seconds_before_manifest": time.perf_counter()-wall,
    "cpu_seconds_before_manifest": time.process_time()-cpu,
    "unmeasured_internal_IO": "unknown_not_zero", "continuous_goal": "active"}
with (dest / "manifest.json").open("x", encoding="utf-8") as f:
    f.write(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
print(json.dumps({"status": "preparation_frozen", "files": len(files)}))
