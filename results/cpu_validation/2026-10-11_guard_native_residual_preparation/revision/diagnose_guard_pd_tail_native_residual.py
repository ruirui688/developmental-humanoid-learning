"""Frozen I: causal previous-base-residual scoring from four saved H files.

No simulator, model, model snapshot, fitting package, or G raw is imported.
The formal entry point requires committed, byte-identical source and protocol.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time


SOURCE_PATH = "scripts/diagnose_guard_pd_tail_native_residual.py"
PROTOCOL_PATH = "docs/GUARD_PD_TAIL_NATIVE_RESIDUAL_DIAGNOSTIC_PROTOCOL.md"
DEFAULT_INPUT = "results/cpu_validation/2026-10-11_guard_forecast_stop/raw"
H_MANIFEST_SHA256 = "b3c9969c6d65987c0993c32e0143a7f5f4e704410d5d4e7cbe423a950b5ed538"
H_SOURCE_COMMIT = "a46633c71e95826835ebc43f0aeaf6d5fdfd19e8"
G_PHYSICAL_COMMIT = "91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2"
KINDS = ("cold11", "learned_sparse11")
SEEDS = (0, 1, 2)
TRIALS = tuple(f"seed{seed}_{kind}" for seed in SEEDS for kind in KINDS)
SEGMENTS = ("ALL", "A", "B", "CROSS_A_TO_B")
DT = .02


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _qv(value):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("qv must be [q_pair,v_pair]")
    result = []
    for pair in value:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("qv must contain two two-axis pairs")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in pair):
            raise ValueError("qv must contain finite numeric values")
        result.append([float(x) for x in pair])
    return result


def _usable(row):
    effort = row.get("interval_effort") or {}
    if effort.get("executed_substeps") != 10 or effort.get("complete_20ms_interval") is not True:
        return None, "partial_or_incomplete_interval"
    prediction = row.get("independent_current_request_prediction") or {}
    if prediction.get("prediction_available") is not True:
        return None, "missing_independent_prediction"
    if row.get("actual_next_qv") is None:
        return None, "missing_actual_qv"
    if prediction.get("saved_prediction_qv") is None:
        return None, "missing_base_qv"
    actual = _qv(row["actual_next_qv"])
    base = _qv(prediction["saved_prediction_qv"])
    step = _integer(row.get("step_index"), "step_index")
    active = _integer(row.get("active_index"), "active_index")
    if step != 100+active or active >= 200:
        raise ValueError("saved active/step index violates fixed H task")
    return {"step_index": step, "active_index": active,
            "actual_qv": actual, "base_prediction_qv": base}, None


def _make_pair(trial_id, previous, current):
    """Construct corrected prediction before using current actual for scoring."""
    bias = previous["original_base_velocity_residual"]
    base = current["base_prediction_qv"]
    corrected = [[base[0][i]+DT*bias[i] for i in range(2)],
                 [base[1][i]+bias[i] for i in range(2)]]
    actual = current["actual_qv"]
    errors = {name: [[actual[signal][axis]-prediction[signal][axis]
                     for axis in range(2)] for signal in range(2)]
              for name, prediction in (("base", base), ("corrected", corrected))}
    segment = "A" if current["active_index"] < 100 else "B"
    previous_segment = "A" if previous["active_index"] < 100 else "B"
    return {"trial_id": trial_id,
            "previous_step_index": previous["step_index"],
            "current_step_index": current["step_index"],
            "previous_active_index": previous["active_index"],
            "current_active_index": current["active_index"],
            "history_segment": previous_segment, "current_segment": segment,
            "cross_a_to_b": previous_segment == "A" and segment == "B",
            "previous_original_base_velocity_residual": list(bias),
            "base_prediction_qv": base, "corrected_prediction_qv": corrected,
            "actual_qv": actual, "signed_actual_minus_prediction_qv": errors,
            "current_actual_used_in_correction": False,
            "previous_residual_definition": "previous actual v minus previous original base v"}


def score_records(rows):
    """Pure synthetic-testable calculation; this function performs no reads."""
    previous = {trial_id: None for trial_id in TRIALS}
    pairs, unscored = [], []
    cost = {"last20_records_parsed": 0, "eligible_complete_records": 0,
            "adjacent_pairs": 0, "bias_state_scalar_calculations": 0,
            "bias_state_scalar_publications": 0, "corrected_velocity_scalar_additions": 0,
            "corrected_q_scalar_multiplications": 0, "corrected_q_scalar_additions": 0}
    for row in rows:
        cost["last20_records_parsed"] += 1
        trial_id = row.get("trial_id")
        if trial_id not in previous:
            raise ValueError(f"unexpected trial_id: {trial_id}")
        current, reason = _usable(row)
        prior = previous[trial_id]
        if current is None:
            previous[trial_id] = None
            unscored.append({"trial_id": trial_id, "step_index": row.get("step_index"),
                             "active_index": row.get("active_index"), "reason": reason,
                             "history_reset": True})
            continue
        if prior is None:
            reason = "no_valid_window_history"
        elif (current["step_index"] != prior["step_index"]+1
              or current["active_index"] != prior["active_index"]+1):
            reason = "noncontiguous_history"
        else:
            pairs.append(_make_pair(trial_id, prior, current))
            cost["adjacent_pairs"] += 1
            cost["corrected_velocity_scalar_additions"] += 2
            cost["corrected_q_scalar_multiplications"] += 2
            cost["corrected_q_scalar_additions"] += 2
            reason = None
        if reason:
            unscored.append({"trial_id": trial_id, "step_index": current["step_index"],
                             "active_index": current["active_index"], "reason": reason,
                             "history_reset": True})
        # Only now publish the current label as ORIGINAL-base history for t+1.
        current["original_base_velocity_residual"] = [
            current["actual_qv"][1][i]-current["base_prediction_qv"][1][i]
            for i in range(2)]
        previous[trial_id] = current
        cost["eligible_complete_records"] += 1
        cost["bias_state_scalar_calculations"] += 2
        cost["bias_state_scalar_publications"] += 2
    return pairs, unscored, cost


def _metrics(errors):
    if not errors:
        return {"count": 0, "rmse": None, "mae": None, "bias": None}
    count = len(errors)
    return {"count": count, "rmse": math.sqrt(math.fsum(x*x for x in errors)/count),
            "mae": math.fsum(abs(x) for x in errors)/count,
            "bias": math.fsum(errors)/count}


def _relative(base, corrected):
    return None if base is None or base == 0 else (base-corrected)/base


def summarize_pairs(pairs):
    bins = {(trial_id, segment, signal, axis): {"base": [], "corrected": []}
            for trial_id in TRIALS for segment in SEGMENTS
            for signal in ("q", "v") for axis in range(2)}
    insertions = 0
    for pair in pairs:
        segments = ["ALL", pair["current_segment"]]
        if pair["cross_a_to_b"]:
            segments.append("CROSS_A_TO_B")
        for segment in segments:
            for signal_index, signal in enumerate(("q", "v")):
                for axis in range(2):
                    target = bins[pair["trial_id"], segment, signal, axis]
                    for variant in ("base", "corrected"):
                        target[variant].append(pair["signed_actual_minus_prediction_qv"][variant][signal_index][axis])
                        insertions += 1
    groups, lookup = [], {}
    for (trial_id, segment, signal, axis), values in bins.items():
        base, corrected = (_metrics(values[name]) for name in ("base", "corrected"))
        record = {"trial_id": trial_id, "segment": segment, "signal": signal,
                  "axis": axis, "axis_name": ("shoulder", "elbow")[axis],
                  "pair_count": base["count"], "base": base, "corrected": corrected,
                  "rmse_relative_improvement": _relative(base["rmse"], corrected["rmse"]),
                  "mae_relative_improvement": _relative(base["mae"], corrected["mae"]),
                  "absolute_bias_reduction": None if not base["count"] else abs(base["bias"])-abs(corrected["bias"]),
                  "empty_reason": "no_eligible_adjacent_pairs" if not base["count"] else None,
                  "domain_validation": False}
        groups.append(record)
        lookup[trial_id, segment, signal, axis] = record
    gates = {}
    for kind in KINDS:
        axis_records = []
        for axis in range(2):
            seed_records, improvements = [], []
            valid = True
            for seed in SEEDS:
                record = lookup[f"seed{seed}_{kind}", "ALL", "v", axis]
                improvement = record["rmse_relative_improvement"]
                defined = improvement is not None and math.isfinite(improvement)
                valid = valid and defined
                if defined:
                    improvements.append(improvement)
                seed_records.append({"seed": seed, "pair_count": record["pair_count"],
                                     "base_rmse": record["base"]["rmse"],
                                     "corrected_rmse": record["corrected"]["rmse"],
                                     "relative_improvement": improvement,
                                     "strictly_improved": defined and improvement > 0,
                                     "undefined_reason": None if defined else "empty_or_zero_base_rmse"})
            mean = math.fsum(improvements)/3 if valid else None
            passed = valid and all(x["strictly_improved"] for x in seed_records) and mean >= .20
            axis_records.append({"axis": axis, "seeds": seed_records,
                                 "mean_relative_improvement": mean, "evaluated": valid,
                                 "passed": passed})
        gates[kind] = {"segment": "ALL", "signal": "v", "metric": "RMSE",
                       "axes": axis_records, "evaluated": all(x["evaluated"] for x in axis_records),
                       "passed": all(x["passed"] for x in axis_records),
                       "scientific_adoption": False}
    return groups, gates, insertions


def _read_input(path, cost):
    data = path.read_bytes()
    cost["H_input_file_reads"] += 1
    cost["H_input_raw_bytes"] += len(data)
    cost["sha256_input_bytes"] += len(data)
    return data, {"path": str(path), "bytes": len(data), "sha256": _sha(data)}


def load_h(input_dir, cost):
    inputs, data = {}, {}
    for name in ("manifest.json", "run.json", "description.json", "last20.jsonl"):
        data[name], inputs[name] = _read_input(input_dir/name, cost)
    if inputs["manifest.json"]["sha256"] != H_MANIFEST_SHA256:
        raise ValueError("H manifest pin mismatch")
    manifest, run, description = (json.loads(data[name]) for name in
                                  ("manifest.json", "run.json", "description.json"))
    cost["H_json_documents_parsed"] = 3
    if manifest.get("status") != "completed" or manifest.get("scientific_adoption") is not False:
        raise ValueError("H manifest status mismatch")
    for name in ("run.json", "description.json", "last20.jsonl"):
        if manifest.get("files", {}).get(name) != {k: inputs[name][k] for k in ("bytes", "sha256")}:
            raise ValueError(f"H payload binding mismatch: {name}")
    source = run.get("diagnostic_source") or {}
    if (run.get("status") != "completed" or run.get("scientific_adoption") is not False
            or source.get("commit") != H_SOURCE_COMMIT
            or source.get("clean_committed_bytes_verified") is not True
            or run.get("G_physics_source_commit") != G_PHYSICAL_COMMIT):
        raise ValueError("H/G frozen source binding mismatch")
    if (description.get("diagnostic") != "H_saved_forecast_stop"
            or description.get("scientific_adoption") is not False):
        raise ValueError("unexpected H description")
    rows = [json.loads(line) for line in data["last20.jsonl"].splitlines() if line.strip()]
    trials = description.get("trials") or []
    trial_map = {trial.get("trial_id"): trial for trial in trials}
    if len(trials) != 6 or set(trial_map) != set(TRIALS):
        raise ValueError("H description must contain exactly six fixed trials")
    for trial_id in TRIALS:
        trial_rows = [row for row in rows if row.get("trial_id") == trial_id]
        trial = trial_map[trial_id]
        count = _integer(trial.get("saved_active_count"), "saved_active_count")
        if (len(trial_rows) != min(20, count) or trial.get("last20_count") != len(trial_rows)
                or (trial_rows and trial_rows[-1].get("active_index") != count-1)):
            raise ValueError(f"H fixed last20 window mismatch: {trial_id}")
    return rows, inputs, trials


def verify_sources(repo, source_commit, cost):
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit):
        raise ValueError("I source commit must be an exact lowercase full commit")
    if Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("formal script must run from its frozen canonical path")

    def git(*args):
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_queries"] += 1
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise RuntimeError(f"Git source verification failed: {args[0]}")
        return result.stdout

    if git("rev-parse", "HEAD").decode("ascii").strip() != source_commit:
        raise ValueError("I HEAD differs from declared frozen source commit")
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise ValueError("I formal execution requires a clean tracked checkout")
    sources = {}
    for name in (SOURCE_PATH, PROTOCOL_PATH):
        data = (repo/name).read_bytes()
        cost["own_source_file_reads"] += 1
        cost["own_source_raw_bytes"] += len(data)
        if git("show", f"{source_commit}:{name}") != data:
            raise ValueError(f"I committed source bytes mismatch: {name}")
        sources[name] = {"bytes": len(data), "sha256": _sha(data)}
    return {"commit": source_commit, "files": sources, "clean_committed_bytes_verified": True}


def _write(path, data, payloads):
    path.write_bytes(data)
    payloads[path.name] = {"bytes": len(data), "sha256": _sha(data)}


def run(args):
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("I output directory already exists; no overwrite or rerun")
    output.mkdir(parents=True)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = {"H_input_file_reads": 0, "H_input_raw_bytes": 0, "sha256_input_bytes": 0,
            "H_json_documents_parsed": 0, "own_source_file_reads": 0, "own_source_raw_bytes": 0,
            "git_queries": 0, "git_return_bytes": 0,
            "model_predictions": 0, "model_updates": 0, "RLS_updates": 0, "physics_calls": 0}
    payloads = {}
    try:
        repo = Path(args.repo).resolve()
        own_source = verify_sources(repo, args.source_commit, cost)
        input_dir = Path(args.input)
        if not input_dir.is_absolute():
            input_dir = repo/input_dir
        rows, inputs, source_trials = load_h(input_dir.resolve(), cost)
        pairs, unscored, calculations = score_records(rows)
        cost.update(calculations)
        groups, gates, insertions = summarize_pairs(pairs)
        cost["group_scalar_error_insertions"] = insertions
        pair_bytes = b"".join((json.dumps(pair, ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8") for pair in pairs)
        _write(output/"adjacent_pairs.jsonl", pair_bytes, payloads)
        description = {"schema_version": 1, "diagnostic": "I_H_saved_causal_native_residual",
                       "scientific_adoption": False, "development_window_only": True,
                       "dt_seconds": DT, "bias_definition": "previous actual v minus previous original base v",
                       "prediction_source": "independent_current_request_prediction",
                       "source_trials": source_trials, "groups": groups, "unscored_records": unscored,
                       "development_gates_by_kind": gates,
                       "primary_development_gate_kind": "learned_sparse11",
                       "primary_development_gate_passed": gates["learned_sparse11"]["passed"],
                       "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
                       "domain_control_cold_start_or_safety_claim": False}
        _write(output/"description.json", _json_bytes(description), payloads)
        cost["wall_seconds"] = time.perf_counter()-wall
        cost["cpu_seconds"] = time.process_time()-cpu
        cost["timing_excludes"] = "final run.json and manifest.json serialization/write"
        run_record = {"schema_version": 1, "status": "completed", "scientific_adoption": False,
                      "inputs": inputs, "H_source_commit": H_SOURCE_COMMIT,
                      "G_physical_source_commit": G_PHYSICAL_COMMIT,
                      "diagnostic_source": own_source, "cost": cost,
                      "primary_development_gate_passed": gates["learned_sparse11"]["passed"]}
        _write(output/"run.json", _json_bytes(run_record), payloads)
        _write(output/"manifest.json", _json_bytes({"schema_version": 1, "status": "completed",
               "scientific_adoption": False, "files": dict(payloads)}), {})
        return run_record
    except BaseException as exc:
        cost["wall_seconds"] = time.perf_counter()-wall
        cost["cpu_seconds"] = time.process_time()-cpu
        failure = {"status": "failed", "scientific_adoption": False,
                   "exception_type": type(exc).__name__, "message": str(exc), "cost": cost,
                   "failure_preserved_no_rerun": True,
                   "declared_I_source_commit": args.source_commit,
                   "diagnostic_source": locals().get("own_source"),
                   "inputs": locals().get("inputs"),
                   "input_binding_note": "null if source verification or load_h did not return; no claim of complete failed-read hashes",
                   "declared_input_directory": str(args.input),
                   "expected_H_manifest_sha256": H_MANIFEST_SHA256,
                   "expected_H_source_commit": H_SOURCE_COMMIT,
                   "expected_G_physical_commit": G_PHYSICAL_COMMIT}
        _write(output/"failure.json", _json_bytes(failure), payloads)
        _write(output/"manifest.json", _json_bytes({"schema_version": 1, "status": "failed",
               "scientific_adoption": False, "files": dict(payloads)}), {})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
