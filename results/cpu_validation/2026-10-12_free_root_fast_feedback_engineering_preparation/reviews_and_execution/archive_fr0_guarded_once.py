"""Guard existing FR0 archiver against empty/premature origin; no physical run."""
import json
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
origin = repo / "external/c4_fr0_engineering_01"
target = repo / "results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering"
receipt = repo / "external/fr0_archive_guard.json"
if target.exists() or receipt.exists():
    raise FileExistsError("fresh_FR0_archive_and_guard_required")
assert origin.is_dir() and (origin / "execution.json").is_file(), "finished_first_launcher_required"
data = (origin / "execution.json").read_bytes()
execution = json.loads(data)
assert type(execution.get("returncode")) is int, "finished_process_returncode_required"
assert (origin / "stdout").is_file() and (origin / "stderr").is_file(), "first_stdio_required"
missing = [name for name in ("run.json", "metrics.json", "manifest.json")
           if not (origin / "raw" / name).is_file()]
if missing and execution["returncode"] == 0:
    raise ValueError("successful_process_missing_formal_payloads:" + ",".join(missing))
with receipt.open("x", encoding="utf-8") as stream:
    json.dump({"finished_launcher_verified": True, "execution_record_reads": 1,
               "execution_record_bytes": len(data), "returncode": execution["returncode"],
               "missing_formal_payloads_preserved_for_failed_execution": missing,
               "raw_trajectory_reads": 0, "model_fit_physics_calls": 0,
               "automatic_retry": False}, stream, indent=2)
process = subprocess.run([sys.executable, str(repo / "external/archive_fr0_once.py")], cwd=repo, check=False)
raise SystemExit(process.returncode)

