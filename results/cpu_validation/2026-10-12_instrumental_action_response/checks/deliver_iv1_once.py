"""Copy and check the first IV1 payload; no trace decoding or model mathematics."""
from pathlib import Path
import hashlib
import io
import json
import struct
import subprocess
import time
import zipfile

repo = Path(__file__).resolve().parents[1]
source = repo / "external/iv1_action_response_first/raw"
dest = repo / "results/cpu_validation/2026-10-12_instrumental_action_response"
assert not dest.exists(), "first delivery directory required"
dest.mkdir()
(dest / "raw").mkdir()
wall, cpu = time.perf_counter(), time.process_time()
cost = {"files_read": 0, "bytes_read": 0, "files_written": 0, "bytes_written": 0}
blobs, identities, checks = {}, {}, []

def ident(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}

def save(path, blob):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        assert stream.write(blob) == len(blob)
    cost["files_written"] += 1
    cost["bytes_written"] += len(blob)

for path in sorted(source.iterdir()):
    assert path.is_file()
    blob = path.read_bytes()
    cost["files_read"] += 1
    cost["bytes_read"] += len(blob)
    blobs[path.name] = blob
    save(dest / "raw" / path.name, blob)
    identities["raw/" + path.name] = ident(blob)

def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)

failure = None
try:
    run = json.loads(blobs["run.json"])
    models = json.loads(blobs["models.json"])
    moments = json.loads(blobs["moments.json"])
    metrics = json.loads(blobs["metrics.json"])
    check("first_complete_without_exception", run["status"] == "completed" and run["first_failure"] is None)
    check("metrics_bound_to_run", metrics == run["metrics"])
    check("actual_physics_and_label_counts", all(run["cost"][k] == n for k, n in {
        "total_control_returns": 15000, "confirmed_physics_substeps": 15000,
        "identification_control_returns": 9000, "prediction_control_returns": 6000,
        "new_IV_scalar_label_uses": 12000, "IV_fit_returns": 3,
        "IV_fitted_coefficient_scalar_outputs": 24, "pair_prediction_returns": 187020}.items()))
    check("six_complete_trial_slots", len(run["trials"]) == 6 and all(
        t["status"] == "completed" and t["contact_qualification"]["passed"] for t in run["trials"]))
    expected = {(seed, name, h, origin) for seed in (8101, 8102, 8103)
        for name in ("cold", "oldlearned", "corrected") for h in (1, 10, 20, 50, 150)
        for origin in range(0, 1000-h+1, 10)}
    actual = {(p["seed"], p["model"], p["horizon"], p["origin_active_index"])
        for p in run["complete_prediction_population"]}
    check("all_4329_fixed_predictions_retained", len(run["complete_prediction_population"]) == len(expected)
        and actual == expected and all(p["status"] == "completed" and p["available"] for p in run["complete_prediction_population"]))
    for seed in ("8101", "8102", "8103"):
        check(seed + "_saved_fit_contract", moments[seed]["samples"] == 2000 and moments[seed]["fit"]["rank"] == 4)
        old, corrected = models[seed]["oldlearned"]["coefficients"], models[seed]["corrected"]["coefficients"]
        columns = (0, 1, 2, 3, 8)
        check(seed + "_ten_nonaction_coefficients_bitwise_retained",
            struct.pack("<10d", *(r[c] for r in old for c in columns)) ==
            struct.pack("<10d", *(r[c] for r in corrected for c in columns)))
        check(seed + "_saved_parameter_fingerprints_unchanged", all(
            m["parameter_fingerprint"] == m["fingerprint_before_prediction"] for m in models[seed].values()))
    flags = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
        "c4_contact_scientific_validation", "c5_scientific_dependency_released")
    check("science_flags_false_and_no_control", all(run[k] is False for k in flags) and run["control_candidate_opened"] is False)
    check("native_label_boundary", run["fork_label_uses"] == run["opaque_state_uses"] == run["RLS_updates"] == 0)
    with zipfile.ZipFile(io.BytesIO(blobs["source.zip"])) as archive:
        check("source_zip_complete_closure", set(archive.namelist()) == set(run["source"]["files"]))
        for name in archive.namelist():
            blob = archive.read(name)
            committed = subprocess.run(["git", "show", run["source"]["commit"] + ":" + name],
                cwd=repo, check=True, capture_output=True).stdout
            cost["zip_decoded_bytes_read"] = cost.get("zip_decoded_bytes_read", 0) + len(blob)
            cost["git_blob_bytes_read"] = cost.get("git_blob_bytes_read", 0) + len(committed)
            check("source_" + name, blob == committed and ident(blob) == run["source"]["files"][name])
except Exception as exc:
    failure = {"type": type(exc).__name__, "message": str(exc)}

self_blob = Path(__file__).read_bytes()
cost["files_read"] += 1
cost["bytes_read"] += len(self_blob)
save(dest / "checks/deliver_iv1_once.py", self_blob)
report = {"status": "failed" if failure else "passed", "checks": checks, "first_failure": failure,
    "payload": identities, "IO_before_report": dict(cost),
    "physics_calls": 0, "model_calls": 0, "fit_calls": 0, "trace_decode_calls": 0,
    "science_gate_reexecuted": False, "continuous_goal": "active",
    "cumulative_physics": {"controls": 529345, "substeps": 2809018},
    "historical_RLS_scalar_updates": 125652, "new_IV_scalar_label_uses": 12000,
    "new_IV_fits": 3, "new_fitted_action_coefficients": 24,
    "wall_seconds_before_report": time.perf_counter()-wall,
    "cpu_seconds_before_report": time.process_time()-cpu,
    "unmeasured_filesystem_internal_IO": "unknown_not_zero"}
save(dest / "delivery_checks.json", (json.dumps(report, ensure_ascii=False, indent=2)+"\n").encode())
print(json.dumps({"status": report["status"], "checks": len(checks), "failure": failure, "actual_IO": cost}))
raise SystemExit(1 if failure else 0)
