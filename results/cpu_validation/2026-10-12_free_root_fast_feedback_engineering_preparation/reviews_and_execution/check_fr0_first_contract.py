"""Check three saved FR0 JSON contracts once; no traces, source reads or recomputation."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

FLAGS = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
         "c4_contact_scientific_validation", "c5_scientific_dependency_released")
ZERO = ("model_calls", "model_restores", "fit_calls", "RLS_updates", "MPC_decisions",
        "teacher_calls", "task_policy_updates", "GPU_training_seconds")
PHASES = ("prefix", "target_A", "target_B")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    wall, cpu = time.perf_counter(), time.process_time()
    errors, saved, identities = [], {}, {}
    reads = read_bytes = checks = 0

    def require(condition, name):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(name)

    def integer(value):
        return type(value) is int and value >= 0

    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    def vector(value):
        return isinstance(value, list) and len(value) == 2 and all(finite(x) and x >= 0 for x in value)

    for name in ("run.json", "metrics.json", "manifest.json"):
        try:
            data = (args.raw / name).read_bytes()
            reads += 1
            read_bytes += len(data)
            identities[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            saved[name] = json.loads(data)
            require(isinstance(saved[name], dict), name + ":object")
        except (OSError, ValueError) as exc:
            errors.append(name + ":" + type(exc).__name__ + ":" + str(exc))

    if len(saved) == 3 and all(isinstance(x, dict) for x in saved.values()):
        run, metrics, manifest = (saved[name] for name in ("run.json", "metrics.json", "manifest.json"))
        for name, value in saved.items():
            require(all(value.get(key) is False for key in FLAGS), name + ":all_scientific_flags_false")
        for name, value in (("run", run), ("manifest", manifest)):
            require(value.get("schema_version") == 1 and value.get("experiment_id") == "FR0"
                    and value.get("stage") == "free_root_fast_feedback_engineering", name + ":identity")
        require(manifest.get("status") == run.get("status"), "saved_status_agrees")
        payloads = manifest.get("files", {})
        require(isinstance(payloads, dict) and all(payloads.get(name) == identities[name]
                for name in ("run.json", "metrics.json")), "manifest_binds_run_and_metrics_bytes")
        require(run.get("seed") == 7800 and run.get("pose") == "supine", "fixed_seed_and_pose")
        require(run.get("planned_upper_bounds") == {"control_calls": 3000, "physics_substeps": 3000,
                "prefix_controls": 1000, "active_controls": 2000, "pd_requests": 2000}, "unchanged_budget")
        require(run.get("no_reset_retry_or_parameter_search") is True
                and run.get("learning_permitted_this_trial") is False, "once_without_learning")
        source, runtime, cost, trial = (run.get(key, {}) for key in ("source", "runtime", "cost", "trial"))
        require(all(isinstance(x, dict) for x in (source, runtime, cost, trial)), "run_sections_are_objects")
        if all(isinstance(x, dict) for x in (source, runtime, cost, trial)):
            require(isinstance(source.get("commit"), str) and bool(source["commit"])
                    and isinstance(source.get("files"), dict), "saved_source_identity_present")
            require(isinstance(runtime.get("python"), str) and isinstance(runtime.get("platform"), str),
                    "saved_runtime_present")
            require(all(cost.get(key) == 0 for key in ZERO), "no_model_learning_teacher_or_GPU_cost")
            require(all(finite(cost.get(key)) and cost[key] >= 0 for key in ("wall_seconds", "cpu_seconds")),
                    "finite_measured_runtime")
            families = ("control_call", "environment_constructor", "reset", "pd_request", "production_import",
                        "audit_contact_snapshot", "audit_geom_name_query", "audit_contact_force_query")
            for family in families:
                values = [cost.get(family + suffix) for suffix in ("_attempts", "_returns", "_exceptions")]
                require(all(integer(x) for x in values) and values[0] == values[1] + values[2],
                        family + ":attempt_return_exception_partition")
            count_keys = ("confirmed_physics_substeps", "captured_native_endpoints", "captured_complete_endpoints",
                          "study_check_attempts", "study_check_returns", "audit_contact_pair_inspections")
            require(all(integer(cost.get(key)) for key in count_keys), "paid_capture_study_pair_counts")
            if all(integer(cost.get(key)) for key in count_keys + ("control_call_attempts", "pd_request_attempts")):
                require(cost["captured_complete_endpoints"] <= cost["captured_native_endpoints"]
                        <= cost["confirmed_physics_substeps"] <= cost["control_call_attempts"] <= 3000,
                        "paid_native_complete_caps")
                require(cost["pd_request_attempts"] <= 2000
                        and cost["study_check_returns"] <= cost["study_check_attempts"] <= cost["pd_request_attempts"],
                        "PD_and_study_caps")
            complete = trial.get("complete")
            require(type(complete) is bool and metrics.get("complete_population") is complete, "complete_flag_agrees")
            expected_status = "failed" if trial.get("failure") else "completed" if complete else "stopped"
            require(run.get("status") == expected_status, "status_retains_failure_or_stop")
            require(not complete or trial.get("failure") is None and trial.get("stop") is None,
                    "complete_has_no_failure_or_stop")
            before, after = trial.get("metadata_before"), trial.get("metadata_after")
            require(metrics.get("metadata_stable") is (before is not None and before == after), "metadata_stability_agrees")
            if before is not None:
                interface = before.get("action_interface", {}) if isinstance(before, dict) else {}
                require(all(interface.get(key) == value for key, value in {
                    "original_baseline_control_dt_s": .02, "construction_control_dt_s": .002,
                    "active_control_dt_s": .002, "model_physics_dt_s": .002,
                    "requested_control_substeps": 1, "request_hold_duration_s": .002,
                    "pd_kp": [64., 64.], "pd_kd": [4., 4.], "controlled_joint_indices": [0, 1],
                    "other_six_requested_torques": "always_zero"}.items()), "saved_frozen_interface")
            if cost.get("control_call_attempts", 0):
                require(source.get("clean_committed_bytes_verified") is True
                        and all(isinstance(runtime.get(key), str) for key in ("mujoco", "numpy")),
                        "paid_run_has_verified_source_and_simulator_runtime")
            windows = metrics.get("windows", [])
            require(isinstance(windows, list) and len(windows) == 2, "two_fixed_windows")
            valid_windows = isinstance(windows, list) and len(windows) == 2 and all(isinstance(w, dict) for w in windows)
            if valid_windows:
                for window, spec in zip(windows, (("A", 800, 999), ("B", 1800, 1999))):
                    label, first, last = spec
                    require((window.get("target"), window.get("active_first"), window.get("active_last")) == spec
                            and window.get("planned_count") == 200 and window.get("threshold_rad") == .01
                            and window.get("full_trial_required") is True, label + ":fixed_window_and_gate")
                    require(integer(window.get("observed_count")) and window["observed_count"] <= 200,
                            label + ":observed_window_cap")
                    mae = window.get("mae_axis_rad")
                    require(window.get("available") is bool(complete), label + ":availability_requires_full_trial")
                    require(vector(mae) and window.get("passed_axis") == [x <= .01 for x in mae]
                            if complete else mae is None and window.get("passed_axis") == [False, False],
                            label + ":saved_MAE_gate_without_trace_recompute")
            phases, contacts = metrics.get("phase_effort_and_contacts", {}), metrics.get("left_arm_contact_checks", {})
            require(isinstance(phases, dict) and set(phases) == set(PHASES)
                    and isinstance(contacts, dict) and set(contacts) == set(PHASES), "three_phase_summaries")
            paid_totals, native_totals, contact_totals = [], [], []
            phase_valid = isinstance(phases, dict) and isinstance(contacts, dict)
            for name in PHASES:
                summary = phases.get(name, {}) if isinstance(phases, dict) else {}
                if not isinstance(summary, dict):
                    require(False, name + ":phase_object")
                    phase_valid = False
                    continue
                paid, native, observed = (summary.get(key) for key in
                    ("confirmed_substeps", "observed_native_endpoints", "observed_contact_endpoints"))
                valid_counts = all(integer(x) for x in (paid, native, observed))
                require(valid_counts and observed <= native <= paid <= 1000 and summary.get("planned_substeps") == 1000,
                        name + ":paid_native_contact_caps")
                phase_valid = phase_valid and valid_counts
                if valid_counts:
                    paid_totals.append(paid); native_totals.append(native); contact_totals.append(observed)
                    require(summary.get("missing_contact_endpoint_substeps") == paid - observed
                            and summary.get("actual_effort_complete") is (paid == native), name + ":missing_and_effort_flags")
                require(all(vector(summary.get(key)) for key in ("requested_absolute_nm_s_axis", "requested_squared_nm2_s_axis",
                        "actual_endpoint_sample_absolute_nm_s_axis", "actual_endpoint_sample_squared_nm2_s_axis")), name + ":finite_effort")
                arm = summary.get("classes", {}).get("left_arm", {})
                positive = arm.get("positive_contact_endpoint_count")
                require(integer(positive) and valid_counts and positive <= observed, name + ":saved_left_arm_count")
                expected_contact = bool(complete and valid_counts and paid == observed == 1000
                                        and integer(positive) and positive >= 1)
                require(isinstance(contacts, dict) and contacts.get(name) is expected_contact, name + ":original_contact_gate")
            if phase_valid:
                require(sum(paid_totals) == cost.get("confirmed_physics_substeps")
                        and sum(native_totals) == cost.get("captured_native_endpoints")
                        and sum(contact_totals) == cost.get("captured_complete_endpoints"), "phase_cost_totals_agree")
            require(not complete or cost.get("control_call_returns") == cost.get("confirmed_physics_substeps")
                    == cost.get("captured_complete_endpoints") == 3000 and cost.get("pd_request_returns") == 2000,
                    "complete_full_paid_population")
            qualified = bool(complete and metrics.get("metadata_stable") and valid_windows
                             and all(all(w.get("passed_axis", [])) for w in windows)
                             and isinstance(contacts, dict) and all(contacts.get(name) is True for name in PHASES))
            require(metrics.get("engineering_qualification_passed") is qualified, "original_engineering_gate_agrees")
        require(metrics.get("partial_subset_ranking") is False
                and metrics.get("sustained_support_or_contact_causality_demonstrated") is False,
                "no_partial_ranking_or_contact_causality_claim")

    receipt = {"status": "saved_contract_consistent" if not errors else "saved_contract_failed_preserved",
               "raw_directory": str(args.raw), "checks": checks, "failures": errors,
               "input_identities": identities, "JSON_payload_reads": reads, "JSON_payload_bytes_read": read_bytes,
               "trajectory_source_journal_or_ZIP_reads": 0, "MAE_or_effort_recomputed_from_trajectory": False,
               "physical_model_fit_or_test_calls": 0, "automatic_retry": False,
               "wall_seconds_before_output": time.perf_counter() - wall,
               "cpu_seconds_before_output": time.process_time() - cpu}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": receipt["status"], "checks": checks, "failures": len(errors), "payload_reads": reads}))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
