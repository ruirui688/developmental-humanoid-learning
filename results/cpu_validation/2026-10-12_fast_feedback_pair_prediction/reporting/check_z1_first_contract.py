"""First thin Z1 saved-payload contract; no model, physics, or metric math.

Reads only manifest.json, run.json, metrics.json, models.json from the new
Z1 directory. Failure and partial execution are legitimate result branches.
The report concerns saved evidence consistency, never scientific adoption.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import time


SEEDS = [7701, 7702, 7703]
ORIGINS = {1: 100, 10: 100, 20: 99, 50: 96, 150: 86}
FLAGS = (
    "scientific_adoption", "old_free_root_C4_validation",
    "c4_scientific_validation", "c5_scientific_dependency_released",
    "c4_contact_scientific_validation",
)
BOUNDS = {
    "control_calls": 21000, "physics_substeps": 21000,
    "RLS_vector_commits": 12000, "RLS_scalar_commits": 24000,
    "independent_prediction_pairs": 124680,
}
TIMES = {
    "construction_control_dt_s": .02, "active_control_dt_s": .002,
    "model_physics_dt_s": .002, "requested_control_substeps": 1,
    "request_hold_duration_s": .002,
}
DEPENDENCIES = (
    "scripts/develop_fast_feedback_pair.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
    "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md",
    "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md",
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/fast_feedback_environment.py",
    "scripts/validate_fast_feedback_engineering.py",
    "docs/SUSPENDED_PAIR_DOMAIN_DESIGN.md",
    "src/developmental_physics/suspended_environment.py",
    "scripts/validate_supported_pair_engineering.py",
    "docs/SUPPORTED_PAIR_DOMAIN_DESIGN.md",
    "src/developmental_physics/supported_environment.py",
    "src/developmental_physics/environment.py",
    "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py",
    "src/developmental_physics/guard_coupled_pair_model.py",
    "src/developmental_physics/guard_pair_model.py",
    "src/developmental_physics/local_pair_model.py",
    "src/developmental_physics/local_model.py",
    "src/developmental_physics/fast_feedback_pair_mpc.py",
    "pyproject.toml",
)
PROTOCOL_PINS = {
    "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md": {
        "bytes": 12655, "sha256": "2370f7b76f627936e18bd609d67f785e6a090bde3c7dea0097deda237b42305b"},
    "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md": {
        "bytes": 9430, "sha256": "5b71ac014786ebbc464becc8579c36df906360e256d47232612ddc141b8bcee4"},
}
BASE_COUNTERS = (
    "control_call_attempts", "control_call_returns", "control_call_exceptions",
    "confirmed_physics_substeps", "captured_substep_endpoint_forward_returns",
    "environment_constructor_attempts", "environment_constructor_returns",
    "reset_attempts", "reset_returns", "RLS_vector_update_attempts",
    "RLS_vector_update_returns", "RLS_vector_update_exceptions",
    "RLS_vector_update_commits", "RLS_scalar_update_commits",
    "MPC_decision_attempts", "MPC_decision_returns", "MPC_decision_exceptions",
    "teacher_calls", "batch_fit_calls", "task_policy_updates", "GPU_training_seconds",
)


def integer(value):
    return type(value) is int and value >= 0


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def shape(value, dimensions, *, nonnegative=False):
    if not dimensions:
        return finite(value) and (not nonnegative or value >= 0)
    return (isinstance(value, list) and len(value) == dimensions[0]
            and all(shape(item, dimensions[1:], nonnegative=nonnegative) for item in value))


def pin(value):
    return (isinstance(value, dict) and integer(value.get("bytes"))
            and isinstance(value.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None)


def reject_constant(value):
    raise ValueError("nonfinite_json_constant:" + value)


class Contract:
    def __init__(self):
        self.checks = []
        self.unknowns = []

    def check(self, name, condition, detail=None):
        row = {"name": name, "passed": bool(condition)}
        if detail is not None:
            row["detail"] = detail
        self.checks.append(row)

    def unknown(self, name):
        self.unknowns.append(name)


def inspect_snapshot(contract, snapshot, label, count):
    c = contract.check
    c(label + ":object", isinstance(snapshot, dict))
    if not isinstance(snapshot, dict):
        return
    expected = {"structure": "coupled_hinge9", "trainable": False,
                "integration": "endpoint_euler", "dt_seconds": .002,
                "initial_covariance_scale": 100., "forgetting_factor": 1.,
                "hinge_threshold_nm": .25, "vector_update_count": count,
                "scalar_update_count": 2 * count, "output_update_counts": [count, count]}
    for key, value in expected.items():
        c(label + ":" + key, snapshot.get(key) == value)
    for key, dimensions in (("qref_rad", (2,)), ("coefficients", (2, 9)),
                            ("covariance", (2, 9, 9))):
        c(label + ":" + key, shape(snapshot.get(key), dimensions))
    mapping = snapshot.get("input_mapping", {}).get("public_guard", {})
    c(label + ":public_ranges", shape(mapping.get("public_joint_ranges_rad"), (2, 2)))
    adaptation = snapshot.get("time_adaptation", {})
    for key, value in {"reference_constructor_dt_seconds": .02,
                       "active_dt_seconds": .002, "velocity_increment_scale": .1,
                       "old_learned_snapshot_restoration": False,
                       "forgetting_factor": 1., "initial_covariance_scale": 100.,
                       "more_correlated_micro_updates_change_prior_relative_weight": True}.items():
        c(label + ":time:" + key, adaptation.get(key) == value)


def inspect_payloads(contract, loaded, identities):
    c = contract.check
    manifest, run, metrics, models = (loaded[name] for name in
                                     ("manifest.json", "run.json", "metrics.json", "models.json"))
    for name, value in loaded.items():
        c(name + ":object", isinstance(value, dict))
    if not all(isinstance(value, dict) for value in loaded.values()):
        return
    for name in ("run.json", "metrics.json", "models.json"):
        c("manifest_binding:" + name, manifest.get("files", {}).get(name) == identities[name])
    c("manifest_schema", manifest.get("schema_version") == 1)
    c("stage", manifest.get("stage") == run.get("stage") == "prediction")
    c("status_binding", manifest.get("status") == run.get("status")
      and run.get("status") in ("completed", "stopped", "failed"))
    for name, value in (("run", run), ("metrics", metrics), ("manifest", manifest)):
        for flag in FLAGS:
            c(name + ":" + flag, value.get(flag) is False)
    for flag in ("z2_model_contribution_gate_passed", "z2_pd_reference_gate_passed",
                 "suspended_mechanism_validation"):
        if flag in metrics:
            c("metrics:" + flag, metrics[flag] is False)
    c("seeds", run.get("seeds") == SEEDS)
    c("budget_plan", run.get("planned_upper_bounds") == BOUNDS)
    c("no_retry", run.get("no_reset_retry_or_mount_search") is True)
    c("calibration_only_updates", run.get("learning_updates_only_calibration") is True)
    explicit_failure = run.get("failure") is not None
    c("failure_status", not explicit_failure or run.get("status") == "failed")
    source = run.get("source", {})
    verified = source.get("clean_committed_bytes_verified") is True
    c("source_verified_boolean", type(source.get("clean_committed_bytes_verified")) is bool)
    pins = source.get("files", {})
    c("source_pin_population", isinstance(pins, dict) and set(pins).issubset(DEPENDENCIES))
    if not isinstance(pins, dict):
        pins = {}
    for name, value in pins.items():
        c("source_pin:" + name, pin(value))
        if name in PROTOCOL_PINS:
            c("protocol_pin:" + name, value == PROTOCOL_PINS[name])
    if verified:
        c("clean_source_population", set(pins) == set(DEPENDENCIES))
        c("source_commit", isinstance(source.get("commit"), str)
          and re.fullmatch(r"[0-9a-f]{40}", source["commit"]) is not None)
    else:
        c("source_failure_disclosed", explicit_failure)
    runtime = run.get("runtime", {})
    c("runtime_object", isinstance(runtime, dict))
    if isinstance(runtime, dict):
        c("python_metadata", isinstance(runtime.get("python"), str))
        c("platform_metadata", isinstance(runtime.get("platform"), str))
    if not explicit_failure:
        c("new_Z0_binding", "Z0" in run.get("source_gate_bindings", {}))

    cost = run.get("cost", {})
    c("cost_object", isinstance(cost, dict))
    if not isinstance(cost, dict):
        return
    for key in BASE_COUNTERS:
        c("cost:" + key, integer(cost.get(key)))
    for key in ("wall_seconds", "cpu_seconds"):
        c("time:" + key, finite(cost.get(key)) and cost[key] >= 0)
    if not all(integer(cost.get(key)) for key in BASE_COUNTERS):
        return
    for prefix in ("control_call", "RLS_vector_update", "MPC_decision"):
        c(prefix + ":outcome_partition", cost[prefix + "_attempts"]
          == cost[prefix + "_returns"] + cost[prefix + "_exceptions"])
    for key, bound in (("control_call_attempts", 21000), ("confirmed_physics_substeps", 21000),
                       ("RLS_vector_update_commits", 12000), ("RLS_scalar_update_commits", 24000)):
        c("bound:" + key, cost[key] <= bound)
    c("physics_le_attempts", cost["confirmed_physics_substeps"] <= cost["control_call_attempts"])
    c("capture_le_physics", cost["captured_substep_endpoint_forward_returns"] <= cost["confirmed_physics_substeps"])
    c("RLS_atomic_two_outputs", cost["RLS_scalar_update_commits"] == 2 * cost["RLS_vector_update_commits"])
    c("RLS_commit_bound", cost["RLS_vector_update_commits"] <= cost["RLS_vector_update_attempts"])
    for key in ("MPC_decision_attempts", "MPC_decision_returns", "MPC_decision_exceptions",
                "teacher_calls", "batch_fit_calls", "task_policy_updates", "GPU_training_seconds"):
        c("forbidden_work_zero:" + key, cost[key] == 0)
    pair_key = "independent_prediction_pair_prediction_attempts"
    if pair_key in cost:
        c("independent_pair_bound", integer(cost[pair_key]) and cost[pair_key] <= 124680)
    elif not explicit_failure and run.get("status") == "completed":
        c("independent_pair_count_present", False)
    else:
        contract.unknown("independent_prediction_not_attempted_or_counter_absent")
    for prefix in ("independent_prediction_pair_prediction", "independent_prediction_scalar_prediction"):
        keys = [prefix + suffix for suffix in ("_attempts", "_returns", "_failures")]
        if any(key in cost for key in keys):
            values = [cost.get(key, 0) for key in keys]
            c(prefix + ":counts", all(integer(value) for value in values)
              and values[0] == values[1] + values[2])
    if not verified:
        for key in ("control_call_attempts", "confirmed_physics_substeps", "RLS_vector_update_attempts"):
            c("preimport_source_failure_zero:" + key, cost[key] == 0)

    seed_rows = run.get("seed_results", [])
    trials = run.get("trials", [])
    c("seed_rows_list", isinstance(seed_rows, list))
    c("trials_list", isinstance(trials, list))
    if not isinstance(seed_rows, list) or not isinstance(trials, list):
        return
    seed_ids = [row.get("seed") for row in seed_rows if isinstance(row, dict)]
    c("attempted_seed_population", len(seed_ids) == len(seed_rows) == len(set(seed_ids))
      and set(seed_ids).issubset(SEEDS))
    c("unattempted_seed_partition", run.get("unattempted_seeds") == [seed for seed in SEEDS if seed not in seed_ids])
    trial_ids = []
    record_count = returned_count = captured_count = 0
    summaries_known = True
    for index, trial in enumerate(trials):
        label = "trial:" + str(index)
        c(label + ":object", isinstance(trial, dict))
        if not isinstance(trial, dict):
            summaries_known = False
            continue
        trial_ids.append(trial.get("trial_id"))
        seed, kind = trial.get("seed"), trial.get("kind")
        c(label + ":seed_kind", seed in SEEDS and kind in ("calibration", "prediction"))
        c(label + ":identity", trial.get("trial_id") == "Z_" + str(seed) + "_" + str(kind))
        planned = 4000 if kind == "calibration" else 1000
        c(label + ":plan", trial.get("planned_prefix") == 1000 and trial.get("planned_active") == planned)
        complete = trial.get("complete") is True
        c(label + ":complete_boolean", type(trial.get("complete")) is bool)
        if complete:
            c(label + ":complete_without_stop_failure", trial.get("stop") is None and trial.get("failure") is None)
        for name in ("physical", "execution"):
            before, after = trial.get(name + "_fingerprint_before"), trial.get(name + "_fingerprint_after")
            if before is not None and after is not None:
                c(label + ":stable_" + name, before == after)
            elif complete:
                c(label + ":complete_" + name + "_fingerprints", False)
            else:
                contract.unknown(label + ":partial_" + name + "_fingerprints")
        interface = trial.get("action_interface")
        if isinstance(interface, dict):
            for key, value in TIMES.items():
                c(label + ":time:" + key, interface.get(key) == value)
        elif complete:
            c(label + ":complete_interface", False)
        else:
            contract.unknown(label + ":partial_interface")
        counts = [trial.get("record_start"), trial.get("record_end"), trial.get("returned_intervals")]
        effort = trial.get("actual_effort", {})
        captures = [effort.get(phase, {}).get("captured_substeps") for phase in ("prefix", "active")]
        if all(integer(value) for value in counts + captures):
            start, end, returns = counts
            c(label + ":record_bounds", end >= start and end - start <= 1000 + planned and returns <= end - start)
            c(label + ":capture_le_records", sum(captures) <= end - start)
            if complete:
                c(label + ":full_population", end - start == returns == 1000 + planned
                  and captures == [1000, planned])
            record_count += end - start
            returned_count += returns
            captured_count += sum(captures)
        else:
            summaries_known = False
            c(label + ":missing_summary_has_failure", explicit_failure or trial.get("failure") is not None)
            contract.unknown(label + ":partial_count_summary")
    c("unique_trial_ids", len(set(trial_ids)) == len(trial_ids))
    if summaries_known:
        c("trial_control_attempt_binding", record_count == cost["control_call_attempts"])
        c("trial_control_return_binding", returned_count == cost["control_call_returns"])
        c("trial_captured_binding", captured_count == cost["captured_substep_endpoint_forward_returns"])
    c("models_attempted_seed_subset", set(models).issubset({str(seed) for seed in seed_ids}))
    all_prediction_available = len(seed_rows) == 3 and set(seed_ids) == set(SEEDS)
    saved_axes = {}
    for row in seed_rows:
        if not isinstance(row, dict):
            continue
        seed, calibration, prediction = row.get("seed"), row.get("calibration", {}), row.get("prediction", {})
        label = "seed:" + str(seed)
        for kind, trial in (("calibration", calibration), ("prediction", prediction)):
            if isinstance(trial, dict) and trial.get("trial_id") is not None:
                c(label + ":" + kind + "_trial_binding", trial in trials)
        complete_calibration = isinstance(calibration, dict) and calibration.get("complete") is True
        if str(seed) in models:
            c(label + ":model_requires_calibration", complete_calibration)
            pair = models[str(seed)]
            c(label + ":model_names", isinstance(pair, dict) and set(pair) == {"cold", "learned"})
            if isinstance(pair, dict):
                for name, count in (("cold", 0), ("learned", 4000)):
                    inspect_snapshot(contract, pair.get(name), label + ":" + name, count)
        elif complete_calibration and not explicit_failure:
            c(label + ":calibrated_models_present", False)
        scores = row.get("prediction_scores", {})
        complete_prediction = isinstance(prediction, dict) and prediction.get("complete") is True
        score_available = scores.get("complete_population") is True
        all_prediction_available &= complete_calibration and complete_prediction and score_available
        if "complete_population" in scores:
            c(label + ":score_population_binding", scores["complete_population"] == complete_prediction)
        if score_available:
            c(label + ":score_population_requires_models", complete_calibration and str(seed) in models)
            c(label + ":score_trial_binding", scores.get("trial_id") == prediction.get("trial_id"))
            c(label + ":model_fingerprints_stable", scores.get("model_fingerprints") is not None
              and scores.get("model_fingerprints") == scores.get("model_fingerprints_after"))
        horizons = scores.get("horizons", {})
        for horizon, planned in ORIGINS.items():
            group = horizons.get(str(horizon), {})
            if "planned_origin_count" in group:
                c(label + ":H" + str(horizon) + ":planned_origins", group["planned_origin_count"] == planned)
            for name in ("cold", "learned"):
                population = group.get("models", {}).get(name)
                if not isinstance(population, dict):
                    all_prediction_available = False
                    c(label + ":H" + str(horizon) + ":" + name + ":missing_allowed",
                      not complete_prediction or explicit_failure)
                    continue
                plabel = label + ":H" + str(horizon) + ":" + name
                available, observed = population.get("available"), population.get("observed_origin_count")
                c(plabel + ":availability_boolean", type(available) is bool)
                c(plabel + ":origin_bound", integer(observed) and observed <= planned)
                c(plabel + ":no_partial_ranking", population.get("partial_subset_ranking") is False)
                all_prediction_available &= available is True
                if available:
                    c(plabel + ":available_complete", complete_calibration and complete_prediction and observed == planned)
                for signal, key in (("q", "q_rmse_axis_rad"), ("v", "v_rmse_axis_rad_s")):
                    value = population.get(key)
                    c(plabel + ":" + signal + "_shape", shape(value, (2,), nonnegative=True) if available else value is None)
                    saved_axes[(seed, horizon, signal, name)] = value

    c("metrics_complete_boolean", type(metrics.get("complete_population")) is bool)
    c("metrics_population_binding", metrics.get("complete_population") == bool(all_prediction_available))
    c("gate_boolean", type(metrics.get("z1_prediction_gate_passed")) is bool)
    checks = metrics.get("checks")
    if isinstance(checks, list):
        c("metric_mean_type", metrics.get("mean_type") == "arithmetic mean of original per_seed axis RMSE")
        c("metric_no_partial_ranking", metrics.get("partial_subset_ranking") is False)
        per_seed, means = set(), set()
        gated_passes = []
        for index, check in enumerate(checks):
            label = "saved_check:" + str(index)
            c(label + ":object", isinstance(check, dict))
            if not isinstance(check, dict):
                continue
            horizon, signal = check.get("horizon"), check.get("signal")
            available, passed = check.get("available"), check.get("passed")
            c(label + ":booleans", type(available) is bool and type(passed) is bool)
            c(label + ":unavailable_false", available is True or passed is False)
            if check.get("scope") == "three_seed_raw_RMSE_mean":
                identity = (horizon, signal)
                c(label + ":mean_identity", identity in ((10, "v"), (150, "q")) and identity not in means)
                means.add(identity)
                c(label + ":required_improvement", check.get("required_improvement") == .20)
                for key in ("cold_axis_mean", "learned_axis_mean"):
                    c(label + ":" + key, shape(check.get(key), (2,), nonnegative=True) if available else check.get(key) is None)
                fractions = check.get("improvement_fractions")
                c(label + ":fraction_shape", (isinstance(fractions, list) and len(fractions) == 2
                  and all(value is None or finite(value) for value in fractions)) if available else fractions is None)
                gated_passes.append(passed is True)
            else:
                seed = check.get("seed")
                identity = (seed, horizon, signal)
                c(label + ":per_seed_identity", seed in SEEDS and horizon in ORIGINS
                  and signal in ("q", "v") and identity not in per_seed)
                per_seed.add(identity)
                gated = horizon != 1 and (horizon, signal) != (10, "q")
                c(label + ":gated_binding", check.get("gated") is gated)
                if gated:
                    gated_passes.append(passed is True)
                if available:
                    c(label + ":strict_binding", check.get("strict") is ((horizon, signal) in ((10, "v"), (150, "q"))))
                    for name in ("cold", "learned"):
                        key = name + "_axis"
                        c(label + ":" + key + "_binding", shape(check.get(key), (2,), nonnegative=True)
                          and check.get(key) == saved_axes.get((seed, horizon, signal, name)))
        c("saved_per_seed_check_population", per_seed == {(seed, h, s) for seed in SEEDS for h in ORIGINS for s in ("q", "v")})
        c("saved_mean_check_population", means == {(10, "v"), (150, "q")})
        c("stored_gate_boolean_binding", metrics.get("z1_prediction_gate_passed")
          is (bool(all_prediction_available) and all(gated_passes) and not explicit_failure))
    else:
        c("minimal_failure_metrics_legal", explicit_failure and metrics.get("z1_prediction_gate_passed") is False)
    if run.get("status") == "completed":
        c("completed_full_trials", len(trials) == 6 and len(seed_rows) == 3
          and all(trial.get("complete") is True for trial in trials))
        c("completed_paid_population", cost["control_call_attempts"] == 21000
          and cost["confirmed_physics_substeps"] == 21000
          and cost["RLS_vector_update_commits"] == 12000
          and cost["RLS_scalar_update_commits"] == 24000)
    if metrics.get("z1_prediction_gate_passed") is True:
        c("passed_gate_requires_complete_run", run.get("status") == "completed" and not explicit_failure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("results/cpu_validation/2026-10-12_fast_feedback_pair_prediction/raw"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, raw = args.output.resolve(), args.raw.resolve()
    if output == raw or output.is_relative_to(raw) or raw.is_relative_to(output):
        raise ValueError("checker_output_must_not_overlap_raw")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    contract, loaded, identities, reads, failures = Contract(), {}, {}, [], []
    for name in ("manifest.json", "run.json", "metrics.json", "models.json"):
        try:
            data = (raw / name).read_bytes()
            digest = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            reads.append({"name": name, **digest})
            identities[name] = digest
            loaded[name] = json.loads(data, parse_constant=reject_constant)
        except (OSError, ValueError, TypeError) as exc:
            failures.append({"phase": "read_or_parse", "name": name,
                             "type": type(exc).__name__, "message": str(exc)})
            contract.check("load:" + name, False)
    if len(loaded) == 4:
        try:
            inspect_payloads(contract, loaded, identities)
        except Exception as exc:
            failures.append({"phase": "contract", "type": type(exc).__name__, "message": str(exc)})
            contract.check("checker_internal_error", False)
    report = {
        "schema_version": 1, "purpose": "Z1 saved evidence consistency only",
        "raw": str(raw), "reads": reads, "read_call_attempts": 4, "read_call_returns": len(reads),
        "known_payload_bytes_read": sum(row["bytes"] for row in reads),
        "checks": contract.checks, "check_count": len(contract.checks),
        "failed_check_count": sum(row["passed"] is False for row in contract.checks),
        "unknowns": contract.unknowns, "failures": failures,
        "contract_passed": not failures and bool(contract.checks) and all(row["passed"] for row in contract.checks),
        "result_status": loaded.get("run.json", {}).get("status") if isinstance(loaded.get("run.json"), dict) else None,
        "saved_z1_prediction_gate_passed": loaded.get("metrics.json", {}).get("z1_prediction_gate_passed") if isinstance(loaded.get("metrics.json"), dict) else None,
        "recomputed_RMSE_vectors": 0, "recomputed_means": 0, "recomputed_improvement_fractions": 0,
        "model_calls": 0, "physics_calls": 0, "fit_calls": 0,
        "production_source_or_old_result_reads": 0,
        "unmeasured_OS_filesystem_IO": "unknown_not_zero",
        "wall_seconds": time.perf_counter() - wall, "cpu_seconds": time.process_time() - cpu,
        **{flag: False for flag in FLAGS},
    }
    (output / "c4_z1_first_contract_receipt.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("contract_passed", "check_count", "failed_check_count", "saved_z1_prediction_gate_passed")}))
    return 0 if report["contract_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
