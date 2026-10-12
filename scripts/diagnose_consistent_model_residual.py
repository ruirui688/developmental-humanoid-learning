"""IV2D: one saved state-residual and coordinate-box diagnostic, no model calls."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import traceback
import zipfile

import numpy as np

SOURCE_PATH = "scripts/diagnose_consistent_model_residual.py"
PROTOCOL_PATH = "docs/CONSISTENT_MODEL_RESIDUAL_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 7809, "sha256": "cc950a5383ca22f40c19b345cd24e034f66de3f21c6d4011df1ba8a599b31f3e"}
SOURCE_PATHS = (SOURCE_PATH, PROTOCOL_PATH)
INPUT_BASE = "results/cpu_validation/2026-10-12_consistent_action_state/raw"
IV2_SOURCE = "d8491b2e0f8b3bae649b8bf9a297bebba7f76270"
INPUT_PINS = {
    "run.json": {"bytes": 1145452, "sha256": "a6fd68bb909ac8d8607986aeb55918d76dce18b51f8a0bbcd2d93b8caef2a0ec"},
    "models.json": {"bytes": 21758, "sha256": "96e94bc63311262878114354e1fb4f084564e5116cf14435ee47936415176dcd"},
    "moments.json": {"bytes": 1425018, "sha256": "a199bb517cafc059bfcf6af23b9dba258f4d4bcf31787c363ea255ebced7c2ea"},
    "predictions.jsonl.gz": {"bytes": 10936879, "sha256": "de32524abd8f5b8a7f45d6dbc92158143c67b5fe05893656401c38dddfd58685"},
}
SEEDS = (8101, 8102, 8103)
MODELS = ("cold", "oldlearned", "IV1", "newmatched")
HORIZONS = (1, 10, 20, 50, 150)
STATE_COLUMNS = (0, 1, 2, 3, 8)
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
    "c4_scientific_validation": False, "c4_contact_scientific_validation": False,
    "c5_scientific_dependency_released": False, "control_candidate_opened": False}
BOUNDS = {"training_pairs_per_seed": 2000, "state_matmul_calls": 6,
    "training_state_velocity_scalar_outputs": 24000, "reused_training_Y_scalar_uses": 24000,
    "saved_prediction_records": 5772, "saved_endpoint_error_scalar_uses": 23088,
    "native_H1_unique_origin_points": 300, "native_H1_box_scalar_uses": 1200,
    "recursive_conditional_input_points": 249360, "recursive_box_scalar_uses": 997440,
    "new_physics": 0, "fit": 0, "model_predict": 0, "RLS": 0, "old_gate_recomputations": 0}


def safe(value):
    if isinstance(value, dict):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return safe(value.tolist())
    if isinstance(value, np.generic):
        return safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return {"nonfinite_float": str(value)}
    return value


def pin(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def finite(name, value, shape):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(name+"_must_be_finite_"+str(shape))
    return array


def error_summary(errors, cost, *, training=False):
    """New fixed signed-error statistics; fresh archived RMSE is not computed."""
    array = np.asarray(errors, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] != 2 or not np.isfinite(array).all():
        raise ValueError("complete_nonempty_finite_two_axis_error_population_required")
    cost["error_summary_attempts"] += 1
    with np.errstate(over="raise", invalid="raise"):
        result = {"count": len(array), "bias_axis": np.mean(array, axis=0),
            "MAE_axis": np.mean(np.abs(array), axis=0),
            "population_std_axis": np.std(array, axis=0, ddof=0),
            "max_absolute_axis": np.max(np.abs(array), axis=0)}
        if training:
            result["training_RMSE_axis"] = np.sqrt(np.mean(np.square(array), axis=0))
    for key, value in result.items():
        if key != "count":
            finite(key, value, (2,))
    cost["error_summary_returns"] += 1
    cost["error_summary_axis_statistic_outputs"] += 10 if training else 8
    return safe(result)


def state_residual(psi, labels, state, cost):
    """The common frozen action was already subtracted from the saved Y."""
    n = len(psi)
    psi, labels = finite("saved_Psi", psi, (n, 5)), finite("saved_Y", labels, (n, 2))
    state = finite("frozen_state_2x5", state, (2, 5))
    cost["state_matmul_attempts"] += 1
    cost["reused_training_Y_scalar_uses"] += labels.size
    with np.errstate(over="raise", invalid="raise"):
        prediction = finite("training_state_prediction", psi @ state.T, (n, 2))
        residual = finite("training_prediction_minus_saved_Y", prediction-labels, (n, 2))
    cost["state_matmul_returns"] += 1
    cost["training_state_velocity_scalar_outputs"] += prediction.size
    cost["training_state_coefficient_scalar_uses"] += n*10
    cost["training_residual_scalar_outputs"] += residual.size
    return residual


def box_summary(points, bounds, cost, scope):
    """A coordinate box is descriptive coverage, not a physical support domain."""
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[0] == 0 or points.shape[1] != 4 or not np.isfinite(points).all():
        raise ValueError("complete_nonempty_finite_state_box_population_required")
    bounds = finite("training_coordinate_box", bounds, (2, 4))
    if np.any(bounds[0] > bounds[1]):
        raise ValueError("ordered_saved_training_box_required")
    cost[scope+"_box_attempts"] += 1
    with np.errstate(over="raise", invalid="raise"):
        outside = (points < bounds[0]) | (points > bounds[1])
        excess = np.maximum(np.maximum(bounds[0]-points, points-bounds[1]), 0.)
        maximum = finite("maximum_coordinate_box_excess", np.max(excess, axis=0), (4,))
    result = {"points": len(points), "outside_count_each_coordinate": np.sum(outside, axis=0).tolist(),
        "outside_any_coordinate_count": int(np.sum(np.any(outside, axis=1))),
        "maximum_excess_each_coordinate": maximum.tolist(), "boundary_is_inside": True}
    cost[scope+"_box_returns"] += 1
    cost[scope+"_input_points"] += len(points)
    cost[scope+"_box_scalar_uses"] += points.size
    return result


def saved_recursive_inputs(row, qref):
    h = row["horizon"]
    qref = finite("frozen_qref2", qref, (2,))
    q0 = finite("saved_native_start_q2", row["model_input"]["q2"], (2,))
    v0 = finite("saved_native_start_v2", row["model_input"]["v2"], (2,))
    qpath = finite("saved_predicted_q_path", row["predicted_q_path"], (h, 2))
    vpath = finite("saved_predicted_v_path", row["predicted_v_path"], (h, 2))
    # Path endpoint H is an output, so it is excluded from H consumed inputs.
    with np.errstate(over="raise", invalid="raise"):
        return finite("saved_recursive_psi4_inputs", np.column_stack((
            np.vstack((v0, vpath[:-1])), np.vstack((q0, qpath[:-1]))-qref)), (h, 4))


def source_gate(repo, commit, cost):
    if Path(__file__).resolve() != (repo / SOURCE_PATH).resolve() or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("canonical_runner_and_exact_source_commit_required")
    def git(args):
        cost["source_git_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["source_git_returns"] += 1
        cost["source_git_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("source_git_query_failed")
        return result.stdout
    if git(["rev-parse", "HEAD"]).decode().strip() != commit or git(["status", "--porcelain"]):
        raise ValueError("exact_clean_source_HEAD_required")
    blobs = {}
    for name in SOURCE_PATHS:
        cost["source_file_reads"] += 1
        blobs[name] = (repo / name).read_bytes()
        cost["source_bytes_read"] += len(blobs[name])
        if blobs[name] != git(["show", commit+":"+name]):
            raise ValueError("source_bytes_differ:"+name)
    if PROTOCOL_PIN is None or pin(blobs[PROTOCOL_PATH]) != PROTOCOL_PIN:
        raise ValueError("frozen_protocol_identity_required")
    return {"commit": commit, "clean_committed_bytes_verified": True,
        "files": {name: pin(blob) for name, blob in blobs.items()}}, blobs


class Diagnostic:
    def __init__(self, repo):
        self.repo, self.cost, self.context = repo, Counter(), None
        self.input_identities, self.source, self.boxes = {}, None, {}
        self.original_gate, self.model_fingerprints = None, {}
        self.training = [{"seed": seed, "model": name, "planned_pairs": 2000, "status": "not_attempted"}
            for seed in SEEDS for name in ("IV1", "newmatched")]
        self.groups = [{"seed": seed, "model": name, "horizon": h, "planned_origins": len(range(0, 1000-h+1, 10)),
            "planned_recursive_inputs": h*len(range(0, 1000-h+1, 10)), "status": "not_attempted"}
            for seed in SEEDS for h in HORIZONS for name in MODELS]
        self.native_H1 = [{"seed": seed, "planned_unique_native_origins": 100, "status": "not_attempted"} for seed in SEEDS]

    def load(self, filename):
        self.context = {"stage": "input_identity", "filename": filename}
        self.cost["IV2_input_file_read_attempts"] += 1
        blob = (self.repo / INPUT_BASE / filename).read_bytes()
        self.cost["IV2_input_file_read_returns"] += 1
        self.cost["IV2_input_bytes_read"] += len(blob)
        self.cost["IV2_input_hash_attempts"] += 1
        self.input_identities[filename] = pin(blob)
        self.cost["IV2_input_hash_returns"] += 1
        self.cost["IV2_input_bytes_hashed"] += len(blob)
        if self.input_identities[filename] != INPUT_PINS[filename]:
            raise ValueError("fixed_IV2_input_identity_differs:"+filename)
        return blob

    def parse(self, blob):
        self.cost["IV2_JSON_parse_attempts"] += 1
        result = json.loads(blob)
        self.cost["IV2_JSON_parse_returns"] += 1
        return result

    def run(self):
        blobs = {name: self.load(name) for name in INPUT_PINS}
        run, models, moments = (self.parse(blobs[name]) for name in ("run.json", "models.json", "moments.json"))
        if (run.get("experiment_id") != "IV2" or run.get("status") != "completed" or run.get("first_failure") is not None
            or run.get("source", {}).get("commit") != IV2_SOURCE or run.get("metrics", {}).get("complete_population") is not True
            or run.get("config", {}).get("seeds") != list(SEEDS) or run.get("config", {}).get("models") != list(MODELS)
            or run.get("config", {}).get("H") != list(HORIZONS)
            or set(models) != {str(seed) for seed in SEEDS} or set(moments) != {str(seed) for seed in SEEDS}):
            raise ValueError("completed_fixed_IV2_source_and_population_required")
        self.original_gate = run["metrics"].get("iv2_prediction_gate_passed")
        for seed in SEEDS:
            self.context = {"stage": "frozen_model_identity", "seed": seed}
            group = models[str(seed)]
            if set(group) != set(MODELS):
                raise ValueError("all_four_saved_frozen_models_required")
            qref = finite("common_qref2", group["IV1"]["qref_rad"], (2,))
            for name in MODELS:
                model, identity = group[name], run.get("model_fingerprints", {}).get(str(seed), {}).get(name, {})
                fingerprint = model.get("parameter_fingerprint")
                if (not isinstance(fingerprint, str) or model.get("fingerprint_before_prediction") != fingerprint
                    or identity.get("parameter_fingerprint") != fingerprint or identity.get("fingerprint_before_prediction") != fingerprint
                    or finite("same_model_qref2", model["qref_rad"], (2,)).tobytes() != qref.tobytes()):
                    raise ValueError("frozen_model_fingerprints_and_common_qref_must_match_saved_run")
                self.model_fingerprints[(seed, name)] = fingerprint
                self.cost["saved_model_identity_checks"] += 1
            first = finite("IV1_theta", group["IV1"]["coefficients"], (2, 9))
            matched = finite("newmatched_theta", group["newmatched"]["coefficients"], (2, 9))
            if first[:, 4:8].tobytes() != matched[:, 4:8].tobytes():
                raise ValueError("common_fixed_action8_bytes_required_before_any_matmul")
            self.cost["fixed_action8_identity_checks"] += 1
        for seed in SEEDS:
            self.context = {"stage": "training_native_residual", "seed": seed}
            record = moments[str(seed)]
            psi = finite("complete_training_Psi", record["Psi_native_state_5"], (2000, 5))
            labels = finite("complete_training_Y", record["Y_native_minus_fixed_action_2"], (2000, 2))
            if record.get("samples") != 2000 or record.get("fit_attempted") is not True or record.get("fit", {}).get("rank") != 5:
                raise ValueError("complete_saved_state_fit_population_required")
            self.cost["training_Psi_scalar_reads"] += psi.size
            self.cost["training_Y_scalar_reads"] += labels.size
            self.boxes[seed] = np.vstack((np.min(psi[:, :4], axis=0), np.max(psi[:, :4], axis=0)))
            self.cost["training_box_bound_scalar_outputs"] += 8
            for slot in (item for item in self.training if item["seed"] == seed):
                self.context.update(model=slot["model"])
                slot["status"] = "attempted"
                theta = finite("saved_frozen_theta", models[str(seed)][slot["model"]]["coefficients"], (2, 9))
                slot.update(status="completed", error=error_summary(state_residual(psi, labels, theta[:, STATE_COLUMNS], self.cost), self.cost, training=True),
                    residual_sign="state_prediction_minus_Y_equals_full_next_v_error_with_common_fixed_action",
                    parameter_fingerprint=models[str(seed)][slot["model"]]["parameter_fingerprint"])
        buffers = {(slot["seed"], slot["model"], slot["horizon"]): {"q": [], "v": [], "inputs": [], "origins": set()}
            for slot in self.groups}
        native_points = {seed: [] for seed in SEEDS}
        native_H1_identities = {}
        expected_keys = {(seed, name, h, origin) for seed in SEEDS for h in HORIZONS for name in MODELS
            for origin in range(0, 1000-h+1, 10)}
        seen = set()
        with gzip.GzipFile(fileobj=io.BytesIO(blobs["predictions.jsonl.gz"]), mode="rb") as stream:
            for line_index, line in enumerate(stream):
                self.context = {"stage": "saved_prediction_residual", "line_index": line_index}
                self.cost["IV2_gzip_decoded_lines"] += 1
                self.cost["IV2_gzip_decoded_bytes"] += len(line)
                row = self.parse(line)
                key = tuple(row.get(name) for name in ("seed", "model", "horizon", "origin_active_index"))
                if key not in expected_keys or key in seen or row.get("status") != "completed" or row.get("available") is not True:
                    raise ValueError("complete_unique_saved_prediction_population_required")
                seen.add(key)
                seed, name, h, origin = key
                self.context.update(seed=seed, model=name, horizon=h, origin_active_index=origin)
                if row.get("model_fingerprint") != self.model_fingerprints[(seed, name)]:
                    raise ValueError("saved_prediction_model_fingerprint_must_match_frozen_snapshot")
                self.cost["saved_prediction_fingerprint_checks"] += 1
                qref = models[str(seed)][name]["qref_rad"]
                inputs = saved_recursive_inputs(row, qref)
                buffer = buffers[(seed, name, h)]
                buffer["q"].append(finite("saved_q_error", row["q_error_rad"], (2,)))
                buffer["v"].append(finite("saved_v_error", row["v_error_rad_s"], (2,)))
                buffer["inputs"].append(inputs)
                buffer["origins"].add(origin)
                self.cost["saved_prediction_record_returns"] += 1
                self.cost["saved_endpoint_error_scalar_uses"] += 4
                self.cost["saved_prediction_path_qv_scalar_reads"] += h*4
                self.cost["recursive_qrel_scalar_subtractions"] += h*2
                if h == 1:
                    native_identity = (finite("H1_native_q2_identity", row["model_input"]["q2"], (2,)).tobytes(),
                        finite("H1_native_v2_identity", row["model_input"]["v2"], (2,)).tobytes())
                    previous = native_H1_identities.setdefault((seed, origin), native_identity)
                    if previous != native_identity:
                        raise ValueError("same_H1_native_qv_origin_required_across_all_four_models")
                    self.cost["native_H1_cross_model_identity_scalar_uses"] += 4
                if name == "cold" and h == 1:
                    native_points[seed].append(inputs[0].copy())
        if seen != expected_keys:
            raise ValueError("all_5772_saved_predictions_required_no_partial_ranking")
        for slot in self.groups:
            seed, name, h = slot["seed"], slot["model"], slot["horizon"]
            self.context = {"stage": "fixed_saved_statistics", "seed": seed, "model": name, "horizon": h}
            buffer = buffers[(seed, name, h)]
            if len(buffer["origins"]) != slot["planned_origins"]:
                raise ValueError("complete_each_H_model_origin_population_required")
            slot["status"] = "attempted"
            original = next(item for item in run["seed_results"] if item["seed"] == seed)["prediction_scores"]["horizons"][str(h)]["models"][name]
            slot.update(status="completed", q_error=error_summary(buffer["q"], self.cost), v_error=error_summary(buffer["v"], self.cost),
                recursive_input_box=box_summary(np.concatenate(buffer["inputs"], axis=0), self.boxes[seed], self.cost, "recursive"),
                saved_origin_active_indices=sorted(buffer["origins"]),
                original_RMSE_transcribed={"q_axis_rad": original["q_rmse_axis_rad"], "v_axis_rad_s": original["v_rmse_axis_rad_s"], "recomputed": False})
            self.cost["original_RMSE_scalar_transcriptions"] += 4
        for slot in self.native_H1:
            seed = slot["seed"]
            self.context = {"stage": "native_H1_coordinate_box", "seed": seed}
            if len(native_points[seed]) != 100:
                raise ValueError("all_100_unique_native_H1_origins_required")
            slot.update(status="completed", box=box_summary(native_points[seed], self.boxes[seed], self.cost, "native_H1"),
                source="cold_H1_saved_native_start_one_per_origin_not_repeated_across_models")
        if (self.cost["state_matmul_returns"] != 6 or self.cost["reused_training_Y_scalar_uses"] != 24000
            or self.cost["training_state_velocity_scalar_outputs"] != 24000 or self.cost["saved_prediction_record_returns"] != 5772
            or self.cost["recursive_input_points"] != 249360 or self.cost["recursive_box_scalar_uses"] != 997440
            or self.cost["native_H1_input_points"] != 300):
            raise ValueError("complete_fixed_diagnostic_population_required")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output.exists() or output == repo or repo.is_relative_to(output) or (repo / INPUT_BASE).resolve().is_relative_to(output):
        parser.error("existing_or_repository_or_input_containing_output_refused")
    output.mkdir(parents=True, exist_ok=False)
    diagnostic, failure, status = Diagnostic(repo), None, "failed"
    wall, cpu = time.perf_counter(), time.process_time()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                diagnostic.source, blobs = source_gate(repo, args.source_commit, diagnostic.cost)
                with zipfile.ZipFile(output / "source.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, blob in blobs.items():
                        archive.writestr(name, blob)
                diagnostic.cost["source_archive_bytes_written"] = (output / "source.zip").stat().st_size
                diagnostic.run()
                status = "completed"
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "context": diagnostic.context, "traceback": traceback.format_exc()}
                traceback.print_exc()
    diagnostic.cost["wall_seconds"], diagnostic.cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    analysis = {"training_state_residuals": diagnostic.training, "saved_endpoint_error_and_recursive_box": diagnostic.groups,
        "native_H1_unique_origin_box": diagnostic.native_H1, "training_coordinate_boxes": safe(diagnostic.boxes),
        "box_coordinate_order": ["v0", "v1", "q_minus_qref0", "q_minus_qref1"],
        "recursive_input_point_scope": "overlapping_horizon_origin_model_conditional_points_not_unique_physical_states",
        "limits": ["coordinate_box_does_not_establish_real_support_domain", "saved_error_growth_and_box_exits_are_correlations_not_unique_causes",
                   "training_and_fresh_populations_and_actions_differ", "no_new_model_or_controller_adopted"], **FLAGS}
    try:
        (output / "analysis.json").write_text(json.dumps(safe(analysis), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    except BaseException as exc:
        detail = {"stage": "analysis_payload_write", "type": type(exc).__name__, "message": str(exc)}
        if failure is None:
            failure, status = detail, "failed"
        else:
            failure.setdefault("secondary_payload_failures", []).append(detail)
    report = {"experiment_id": "IV2D", "status": status, "first_failure": failure, "source": diagnostic.source,
        "input_source": {"base": INPUT_BASE, "IV2_source_commit": IV2_SOURCE, "required_pins": INPUT_PINS, "actual_identities": diagnostic.input_identities},
        "planned_upper_bounds": BOUNDS, "cost": dict(diagnostic.cost), "analysis_file": "analysis.json",
        "original_IV2_prediction_gate_transcribed": diagnostic.original_gate,
        "model_fingerprints_transcribed": {str(seed): {name: diagnostic.model_fingerprints.get((seed, name)) for name in MODELS} for seed in SEEDS},
        "config": {"seeds": SEEDS, "models": MODELS, "H": HORIZONS, "stride": 10,
            "training_pairs_per_seed": 2000, "population_std_ddof": 0, "coordinate_box_boundary": "inside"},
        "complete_population": status == "completed", "runtime": {"python": sys.version, "numpy": np.__version__,
            "platform": platform.platform(), "cpu": platform.processor() or "unknown", "logical_cpu_count": os.cpu_count(), "GPU_used": False},
        "new_physics_controls": 0, "new_physics_substeps": 0, "fit_attempts": 0, "model_predict_calls": 0,
        "RLS_updates": 0, "source_trace_reads": 0, "old_gate_recomputations": 0, "fresh_RMSE_recomputations": 0,
        "internal_numpy_matmul_and_reduction_work": "unmeasured_unknown_not_zero", "unmeasured_import_IO": "unknown_not_zero",
        "timing_excludes": "final_JSON_encoding_and_payload_writes", "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"experiment_id": "IV2D", "status": status, "output": str(output), "cost": dict(diagnostic.cost), "failure": failure}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
