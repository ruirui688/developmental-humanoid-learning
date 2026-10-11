"""First Z2 thin output contract; standard library only, never imports experiment code.

Usage: python external/check_z2_first_contract.py RAW_DIRECTORY --output REPORT_JSON
Reads only run/metrics/models/manifest once each. No traces, predictions, source ZIP,
model restoration, fitting, RMSE recomputation, or physical calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time

SEEDS = [7701, 7702, 7703]
FLAGS = ("scientific_adoption", "old_free_root_C4_validation",
         "c4_scientific_validation", "c5_scientific_dependency_released",
         "c4_contact_scientific_validation")
BOUNDS = {"control_calls": 36000, "physics_substeps": 36000, "MPC_decisions": 1200,
          "planning_prediction_pairs": 14580000, "conditional_prediction_pairs": 526560}
TIME_KEYS = {"construction_control_dt_s": .02, "active_control_dt_s": .002,
             "model_physics_dt_s": .002, "requested_control_substeps": 1,
             "request_hold_duration_s": .002}
SHA = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
REQUIRED_SOURCES = (
    "src/developmental_physics/fast_feedback_environment.py",
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/fast_feedback_pair_mpc.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
    "scripts/develop_fast_feedback_pair.py",
    "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md",
    "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md",
)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int and value >= 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    failures, unknown, checks, reads, saved = [], [], [], [], {}

    def require(condition, name):
        checks.append({"check": name, "passed": bool(condition)})
        if not condition:
            failures.append(name)

    for name in ("run.json", "metrics.json", "models.json", "manifest.json"):
        path = args.raw_directory / name
        try:
            data = path.read_bytes()
            record = {"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            reads.append(record)
            value = json.loads(data)
            require(isinstance(value, dict), "JSON_object:" + name)
            saved[name] = value if isinstance(value, dict) else {}
        except Exception as exc:
            failures.append("read_or_parse:" + name + ":" + type(exc).__name__)
            saved[name] = {}

    run, metrics, models, manifest = (saved[name] for name in
        ("run.json", "metrics.json", "models.json", "manifest.json"))
    cost = run.get("cost", {})
    cost = cost if isinstance(cost, dict) else {}
    trials = run.get("trials", [])
    trials = trials if isinstance(trials, list) else []
    rows = run.get("seed_results", [])
    rows = rows if isinstance(rows, list) else []
    top_failure = bool(run.get("failure") or metrics.get("execution_failed") or metrics.get("collector_failed"))

    for label, value in (("run", run), ("manifest", manifest)):
        require(value.get("stage") == "control", label + ":stage_control")
        require(value.get("status") in ("completed", "stopped", "failed"), label + ":status")
    require(manifest.get("schema_version") == 1, "manifest:schema_1")
    require(run.get("status") == manifest.get("status"), "status_binding")
    require(run.get("seeds") == SEEDS, "frozen_seed_population")
    for label, value in (("run", run), ("metrics", metrics), ("manifest", manifest)):
        for key in FLAGS:
            require(value.get(key) is False, label + ":false:" + key)
    for key, maximum in BOUNDS.items():
        require(run.get("planned_upper_bounds", {}).get(key) == maximum, "frozen_budget:" + key)
    declared = manifest.get("files", {})
    declared = declared if isinstance(declared, dict) else {}
    for record in reads:
        if record["name"] != "manifest.json":
            require(declared.get(record["name"]) ==
                    {"bytes": record["bytes"], "sha256": record["sha256"]},
                    "payload_identity:" + record["name"])

    source = run.get("source", {})
    source = source if isinstance(source, dict) else {}
    verified = source.get("clean_committed_bytes_verified") is True
    pins = source.get("files", {})
    pins = pins if isinstance(pins, dict) else {}
    if verified:
        require(bool(COMMIT.fullmatch(str(source.get("commit", "")))), "clean_source_commit")
        require(all(path in pins for path in REQUIRED_SOURCES), "required_new_source_pins")
    else:
        require(top_failure and run.get("status") == "failed", "unverified_source_is_preserved_failure")
    for path, pin in pins.items():
        require(isinstance(pin, dict) and integer(pin.get("bytes")) and pin.get("bytes", 0) > 0
                and bool(SHA.fullmatch(str(pin.get("sha256", "")))), "source_pin:" + str(path))
    runtime = run.get("runtime", {})
    runtime = runtime if isinstance(runtime, dict) else {}
    for key in ("python", "platform"):
        require(isinstance(runtime.get(key), str) and bool(runtime[key]), "runtime:" + key)
    if trials:
        require(verified, "paid_trials_require_verified_source")
        for key in ("numpy", "mujoco"):
            require(isinstance(runtime.get(key), str) and bool(runtime[key]), "runtime:" + key)
    for key in ("wall_seconds", "cpu_seconds"):
        if key in cost:
            require(finite(cost[key]) and cost[key] >= 0, "runtime_cost:" + key)

    def count(key, maximum=None):
        value = cost.get(key, 0)
        require(integer(value), "nonnegative_counter:" + key)
        value = value if integer(value) else 0
        if maximum is not None:
            require(value <= maximum, "counter_cap:" + key)
        return value

    attempts = count("control_call_attempts", 36000)
    returns = count("control_call_returns", 36000)
    exceptions = count("control_call_exceptions", 36000)
    steps = count("confirmed_physics_substeps", 36000)
    captured = count("captured_substep_endpoint_forward_returns", 36000)
    require(returns + exceptions == attempts, "paid_attempt_return_exception_partition")
    require(captured <= steps <= attempts, "microstep_and_capture_paid_bounds")
    if not verified:
        require(attempts == steps == 0, "source_failure_no_physics")
    for key in ("RLS_vector_update_attempts", "RLS_vector_update_returns", "RLS_vector_update_exceptions",
                "RLS_vector_update_commits", "RLS_scalar_update_commits", "teacher_calls",
                "batch_fit_calls", "task_policy_updates", "GPU_training_seconds"):
        require(cost.get(key, 0) == 0, "forbidden_update_or_prior:" + key)

    decisions = count("MPC_decision_attempts", 1200)
    decision_returns = count("MPC_decision_returns", 1200)
    decision_failures = count("MPC_decision_exceptions", 1200)
    require(decision_returns + decision_failures == decisions, "decision_partition")
    candidates = count("planning_residual_candidate_attempts", 97200)
    require(candidates <= 81 * decisions, "candidate_budget_by_decisions")
    require(count("planning_returned_candidate_rejections", 97200) <= 81 * decision_returns,
            "returned_candidate_rejection_bounds")
    require(count("planning_fallback_returns", 1200) <= decision_returns, "fallback_return_bounds")
    for scope, pair_cap in (("planning", 14580000), ("control_conditional_prediction", 526560)):
        pa = count(scope + "_pair_prediction_attempts", pair_cap)
        pr = count(scope + "_pair_prediction_returns", pair_cap)
        pf = count(scope + "_pair_prediction_failures", pair_cap)
        sa = count(scope + "_scalar_prediction_attempts", 2 * pair_cap)
        sr = count(scope + "_scalar_prediction_returns", 2 * pair_cap)
        sf = count(scope + "_scalar_prediction_failures", 2 * pair_cap)
        require(pr + pf == pa and sr + sf == sa, scope + ":prediction_partitions")
        require(2 * pr <= sr <= sa <= 2 * pa, scope + ":atomic_head_accounting")
        ga = count(scope + "_feature_guard_projection_attempts", pair_cap)
        gr = count(scope + "_feature_guard_projection_returns", pair_cap)
        require(gr <= ga, scope + ":feature_guard_accounting")
    require(cost.get("planning_pair_prediction_attempts", 0) <= candidates * 150,
            "planning_horizon_budget")
    pd_total = 0
    for scope, cap in (("control_cold", 6000), ("control_learned", 6000),
                       ("control_pd", 6000), ("planning", 14580000)):
        pa = count(scope + "_pd_request_attempts", cap)
        pr = count(scope + "_pd_request_returns", cap)
        require(pr <= pa, scope + ":PD_partition")
        if scope != "planning":
            pd_total += pa
    require(pd_total <= 18000, "actual_actor_PD_budget_separate_from_planning")
    for key, value in cost.items():
        if key.endswith(("_pair_prediction_attempts", "_scalar_prediction_attempts",
                         "_feature_guard_projection_attempts")):
            require(key.startswith(("planning_", "control_conditional_prediction_")) or value == 0,
                    "forward_category:" + key)
        if key.endswith("_pd_request_attempts"):
            require(key.startswith(("planning_", "control_cold_", "control_learned_", "control_pd_")) or value == 0,
                    "PD_category:" + key)
        if key.endswith("_unknown_failure_count") and value:
            unknown.append("reported_unknown_accounting:" + key)

    span_total = returned_total = captured_total = 0
    spans_known = returned_known = capture_known = True
    for index, trial in enumerate(trials):
        label = "trial:" + str(index)
        if not isinstance(trial, dict):
            require(False, label + ":object")
            continue
        complete = trial.get("complete") is True
        require(trial.get("seed") in SEEDS or (top_failure and not trial), label + ":seed")
        require(trial.get("kind") in ("control_cold", "control_learned", "control_pd", "control_zero")
                or (top_failure and not trial), label + ":kind")
        for key, expected in (("planned_prefix", 1000), ("planned_active", 2000)):
            if key in trial or complete:
                require(trial.get(key) == expected, label + ":" + key)
        start, end = trial.get("record_start"), trial.get("record_end")
        if integer(start) and integer(end):
            require(0 <= end - start <= 3000, label + ":paid_record_span")
            span_total += end - start
        else:
            spans_known = False
            unknown.append(label + ":paid_span_unavailable")
        returned = trial.get("returned_intervals")
        if integer(returned):
            require(returned <= 3000, label + ":returned_bound")
            returned_total += returned
        else:
            returned_known = False
        interface = trial.get("action_interface")
        if isinstance(interface, dict):
            for key, expected in TIME_KEYS.items():
                require(interface.get(key) == expected, label + ":time:" + key)
        else:
            require(not complete, label + ":complete_requires_time_identity")
            unknown.append(label + ":time_identity_unavailable")
        for stem in ("physical_fingerprint", "execution_fingerprint"):
            before, after = trial.get(stem + "_before"), trial.get(stem + "_after")
            if before is not None and after is not None:
                require(before == after, label + ":fixed:" + stem)
            else:
                require(not complete, label + ":complete_requires:" + stem)
        before, after = trial.get("model_fingerprints_before"), trial.get("model_fingerprints_after")
        if before is not None and after is not None:
            require(before == after, label + ":frozen_models")
        else:
            require(not complete, label + ":complete_requires_model_identity")
        effort = trial.get("actual_effort", {})
        if not isinstance(effort, dict):
            effort = {}
        for phase, cap in (("prefix", 1000), ("active", 2000)):
            values = effort.get(phase, {})
            if not isinstance(values, dict) or not integer(values.get("captured_substeps")):
                capture_known = False
                require(not complete, label + ":complete_requires_effort:" + phase)
                continue
            number = values["captured_substeps"]
            captured_total += number
            require(number <= cap, label + ":effort_capture:" + phase)
            for key in ("actual_absolute_two_axis_nm_s", "actual_squared_two_axis_nm2_s",
                        "all8_actual_absolute_nm_s", "all8_actual_squared_nm2_s"):
                require(finite(values.get(key)) and values[key] >= 0, label + ":effort_finite:" + phase + ":" + key)
            if complete:
                require(number == cap and values.get("complete") is True, label + ":complete_effort:" + phase)
    if spans_known:
        require(span_total == attempts, "trial_paid_spans_bind_attempts")
    if returned_known:
        require(returned_total == returns, "trial_returns_bind_paid_returns")
    if capture_known:
        require(captured_total == captured, "trial_effort_capture_bind_counter")

    require(len(trials) <= 12, "attempted_trial_upper_bound")
    require(len(rows) <= 3 and len({row.get("seed") for row in rows if isinstance(row, dict)}) == len(rows),
            "attempted_seed_population")
    for row in rows:
        if not isinstance(row, dict):
            continue
        seed = row.get("seed")
        require(seed in SEEDS, "seed_result:known_seed")
        controls = row.get("controls", {})
        scores = row.get("tracking_scores", {})
        controls = controls if isinstance(controls, dict) else {}
        scores = scores if isinstance(scores, dict) else {}
        for name, score in scores.items():
            trial = controls.get(name, {})
            require(name in ("cold", "learned", "pd", "zero") and isinstance(score, dict),
                    "tracking_schema:" + str(seed) + ":" + name)
            if not isinstance(score, dict):
                continue
            require(score.get("partial_subset_ranking") is False, "no_partial_ranking:" + str(seed) + ":" + name)
            if score.get("available") is True:
                active_effort = trial.get("actual_effort", {}).get("active", {})
                require(trial.get("complete") is True and active_effort.get("complete") is True
                        and score.get("planned_active_count") == 2000
                        and score.get("observed_active_count") == 2000,
                        "tracking_complete_effort_population:" + str(seed) + ":" + name)
                values = [score.get("joint_rmse_rad"), score.get("actual_absolute_two_axis_nm_s"),
                          score.get("actual_squared_two_axis_nm2_s")]
                axis = score.get("axis_rmse_rad")
                require(isinstance(axis, list) and len(axis) == 2
                        and all(finite(x) and x >= 0 for x in values + (axis if isinstance(axis, list) else [])),
                        "tracking_saved_values_finite:" + str(seed) + ":" + name)
            else:
                require(score.get("axis_rmse_rad") is None and score.get("joint_rmse_rad") is None,
                        "unavailable_tracking_not_partial_RMSE:" + str(seed) + ":" + name)

    if models:
        require(set(models) == {str(seed) for seed in SEEDS}, "frozen_Z1_model_population")
        for seed, pair in models.items():
            require(isinstance(pair, dict) and set(pair) == {"cold", "learned"}, "model_pair:" + seed)
            if not isinstance(pair, dict):
                continue
            for name, snapshot in pair.items():
                require(isinstance(snapshot, dict), "snapshot_object:" + seed + ":" + name)
                if not isinstance(snapshot, dict):
                    continue
                count_expected = 0 if name == "cold" else 4000
                require(snapshot.get("dt_seconds") == .002 and snapshot.get("trainable") is False
                        and snapshot.get("time_adaptation", {}).get("active_dt_seconds") == .002,
                        "new_micro_snapshot_time:" + seed + ":" + name)
                require(snapshot.get("vector_update_count") == count_expected
                        and snapshot.get("scalar_update_count") == 2 * count_expected
                        and snapshot.get("output_update_counts") == [count_expected, count_expected],
                        "frozen_snapshot_update_identity:" + seed + ":" + name)
    else:
        require(not trials and top_failure, "empty_models_only_early_failure")

    gates = []
    for name, flag, baseline in (("model_contribution", "z2_model_contribution_gate_passed", "cold"),
                                ("pd_reference", "z2_pd_reference_gate_passed", "pd")):
        gate = metrics.get(name)
        passed = metrics.get(flag)
        require(type(passed) is bool, "gate_flag:" + flag)
        gates.append(passed is True)
        if isinstance(gate, dict):
            require(type(gate.get("available")) is bool and type(gate.get("passed")) is bool
                    and (top_failure or gate.get("passed") is passed), "gate_binding:" + name)
            gate_checks = gate.get("checks", [])
            require(isinstance(gate_checks, list), "gate_checks_list:" + name)
            if gate.get("available") is True:
                require(len(rows) == 3 and all(
                    row.get("tracking_scores", {}).get(baseline, {}).get("available") is True
                    and row.get("tracking_scores", {}).get("learned", {}).get("available") is True for row in rows),
                    "gate_complete_tracking:" + name)
                effort_checks = [value for value in gate_checks if isinstance(value, dict)
                                 and value.get("scope") == "three_seed_actual_effort_mean"]
                require({value.get("signal") for value in effort_checks} ==
                        {"actual_absolute_two_axis_nm_s", "actual_squared_two_axis_nm2_s"},
                        "effort_gate_population:" + name)
                for value in effort_checks:
                    require(all(finite(value.get(key)) and value[key] >= 0
                                for key in ("baseline_mean", "learned_mean"))
                            and value.get("maximum_ratio") == 1.05,
                            "effort_gate_evaluable:" + name + ":" + str(value.get("signal")))
            if passed:
                require(gate.get("available") is True and len(gate_checks) == 6
                        and all(isinstance(value, dict) and value.get("passed") is True for value in gate_checks),
                        "passed_gate_complete_checks:" + name)
        else:
            require(top_failure and passed is False, "missing_comparison_only_execution_failure:" + name)
    require(not gates[1] or gates[0], "PD_gate_depends_on_model_contribution")
    if "suspended_mechanism_validation" in metrics:
        require(metrics["suspended_mechanism_validation"] is (gates[0] and gates[1]), "suspended_gate_binding")
    else:
        require(top_failure, "missing_suspended_flag_only_execution_failure")
    if top_failure:
        require(not any(gates) and run.get("status") == "failed", "exception_closes_both_science_gates")

    report = {"schema": "Z2_first_thin_contract_v1", "contract_passed": not failures,
              "failure_count": len(failures), "failures": failures, "unknown_preserved": unknown,
              "checks": checks, "read_receipt": {"file_reads": len(reads),
              "bytes": sum(value["bytes"] for value in reads), "files": reads},
              "wall_seconds": time.perf_counter() - started, "cpu_seconds": time.process_time() - cpu,
              "raw_trajectory_reads": 0, "prediction_payload_reads": 0, "source_payload_reads": 0,
              "experiment_imports": 0, "model_calls": 0, "fit_calls": 0, "physical_calls": 0,
              "RMSE_recalculations": 0, "gate_mean_recalculations": 0,
              "scientific_gate_values_are_saved_not_recomputed": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"contract_passed": report["contract_passed"], "failure_count": len(failures),
                      "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["contract_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

