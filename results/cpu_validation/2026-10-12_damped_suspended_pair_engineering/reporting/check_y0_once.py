"""Check first X0 bytes/telemetry and recompute only four new engineering MAEs."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import time


def main():
    repo = Path(__file__).resolve().parents[1]
    root = repo / "results/cpu_validation/2026-10-12_damped_suspended_pair_engineering"
    output = repo / "external/c4_y0_output_contract_01"
    output.mkdir(exist_ok=False)
    start, cpu = time.perf_counter(), time.process_time()
    cost = {"file_reads": 0, "read_bytes": 0, "json_parses": 0, "decompressed_bytes": 0}
    checks = []

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})

    def read(path):
        data = path.read_bytes()
        cost["file_reads"] += 1
        cost["read_bytes"] += len(data)
        return data

    def parse(data):
        cost["json_parses"] += 1
        return json.loads(data)

    manifest = parse(read(root / "raw/manifest.json"))
    loaded = {}
    for name in ("run.json", "metrics.json", "trace.jsonl.gz"):
        data = read(root / "raw" / name)
        check("payload_identity:"+name, manifest["files"][name] == {
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        loaded[name] = data
    run, metrics = (parse(loaded[name]) for name in ("run.json", "metrics.json"))
    expanded = gzip.decompress(loaded["trace.jsonl.gz"])
    cost["decompressed_bytes"] = len(expanded)
    rows = [parse(line) for line in expanded.splitlines()]
    mount = (run.get("support") or {}).get("installation") or {}

    def finite_scalar(x):
        return isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)

    def vector(x, length):
        return isinstance(x, list) and len(x) == length and all(finite_scalar(a) for a in x)

    expected_step, all_samples, confirmed, native_complete, fixed = 1, 0, 0, True, bool(mount)
    explicit_failure = run.get("failure") is not None
    for index, row in enumerate(rows):
        check("row_identity:"+str(index), row["seed"] == 7500 and row["control_index"] == index
              and row["transition_id"] == f"Y0_seed7500:{index}"
              and row["phase"] == ("prefix" if index < 100 else "active")
              and row["phase_index"] == (index if index < 100 else index-100))
        check("shared_request:"+str(index), vector(row["requested_torque"], 8)
              and max(abs(x) for x in row["requested_torque"]) <= .5
              and row["requested_torque"][2:] == [0.]*6)
        samples = (row.get("diagnostics") or row.get("saved_partial") or {}).get("substep_native_and_contact_records", [])
        if row.get("returned"):
            check("returned_sample_count:"+str(index), len(samples) == row["diagnostics"]["executed_substeps"])
            confirmed += row["diagnostics"]["executed_substeps"]
        else:
            paid = row.get("confirmed_completed_substeps", (row.get("saved_partial") or {}).get("confirmed_completed_physics_substeps", 0))
            confirmed += paid
            check("partial_samples_are_lower_bound:"+str(index), len(samples) <= paid)
        for sample in samples:
            all_samples += 1
            obs = sample.get("observation", {})
            complete = (sample["physics_step"] == expected_step
                        and finite_scalar(sample.get("time"))
                        and abs(sample["time"]-expected_step*.002) <= 1e-10
                        and vector(sample.get("applied_command8"), 8)
                        and vector(sample.get("actual_actuator_torque8"), 8)
                        and all(vector(obs.get(key), size) for key, size in (
                            ("joint_position", 8), ("joint_velocity", 8), ("imu_gyro", 3),
                            ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8)))
                        and isinstance(sample.get("floor_contacts"), list))
            native_complete &= complete
            expected_step += 1
            diagnostic = sample.get("diagnostics", {})
            fixed &= (diagnostic.get("root_position") == mount.get("fixed_torso_world_position")
                      and diagnostic.get("root_quaternion") == mount.get("fixed_torso_world_quaternion"))
            for pair in sample.get("floor_contacts", []):
                names = pair["geom_names"]
                expected_kind = ("left_arm" if any(name in ("left_upper_arm_geom", "left_forearm_geom") for name in names)
                                 else "feet" if any(name in ("left_foot_geom", "right_foot_geom") for name in names)
                                 else "other")
                contact_finite = finite_scalar(pair["normal_force_n"]) and finite_scalar(pair["distance_m"])
                native_complete &= contact_finite
                check("contact_finite_and_class:"+str(all_samples), contact_finite
                      and pair["contact_class"] == expected_kind and "floor" in names)
    full = (len(rows) == 300 and all_samples == 3000 and native_complete
            and all(row.get("returned") is True and row["diagnostics"].get("executed_substeps") == 10
                    and row.get("environment_terminated") is False and row.get("study_abort") is None for row in rows))
    check("structural_full", metrics.get("full_100_prefix_200_active") == full or
          ("full_100_prefix_200_active" not in metrics and explicit_failure))
    check("paid_return_count", run["cost"]["control_call_returns"] == sum(row.get("returned") is True for row in rows))
    check("paid_substeps", run["cost"]["confirmed_physics_substeps"] == confirmed and all_samples <= confirmed)
    check("observed_mount", metrics.get("fixed_upright_mount_observed_all_3000_substeps") == (fixed and all_samples == 3000)
          or ("fixed_upright_mount_observed_all_3000_substeps" not in metrics and explicit_failure))
    check("upright_identity", not mount or mount["fixed_torso_world_quaternion"] == [1., 0., 0., 0.])
    maes, windows_passed, mae_count = [], True, 0
    windows = metrics.get("last20_post_step_windows")
    missing_failed_windows = windows is None and explicit_failure
    check("two_windows_or_explicit_reporting_failure", missing_failed_windows or isinstance(windows, list) and len(windows) == 2)
    if missing_failed_windows:
        windows_passed = False
    for window, (lower, upper) in zip(windows or (), ((80, 100), (180, 200))):
        selected = [row for row in rows if row["phase"] == "active" and lower <= row["phase_index"] < upper]
        available = full and len(selected) == 20 and all(vector(row.get("target_error_rad"), 2) for row in selected)
        mae = [sum(abs(row["target_error_rad"][i]) for row in selected)/20 for i in range(2)] if available else None
        # Independently bind errors to native after state and each row's current target.
        check("native_target_errors:"+str(lower), not available or all(
            row["target_error_rad"] == [row["observation_after"]["joint_position"][i]-row["current_target_q2"][i] for i in range(2)] for row in selected))
        check("window_availability:"+str(lower), window["available"] == available and window["observed_count"] == len(selected))
        check("frozen_window:"+str(lower), window["active_indices"] == [lower, upper-1] and window["planned_count"] == 20
              and window["full_trial_required"] is True and window["threshold_rad"] == .01)
        check("window_MAE:"+str(lower), window["per_axis_mae_rad"] is None if mae is None else
              vector(window["per_axis_mae_rad"], 2) and all(abs(a-b) <= 1e-12 for a, b in zip(window["per_axis_mae_rad"], mae)))
        passed = available and all(x <= .01 for x in mae)
        check("window_pass:"+str(lower), window["passed"] == passed)
        windows_passed &= passed
        maes.append(mae)
        mae_count += 2*available
    qualified = full and fixed and windows_passed and isinstance(windows, list) and len(windows) == 2 and not explicit_failure
    check("new_engineering_gate", run["engineering_qualification_passed"] == metrics["engineering_qualification_passed"] == qualified)
    check("noncontact_gate", metrics.get("contact_required_for_pass") is False or
          ("contact_required_for_pass" not in metrics and explicit_failure))
    check("new_calls_clean", not all_samples or run["source"]["clean_committed_bytes_verified"] is True)
    before, after = run.get("physical_fingerprint_before"), run.get("physical_fingerprint_after")
    check("parameter_unchanged_or_unavailable_failure", (before is not None and after is not None and before == after)
          or (explicit_failure and (before is None or after is None)))
    for flag in ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation", "c5_scientific_dependency_released",
                 "c4_contact_scientific_validation"):
        check(flag, run[flag] is False and metrics[flag] is False)
    result = {"checks": checks, "failed_checks": sum(not check["passed"] for check in checks),
              "records": len(rows), "confirmed_substeps": confirmed, "retained_substep_samples": all_samples, "full": full,
              "engineering_qualification_passed": qualified, "independent_MAE_rad": maes,
              "new_engineering_MAE_recalculations": mae_count,
              "new_engineering_gate_verifications": 1, "old_scientific_metric_recalculations": 0,
              "model_physics_RLS_calls": 0, "cost": cost,
              "wall_seconds": time.perf_counter()-start, "cpu_seconds": time.process_time()-cpu}
    (output / "report.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    (output / "checker.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}))
    raise SystemExit(bool(result["failed_checks"]))


if __name__ == "__main__":
    main()
