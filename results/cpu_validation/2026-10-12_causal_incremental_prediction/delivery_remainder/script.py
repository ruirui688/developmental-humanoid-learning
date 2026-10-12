"""Finish only CF1 delivery checks not reached after a wrong source argument."""
from pathlib import Path
import hashlib
import json
import subprocess
import zipfile

repo = Path(r"D:\Codex_ws\robot_rl")
output = repo / "results/cpu_validation/2026-10-12_causal_incremental_prediction"
raw = output / "raw"
remainder = output / "delivery_remainder"
remainder.mkdir(exist_ok=False)
actual_commit = "bb7e4b8fa744b4ec7c76855cfe6730ebbca26421"
wrong_commit = "bb7e4b8e0000000000000000000000000000000000"
first = json.loads((output / "delivery_checks.json").read_bytes())
if first["status"] != "failed" or len(first["checks"]) != 12 or not all(x["passed"] for x in first["checks"][1:]):
    raise ValueError("preserve expected first partial delivery rather than replace evidence")
(output / "first_delivery_script.py").write_bytes((repo / "external/deliver_cf1_once.py").read_bytes())
(output / "first_delivery_error.json").write_text(json.dumps({"type": "CalledProcessError", "returncode": 128,
    "failed_command": ["git", "show", wrong_commit+":scripts/develop_causal_incremental_prediction.py"],
    "source_argument_error": {"supplied": wrong_commit, "actual_frozen": actual_commit},
    "first_saved_checks": 12, "first_failed_check": "CF1_identity_and_clean_first_source",
    "first_passed_checks": 11, "experiment_reexecuted": False, "prediction_gate": False,
    "remediation": "only wrong-argument source identity and previously unreached checks; no passed check or mathematics repeated"}, indent=2)+"\n", encoding="utf-8")
run = json.loads((raw / "run.json").read_bytes())
old = json.loads((raw / "old_scores_transcribed.json").read_bytes())
checks = []

def seal():
    (remainder / "checks.json").write_text(json.dumps({"status": "passed" if checks and all(c["passed"] for c in checks) else "failed",
        "checks": checks, "first_error_preserved": True, "prior_passed_checks_repeated": 0,
        "new_physics_fit_model_RMSE_gate_recomputations": 0, "raw_prediction_decodes": 0}, indent=2)+"\n", encoding="utf-8")

def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    seal()

check("corrected_source_argument_identity", run["source"]["commit"] == actual_commit and run["source"]["clean_committed_bytes_verified"] is True)
with zipfile.ZipFile(raw / "source.zip") as archive:
    for name in archive.namelist():
        committed = subprocess.run(["git", "show", actual_commit+":"+name], cwd=repo, capture_output=True, check=True).stdout
        check("previously_unreached_source_archive_identity:"+name, archive.read(name) == committed)
old_source = json.loads((repo / "results/cpu_validation/2026-10-12_near_reference_identification/raw/run.json").read_bytes())
check("unreached_old_metrics_transcription", old["old_metrics_transcribed_not_recomputed"] == old_source["metrics"])
for seed in (8101, 8102, 8103):
    saved = next(s for s in old_source["seed_results"] if s["seed"] == seed)["prediction_scores"]
    check("unreached_old_score_transcription:"+str(seed), old[str(seed)] == saved)

def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}

(remainder / "script.py").write_bytes(Path(__file__).read_bytes())
(output / "delivery_manifest.json").write_text(json.dumps({"status": "completed_after_source_argument_error",
    "source_commit": actual_commit, "first_delivery_failure_preserved": True,
    "first_saved": {"passed": 11, "failed_wrong_source_argument": 1},
    "unreached_and_corrected_checks": len(checks), "remainder_all_passed": all(x["passed"] for x in checks),
    "raw_payload": {path.name: identity(path.read_bytes()) for path in sorted(raw.iterdir())},
    "physics_fit_model_RMSE_gate_recomputations": 0, "prediction_raw_decodes": 0,
    "prior_passed_checks_repeated": 0, "unmeasured_IO_internal_work": "unknown_not_zero"}, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"first_passed_preserved": 11, "first_failed_preserved": 1, "unreached_or_corrected": len(checks), "remainder_passed": all(c["passed"] for c in checks)}))
if not all(c["passed"] for c in checks):
    raise SystemExit(1)
