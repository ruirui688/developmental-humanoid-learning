"""Preserve source originals and run only the three small new-tail fixtures."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


staging = Path(__file__).resolve().parent
root = staging.parents[1]
output = staging / "engineering_01"
output.mkdir(exist_ok=False)
paths = [
    staging/"pd_tail_pair_mpc.py", staging/"check_pd_tail_new_branches.py", Path(__file__).resolve(),
    root/"src/developmental_physics/__init__.py",
    root/"src/developmental_physics/guard_lag_pair_mpc.py",
    root/"src/developmental_physics/guard_lag_pair_model.py",
    root/"src/developmental_physics/guard_pair_model.py",
    root/"src/developmental_physics/local_model.py",
    root/"src/developmental_physics/local_pair_model.py",
]
source_records = []
for path in paths:
    content = path.read_bytes()
    relative = path.relative_to(root).as_posix()
    target = output/"source_snapshot"/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    source_records.append({"path": relative, "bytes": len(content),
                           "sha256": hashlib.sha256(content).hexdigest()})
source_bytes = sum(x["bytes"] for x in source_records)
git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True)
environment = os.environ.copy()
environment["PYTHONPATH"] = str(root/"src")
started_wall, started_cpu = time.perf_counter(), time.process_time()
with (output/"stdout.txt").open("wb") as stdout, (output/"stderr.txt").open("wb") as stderr:
    completed = subprocess.run([sys.executable, str(staging/"check_pd_tail_new_branches.py")],
        cwd=root, env=environment, stdout=stdout, stderr=stderr)
wall, cpu = time.perf_counter()-started_wall, time.process_time()-started_cpu
stdout_bytes = (output/"stdout.txt").read_bytes()
try:
    returned = json.loads(stdout_bytes)
except (UnicodeError, json.JSONDecodeError):
    returned = None
record = {
    "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "git_HEAD": git.stdout.strip(), "source_status": "unselected engineering draft; snapshot before first new-tail fixture",
    "candidate_selected": False, "formal_experiment_enabled": False,
    "python_executable": sys.executable, "exit_code": completed.returncode,
    "wrapper_wall_seconds": wall, "wrapper_cpu_seconds_excluding_child": cpu,
    "source_snapshot_files": source_records,
    "explicit_source_snapshot_read_bytes": source_bytes,
    "saved_stdout_read_bytes": len(stdout_bytes),
    "explicit_wrapper_read_bytes": source_bytes+len(stdout_bytes),
    "read_cost_scope": "explicit source snapshots/hash pass and one saved stdout JSON projection; imports are not disk-I/O measured",
    "child_report": returned,
    "cost_exclusions": "module/package import I/O and interpreter startup compute are not zero; wrapper wall includes child startup",
    "physics_steps": 0, "E_C_D_archive_reads": 0, "fits": 0, "old_fixture_runs": 0,
}
(output/"run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"output": str(output), "exit_code": completed.returncode,
                  "check_count": returned.get("check_count") if returned else None,
                  "failed": returned.get("failed") if returned else None,
                  "child_cost": returned.get("cost") if returned else None,
                  "child_execution": returned.get("execution") if returned else None,
                  "wrapper_wall_seconds": wall,
                  "explicit_wrapper_read_bytes": record["explicit_wrapper_read_bytes"]}, ensure_ascii=False))
raise SystemExit(completed.returncode)
