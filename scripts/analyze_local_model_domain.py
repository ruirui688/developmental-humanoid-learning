"""Development-only model-domain and conditional free-rollout diagnostics.

Uses recorded native states, requested inputs and frozen saved model snapshots.
No physics, fitting, model selection, simulator queries or held-out data access.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
import zipfile

HORIZONS = (1, 2, 5, 15)
CORE = {"metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip"}
FIELDS = ("qref_rad", "dt_seconds", "features", "initial_coefficients", "initial_covariance_scale", "forgetting_factor", "coefficients", "covariance", "dtype")
LINEAR_FEATURES = ["v", "q-qref", "requested_torque", "1"]
HINGE_FEATURES = ["v", "q-qref", "requested_torque", "sign(u)*max(abs(u)-0.25,0)", "1"]
POSES = ("supine", "prone", "left_side", "right_side")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_outputs(output, archives):
    output = Path(output).resolve()
    windows = output.with_name(output.stem + ".windows.jsonl.gz")
    for candidate in (output, windows):
        if candidate.exists():
            raise ValueError(f"Refusing to overwrite output: {candidate}")
        if any(candidate.is_relative_to(Path(path).resolve()) for path in archives):
            raise ValueError("Diagnostic outputs must be outside input archives.")
    return output, windows


def verify_archive(path):
    path = Path(path).resolve()
    metadata = load_json(path / "metadata.json")
    if metadata.get("split") != "development":
        raise ValueError("Model-domain analysis only accepts development archives; held-out data cannot select a model.")
    if metadata.get("pose") not in POSES or type(metadata.get("joint_index")) is not int or not 0 <= metadata["joint_index"] < 8:
        raise ValueError("Unknown pose or joint mapping.")
    manifest = load_json(path / "manifest.json")
    names = {file.name for file in path.iterdir() if file.is_file() and file.name != "manifest.json"}
    if not CORE.issubset(manifest) or set(manifest) != names:
        raise ValueError("Manifest must cover every input file and all core archive files.")
    for name, expected in manifest.items():
        if Path(name).name != name or sha(path / name) != expected:
            raise ValueError(f"Manifest hash mismatch or invalid filename: {name}")
    with zipfile.ZipFile(path / "source_snapshot.zip") as source:
        hashes = metadata["source_sha256"]
        if len(source.namelist()) != len(set(source.namelist())) or set(source.namelist()) != set(hashes):
            raise ValueError("Source snapshot coverage mismatch.")
        for name, expected in hashes.items():
            if hashlib.sha256(source.read(name)).hexdigest() != expected:
                raise ValueError(f"Source snapshot hash mismatch: {name}")
    return metadata, {**manifest, "manifest.json": sha(path / "manifest.json")}


def snapshot_model(snapshot):
    if snapshot is None:
        return None
    features = snapshot["features"]
    if features not in (LINEAR_FEATURES, HINGE_FEATURES):
        raise ValueError("Unsupported model feature definition.")
    count = len(features)
    keys = FIELDS + (("hinge_threshold_nm", "hinge_threshold_updates", "hinge_structure_prior") if count == 5 else ())
    record = {key: snapshot[key] for key in keys}
    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if fingerprint != snapshot["parameter_fingerprint"]:
        raise ValueError("Saved model fingerprint mismatch.")
    if len(snapshot["coefficients"]) != count or not all(finite(value) for value in snapshot["coefficients"]):
        raise ValueError("Saved model has invalid coefficients.")
    if not finite(snapshot["qref_rad"]) or snapshot["dt_seconds"] != .02:
        raise ValueError("Expected fixed 20 ms model interval and finite qref.")
    if count == 5 and (snapshot["hinge_threshold_nm"] != .25 or snapshot["hinge_threshold_updates"] != 0):
        raise ValueError("Hinge threshold must retain its frozen structure prior.")
    return {"theta": snapshot["coefficients"], "qref": snapshot["qref_rad"], "dt": snapshot["dt_seconds"], "dimension": count, "snapshot_sha256": fingerprint, "update_count": snapshot["update_count"], "trainable_snapshot": snapshot["trainable"]}


def features(model, q, v, torque):
    values = [v, q - model["qref"], torque]
    if model["dimension"] == 5:
        sign = 1. if torque > 0 else (-1. if torque < 0 else 0.)
        values.append(sign * max(abs(torque) - .25, 0.))
    values.append(1.)
    return values


def predict(model, q, v, torque):
    next_v = sum(a * b for a, b in zip(model["theta"], features(model, q, v, torque)))
    next_q = q + model["dt"] * next_v
    if not finite(next_q) or not finite(next_v):
        raise ValueError("Model rollout became nonfinite.")
    return next_q, next_v


def free_rollout(model, q, v, requests):
    result = []
    for torque in requests:
        if model is None:  # Independent constant-velocity baseline.
            q = q + .02 * v
        else:
            q, v = predict(model, q, v, torque)
        result.append((q, v))
    return result


def amplitude_bin(torque):
    magnitude = abs(torque)
    if magnitude == 0:
        return "zero"
    for upper in (.125, .25, .375, .5):
        if magnitude <= upper:
            return "abs_u<=" + str(upper)
    return "outside_permission"


def state_bin(value, edges):
    for upper in edges:
        if abs(value) <= upper:
            return "abs<=" + str(upper)
    return "abs>" + str(edges[-1])


def row_problem(row, joint):
    if row is None:
        return "missing_control_row"
    if "collector_exception" in row:
        return "collector_exception"
    if row.get("invalid_numeric_fields"):
        return "invalid_numeric_marker"
    try:
        if row["diagnostics"]["executed_substeps"] != 10:
            return "partial_physics_interval"
        if not finite(row["diagnostics"]["time"]):
            return "invalid_physical_time"
        for key in ("joint_position", "joint_velocity"):
            if len(row["observation_before"][key]) != 8 or len(row["observation_after"][key]) != 8:
                return "invalid_native_shape"
            if not all(finite(value) for value in row["observation_before"][key] + row["observation_after"][key]):
                return "invalid_native_value"
        request = row["requested_torque"]
        if len(request) != 8 or not all(finite(value) and abs(value) <= .5 for value in request):
            return "invalid_requested_input"
        if any(value != 0. for index, value in enumerate(request) if index != joint):
            return "nontarget_requested_input"
    except (KeyError, IndexError, TypeError):
        return "missing_native_transition"
    return None


def valid_window(indexed, start, horizon, joint):
    rows = [indexed.get(index) for index in range(start, start + horizon)]
    for offset, row in enumerate(rows):
        problem = row_problem(row, joint)
        if problem:
            return None, problem
        if row["step_index"] != start + offset:
            return None, "nonconsecutive_step_index"
        if offset:
            previous = rows[offset - 1]
            if row["phase"] != previous["phase"]:
                return None, "crossed_phase_boundary"
            if row["observation_before"] != previous["observation_after"]:
                return None, "native_state_discontinuity"
            if abs(row["diagnostics"]["time"] - previous["diagnostics"]["time"] - .02) > 1e-10:
                return None, "physical_time_discontinuity"
            if previous["diagnostics"]["terminated"]:
                return None, "continued_after_termination"
    return rows, None


class Errors:
    def __init__(self):
        self.count = self.path_count = 0
        self.q2 = self.v2 = self.q_path2 = self.v_path2 = 0.
        self.q_bias = self.v_bias = self.max_q = self.max_v = 0.

    def add(self, predicted, truth):
        q_errors = [p[0] - actual[0] for p, actual in zip(predicted, truth)]
        v_errors = [p[1] - actual[1] for p, actual in zip(predicted, truth)]
        q, v = q_errors[-1], v_errors[-1]
        self.count += 1
        self.path_count += len(truth)
        self.q2 += q * q
        self.v2 += v * v
        self.q_bias += q
        self.v_bias += v
        self.max_q = max(self.max_q, abs(q))
        self.max_v = max(self.max_v, abs(v))
        self.q_path2 += sum(value * value for value in q_errors)
        self.v_path2 += sum(value * value for value in v_errors)

    def result(self):
        return {"valid_prediction_windows": self.count, "path_endpoint_samples": self.path_count, "terminal_q_rmse_rad": None if not self.count else math.sqrt(self.q2 / self.count), "terminal_v_rmse_rad_s": None if not self.count else math.sqrt(self.v2 / self.count), "path_q_rmse_rad": None if not self.path_count else math.sqrt(self.q_path2 / self.path_count), "path_v_rmse_rad_s": None if not self.path_count else math.sqrt(self.v_path2 / self.path_count), "terminal_q_bias_rad": None if not self.count else self.q_bias / self.count, "terminal_v_bias_rad_s": None if not self.count else self.v_bias / self.count, "maximum_terminal_q_error_rad": None if not self.count else self.max_q, "maximum_terminal_v_error_rad_s": None if not self.count else self.max_v}


def coverage(rows, joint, qref):
    values = {"q_offset_rad": [], "v_rad_s": [], "requested_u_nm": []}
    bins = Counter()
    for row in rows:
        if row_problem(row, joint):
            continue
        q = row["observation_before"]["joint_position"][joint] - qref
        v = row["observation_before"]["joint_velocity"][joint]
        u = row["requested_torque"][joint]
        values["q_offset_rad"].append(q)
        values["v_rad_s"].append(v)
        values["requested_u_nm"].append(u)
        bins[(amplitude_bin(u), state_bin(q, (.02, .05, .1, .15)), state_bin(v, (.02, .05, .1, .2, .5)))] += 1
    return {"full_control_transitions": len(values["q_offset_rad"]), "axis_aligned_ranges": {name: {"minimum": min(items, default=None), "maximum": max(items, default=None)} for name, items in values.items()}, "exact_requested_values_nm": sorted(set(values["requested_u_nm"])), "bins": [{"amplitude_bin": key[0], "q_offset_bin": key[1], "velocity_bin": key[2], "samples": count} for key, count in sorted(bins.items())]}


def analyze_archive(path, metadata, window_stream):
    joint = metadata["joint_index"]
    episodes = load_json(path / "episodes.json")
    results = {row["seed"]: row for row in load_json(path / "seed_results.json")}
    groups = defaultdict(list)
    with gzip.open(path / "trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            groups[row["trial_id"]].append(row)
    trials, total_windows = [], 0
    for episode in episodes:
        seed, kind = episode["seed"], episode["kind"]
        trial_id = episode.get("trial_id", f"seed{seed}_{kind}")
        rows = groups.get(trial_id, [])
        indexed = {}
        for row in rows:
            if type(row.get("step_index")) is int:
                if row["step_index"] in indexed:
                    raise ValueError(f"Duplicate control index in {trial_id}")
                indexed[row["step_index"]] = row
        sr = results.get(seed, {})
        nominal = snapshot_model(sr.get("initial_model"))
        learned = snapshot_model(sr.get("learned_model"))
        models = {"velocity_persistence": None}
        if nominal is not None:
            models["nominal"] = nominal
        if learned is not None:
            models["learned_final_snapshot"] = learned
        reference_model = nominal or learned
        qref = None if reference_model is None else reference_model["qref"]
        planned = episode.get("maximum_control_steps", 400 if kind == "calibration" else (200 if kind == "prediction" else 300))
        active = [row for index, row in sorted(indexed.items()) if index >= 100]
        complete = (episode["status"] == "completed" and episode["control_steps"] == planned
                    and episode["physics_steps"] == planned * 10 and set(indexed) == set(range(planned))
                    and all(row_problem(row, joint) is None and not row["diagnostics"]["terminated"] for row in indexed.values()))
        calibration_rows = [row for row in groups.get(f"seed{seed}_calibration", []) if type(row.get("step_index")) is int and row["step_index"] >= 100]
        cal_coverage = None if qref is None else coverage(calibration_rows, joint, qref)
        trial_coverage = None if qref is None else coverage(active, joint, qref)
        outside = Counter()
        if cal_coverage is not None:
            for row in active:
                if row_problem(row, joint):
                    continue
                value_map = {"q_offset_rad": row["observation_before"]["joint_position"][joint] - qref, "v_rad_s": row["observation_before"]["joint_velocity"][joint], "requested_u_nm": row["requested_torque"][joint]}
                for name, value in value_map.items():
                    bounds = cal_coverage["axis_aligned_ranges"][name]
                    if bounds["minimum"] is not None and not bounds["minimum"] - 1e-12 <= value <= bounds["maximum"] + 1e-12:
                        outside[name] += 1
        horizon_reports = []
        for horizon in HORIZONS:
            aggregate = {name: Errors() for name in models}
            cohorts = defaultdict(lambda: {name: Errors() for name in models})
            reasons, bad_models = Counter(), Counter()
            expected = max(planned - 100 - horizon + 1, 0)
            valid = 0
            for start in range(100, planned - horizon + 1):
                segment, problem = valid_window(indexed, start, horizon, joint)
                if problem:
                    reasons[problem] += 1
                    continue
                valid += 1
                first, last = segment[0], segment[-1]
                q0, v0 = first["observation_before"]["joint_position"][joint], first["observation_before"]["joint_velocity"][joint]
                requests = [row["requested_torque"][joint] for row in segment]
                truth = [(row["observation_after"]["joint_position"][joint], row["observation_after"]["joint_velocity"][joint]) for row in segment]
                key = (amplitude_bin(requests[0]), "unknown_reference" if qref is None else state_bin(q0 - qref, (.02, .05, .1, .15)), state_bin(v0, (.02, .05, .1, .2, .5)))
                forecasts = {}
                for name, model in models.items():
                    try:
                        prediction = free_rollout(model, q0, v0, requests)
                        aggregate[name].add(prediction, truth)
                        cohorts[key][name].add(prediction, truth)
                        forecasts[name] = {"terminal_q_rad": prediction[-1][0], "terminal_v_rad_s": prediction[-1][1], "terminal_q_error_rad": prediction[-1][0] - truth[-1][0], "terminal_v_error_rad_s": prediction[-1][1] - truth[-1][1], "predicted_native_qv_path": prediction}
                    except (ValueError, OverflowError):
                        bad_models[name] += 1
                        forecasts[name] = {"invalid_prediction": True}
                window_stream.write(json.dumps({"archive_path": str(path), "source_commit": metadata["source_commit"], "seed": seed, "trial_id": trial_id, "kind": kind, "horizon_control_steps": horizon, "start_control_index": start, "end_control_index": start + horizon - 1, "start_time_seconds": first["diagnostics"]["time"] - .02, "end_time_seconds": last["diagnostics"]["time"], "initial_native_q_rad": q0, "initial_native_v_rad_s": v0, "terminal_native_q_rad": truth[-1][0], "terminal_native_v_rad_s": truth[-1][1], "recorded_requested_sequence_nm": requests, "conditioned_on_logged_future_requests": horizon > 1, "trial_complete": complete, "ends_in_termination": bool(last["diagnostics"]["terminated"]), "start_amplitude_bin": key[0], "start_q_offset_bin": key[1], "start_velocity_bin": key[2], "model_forecasts": forecasts}, allow_nan=False) + "\n")
                total_windows += 1
            horizon_reports.append({"horizon_control_steps": horizon, "expected_windows_from_planned_active_duration": expected, "valid_physical_windows": valid, "excluded_windows": expected - valid, "exclusion_reasons": dict(reasons), "invalid_model_prediction_windows": dict(bad_models), "predictors": {name: errors.result() for name, errors in aggregate.items()}, "start_state_cohorts": [{"amplitude_bin": key[0], "q_offset_bin": key[1], "velocity_bin": key[2], "predictors": {name: errors.result() for name, errors in values.items()}} for key, values in sorted(cohorts.items())]})
        trials.append({"seed": seed, "kind": kind, "trial_id": trial_id, "status": episode["status"], "reason": episode.get("reason"), "planned_control_steps": planned, "observed_control_rows": len(indexed), "control_calls_attempted": episode["control_calls_attempted"], "completed_control_steps": episode["control_steps"], "physics_steps": episode["physics_steps"], "complete_trial": complete, "prefix_rows_excluded_from_prediction": sum(index < 100 for index in indexed), "collector_exception_rows": sum("collector_exception" in row for row in rows), "learned_final_calibration_in_sample": kind == "calibration", "saved_model_updates": None if learned is None else learned["update_count"], "model_snapshot_scope": "unavailable" if learned is None else ("complete_calibration" if learned["update_count"] == 300 else "partial_calibration"), "nominal_model": nominal, "learned_model": learned, "calibration_coverage": cal_coverage, "trial_coverage": trial_coverage, "outside_calibration_axis_aligned_ranges_counts": dict(outside), "horizons": horizon_reports})
    return {"path": str(path), "split": metadata["split"], "variant": metadata.get("variant", "linear"), "source_commit": metadata["source_commit"], "source_dirty": metadata.get("source_dirty", bool(metadata.get("source_status"))), "pose": metadata["pose"], "joint_index": joint, "archive_complete_flag": metadata.get("complete"), "complete_trials": sum(trial["complete_trial"] for trial in trials), "planned_trials": len(episodes), "window_records": total_windows, "trials": trials}


def main():
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    started_utc = datetime.now(timezone.utc).isoformat()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output, windows = validate_outputs(args.output, args.archives)
        paths = [Path(value).resolve() for value in args.archives]
        if len(set(paths)) != len(paths):
            raise ValueError("Duplicate input archive.")
        verified = [(path, *verify_archive(path)) for path in paths]
        output.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(windows, "xt", encoding="utf-8") as stream:
            archives = []
            for path, metadata, hashes in verified:
                report = analyze_archive(path, metadata, stream)
                if any(sha(path / name) != expected for name, expected in hashes.items()):
                    raise ValueError("Input archive changed during analysis.")
                report["input_hashes"] = hashes
                archives.append(report)
        report = {"schema_version": 2, "purpose": __doc__, "analysis_script_sha256": sha(Path(__file__)), "window_records_path": str(windows), "window_records_sha256": sha(windows), "horizons_control_steps": list(HORIZONS), "future_input_semantics": "Multi-step forecasts are offline diagnostics conditioned on the recorded future requested sequence. They do not assume an online controller knows future feedback-selected actions.", "prefix_semantics": "The reference is established at the paid prefix endpoint; prefix interactions remain in the input budget but are excluded from local-model forecast windows.", "persistence_semantics": "Keep initial velocity fixed and advance position by dt times that velocity; no learned coefficients or future states.", "sample_semantics": "Windows overlap, share seeds and reuse controller trajectories; their counts are denominators, not independent experimental samples.", "coverage_semantics": "Calibration ranges are axis-aligned feature envelopes, not convex hulls, identifiable contact modes or safety sets. Amplitude and state cohorts label window start only.", "calibration_semantics": "Final-model predictions on calibration are in-sample post-fit diagnostics, distinct from the recorded predict-before-update online errors.", "model_selection": "No model is fitted or selected by this script; only development data are accepted.", "archives": archives}
        report["execution"] = {
            "started_utc": started_utc,
            "wall_seconds": time.perf_counter() - wall_start,
            "cpu_seconds": time.process_time() - cpu_start,
            "timing_scope": "main entry through input verification, analysis, window-file writing and hashing; excludes module import and final report JSON writing",
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "dependencies": "Python standard library only; no simulator or numerical fitting library imported",
            "physical_simulation_calls": 0,
            "model_parameter_updates": 0,
        }
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError, IndexError, zipfile.BadZipFile) as error:
        parser.error(str(error))
    print(json.dumps({"output": str(output), "windows": str(windows), "window_records": sum(item["window_records"] for item in archives), "analysis_script_sha256": report["analysis_script_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
