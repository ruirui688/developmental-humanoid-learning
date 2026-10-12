"""EF1D: one saved H1 error-to-request-scale diagnostic, with no model calls.

The local Moore-Penrose mapping is descriptive. It is neither a controller nor
a constrained root search. All logged-request adjacent closed boxes are kept.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import gzip
import hashlib
import io
from itertools import product
import json
import math
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import time
import traceback
import zipfile

import numpy as np


SOURCE_PATH = "scripts/diagnose_model_action_error.py"
PROTOCOL_PATH = "docs/MODEL_ACTION_ERROR_DIAGNOSTIC_PROTOCOL.md"
PROTOCOL_PIN = {'bytes': 10242, 'sha256': '1f9af9e89c1127e0210fdc99b805c6777b2f1f8214ed381cdee71fe907c94949'}
EF1B_SOURCE_COMMIT = "f9f500706364aab32bd18047266d4b06358e4473"
EF1B_DELIVERY_COMMIT = "5b577a939109a6e32119007248bdcd201abc39f3"
ARCHIVE = "results/cpu_validation/2026-10-12_equilibrium_feedforward_control"
INPUT_PINS = {
    "raw/manifest.json": (8947, "f5917b3d988bc0365b4d6f21fa0dd6b3f3ee573b09792d0413f68ba9aa6bcd09"),
    "raw/run.json": (7067299, "b7612382fb517d87a581b6dd7585838dd5313233c2f491d840c7bcb3cc09f32b"),
    "raw/models.json": (60924, "3cfbd871c275a8f5d8a07615a239ee9e8192b5e93dcf35104cf61a01f6a6a992"),
    "raw/predictions.jsonl.gz": (18485641, "6e51dfb6d0823f6c55d1f055ba4eec2cf1d83c4b7c26a9ad0659962e7af55be8"),
    "raw/predictions.00001.jsonl.gz": (4261371, "9e884a3571bd47a5c5af83c6eb00fb0d2430fc35d9ced80fc0e609cf3c4aa5b2"),
    "audit_first/audit.json": (124900, "b666b01813669c3590afec2e5ccd21e969312a4e16238e0002329e7bba7ac630"),
}
SEEDS, METHODS = (8101, 8102, 8103), ("cold", "learned")
BOXES = ((-.5, -.25), (-.25, 0.), (0., .25), (.25, .5))
EPS = 128. * np.finfo(np.float64).eps
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
         "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
         "c4_contact_scientific_validation": False}
LIMITS = {"prediction_decoded_records": 11772, "H1_model_records": 2400,
          "paired_origins": 1200, "frozen_theta_scalars_read": 108,
          "independent_saved_error_scalar_uses": 4800,
          "closed_box_membership_checks": 38400,
          "jacobian_build_attempts": 9600, "svd_attempts": 9600,
          "minimum_norm_mapping_attempts": 9600,
          "branch_saved_error_scalar_uses": 19200,
          "jacobian_coefficient_scalar_uses": 76800,
          "jacobian_entry_scalars": 38400, "matvec_attempts": 28800,
          "singular_component_division_attempts": 19200}


def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def expected_pin(value):
    return {"bytes": value[0], "sha256": value[1]}


def safe(value):
    if isinstance(value, dict):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return safe(value.tolist())
    if isinstance(value, np.generic):
        return safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_float": str(value)}
    return value


def finite(name, value, shape):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(name+"_must_be_finite_shape_"+str(shape))
    return array


def matvec(matrix, vector, cost):
    cost["matvec_attempts"] += 1
    try:
        result = matrix @ vector
    except BaseException:
        cost["matvec_exceptions"] += 1
        raise
    cost["matvec_returns"] += 1
    return finite("matvec_result", result, (2,))


def diagnose_row(q, v, request, error, coefficients, ranges, *, cost, svd=None):
    """Keep every adjacent box; technical errors raise with the partial record."""
    result = {"q2": safe(q), "v2": safe(v), "logged_request2": safe(request),
              "saved_velocity_error2": safe(error), "branches": [],
              "interpretation": "model_internal_minimum_norm_scale_not_an_action_or_causal_gain"}
    current = None
    cost["row_algebra_attempts"] += 1
    try:
        q, v, request, error = (finite(name, value, (2,)) for name, value in
            (("q", q), ("v", v), ("request", request), ("saved_error", error)))
        theta, ranges = finite("theta", coefficients, (2, 9)), finite("public_ranges", ranges, (2, 2))
        if any(lower >= upper for lower, upper in ranges) or np.any(np.abs(request) > .5):
            raise ValueError("ordered_public_ranges_and_logged_permission_required")
        result["permission_margins_nm"] = [[float(u+.5), float(.5-u)] for u in request]
        for index, axes in enumerate(product(range(4), repeat=2)):
            bounds = tuple(BOXES[axis] for axis in axes)
            cost["closed_box_membership_checks"] += 1
            if not all(lower <= request[i] <= upper for i, (lower, upper) in enumerate(bounds)):
                continue
            current = {"index": index, "axis_branch_indices": axes, "bounds_nm": bounds,
                       "logged_box_margins_nm": [[float(request[i]-lower), float(upper-request[i])]
                                                  for i, (lower, upper) in enumerate(bounds)],
                       "status": "algebra_started"}
            result["branches"].append(current)
            cost["jacobian_build_attempts"] += 1
            cost["jacobian_coefficient_scalar_uses"] += 8
            cost["branch_saved_error_scalar_uses"] += 2
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                blocked = [bool((q[i] <= ranges[i, 0]+.03 and axes[i] < 2)
                                or (q[i] >= ranges[i, 1]-.03 and axes[i] >= 2)) for i in range(2)]
                gprime = np.asarray([0. if item else 1. for item in blocked])
                hprime = np.asarray([float(axis in (0, 3)) for axis in axes])
                matrix = finite("J", (theta[:, 4:6]+theta[:, 6:8]*hprime)*gprime, (2, 2))
                current.update(guard_blocked_direction=blocked, guard_prime=gprime.tolist(),
                               hinge_branch_prime=hprime.tolist(), jacobian=matrix.tolist())
                cost["jacobian_build_returns"] += 1
                cost["jacobian_entry_scalars"] += 4
                cost["svd_attempts"] += 1
                try:
                    left, singular, right = (np.linalg.svd if svd is None else svd)(matrix, full_matrices=True)
                except BaseException:
                    cost["svd_exceptions"] += 1
                    raise
                cost["svd_returns"] += 1
                left, singular, right = (finite(name, value, shape) for name, value, shape in
                    (("svd_left", left, (2, 2)), ("singular", singular, (2,)), ("svd_right", right, (2, 2))))
                rank_tolerance = float(EPS*singular[0])
                rank = int(np.count_nonzero(singular > rank_tolerance)) if singular[0] > 0. else 0
                current.update(singular_values=singular.tolist(), rank=rank, rank_tolerance=rank_tolerance)
                cost["rank"+str(rank)+"_branches"] += 1
                cost["minimum_norm_mapping_attempts"] += 1
                projection = matvec(left.T, error, cost)
                scaled = np.zeros(2)
                for component in range(rank):
                    cost["singular_component_division_attempts"] += 1
                    scaled[component] = projection[component]/singular[component]
                    cost["singular_component_division_returns"] += 1
                delta = finite("delta_u", -matvec(right.T, scaled, cost), (2,))
                response = matvec(matrix, delta, cost)
                mapped, unmapped = finite("mapped", -response, (2,)), finite("unmapped", error+response, (2,))
                candidate = finite("logged_request_plus_delta", request+delta, (2,))
                tolerance = float(EPS*max(1., float(np.sum(np.abs(error))+np.sum(np.abs(matrix*delta)))))
                finite("image_tolerance", tolerance, ())
                cost["image_residual_tolerance_evaluations"] += 1
                cost["minimum_norm_mapping_returns"] += 1
                direction = [bool((request[i] != lower or delta[i] >= 0.) and
                                  (request[i] != upper or delta[i] <= 0.))
                             for i, (lower, upper) in enumerate(bounds)]
                within_box = [bool(lower <= candidate[i] <= upper) for i, (lower, upper) in enumerate(bounds)]
                permission = [bool(-.5 <= value <= .5) for value in candidate]
                image_compatible = bool(np.max(np.abs(unmapped)) <= tolerance)
                reasons = []
                if not image_compatible:
                    reasons.append("saved_error_not_in_numeric_image")
                if not all(direction):
                    reasons.append("minimum_norm_direction_outside_logged_one_sided_branch")
                if not all(within_box):
                    reasons.append("minimum_norm_leaves_logged_closed_box")
                if not all(permission):
                    reasons.append("minimum_norm_exceeds_shared_permission")
                crossed_hinge = [any(min(request[i], candidate[i]) < cut < max(request[i], candidate[i])
                                     for cut in (-.25, .25)) for i in range(2)]
                crossed_guard_sign = [bool((q[i] <= ranges[i, 0]+.03 or q[i] >= ranges[i, 1]-.03)
                    and min(request[i], candidate[i]) < 0. < max(request[i], candidate[i])) for i in range(2)]
                cost["delta_and_unmapped_l2_norm_attempts"] += 2
                delta_norm = float(finite("delta_l2", math.hypot(*delta), ()))
                unmapped_norm = float(finite("unmapped_l2", math.hypot(*unmapped), ()))
                cost["delta_and_unmapped_l2_norm_returns"] += 2
                current.update(status="descriptive_mapping" if not reasons else "finite_mapping_unavailable",
                    minimum_norm_delta_u_nm=delta.tolist(), candidate_request_nm=candidate.tolist(),
                    mapped_error_rad_s=mapped.tolist(), unmapped_error_rad_s=unmapped.tolist(),
                    image_residual_tolerance_rad_s=tolerance, numeric_image_compatible=image_compatible,
                    branch_direction_compatible_axis=direction, within_same_closed_box_axis=within_box,
                    within_shared_permission_axis=permission, crossed_hinge_cut_axis=crossed_hinge,
                    crossed_guard_sign_cut_axis=crossed_guard_sign, mapping_available=not reasons,
                    unavailable_reasons=reasons, delta_l2_nm=delta_norm,
                    unmapped_l2_rad_s=unmapped_norm,
                    rank1_outside_box_does_not_exclude_other_nullspace_solutions=rank == 1 and not all(within_box))
        if not 1 <= len(result["branches"]) <= 4:
            raise ValueError("logged_request_must_have_one_to_four_adjacent_boxes")
        cost["row_algebra_returns"] += 1
        return result
    except BaseException as exc:
        cost["row_algebra_exceptions"] += 1
        if current is not None:
            current["status"] = "technical_failure"
        exc.action_error_partial_record = safe(result)
        raise


def distribution(values, cost):
    cost["descriptive_distribution_calls"] += 1
    cost["descriptive_distribution_value_uses"] += len(values)
    if not values:
        return None
    result = {"count": len(values), "minimum": min(values), "maximum": max(values),
              "mean": statistics.fmean(values), "median": statistics.median(values)}
    for name in ("minimum", "maximum", "mean", "median"):
        finite("description_"+name, result[name], ())
    return result


class Reader:
    def __init__(self, repo, cost):
        self.repo, self.cost, self.inputs = repo, cost, {}
        self.h1_seen, self.paired_seen, self.current_H1_identity = set(), set(), None

    def read(self, relative):
        pin = INPUT_PINS[relative]
        path = (self.repo / ARCHIVE / relative).resolve()
        if not path.is_relative_to((self.repo / ARCHIVE).resolve()):
            raise ValueError("fixed_input_path_escaped_archive")
        self.cost["input_file_read_attempts"] += 1
        if path.stat().st_size != pin[0]:
            raise ValueError("fixed_input_byte_count_differs:"+relative)
        blob = path.read_bytes()
        self.cost["input_file_read_returns"] += 1
        self.cost["input_stored_bytes_read"] += len(blob)
        self.cost["input_hash_calls"] += 1
        self.inputs[relative] = identity(blob)
        if self.inputs[relative] != expected_pin(pin):
            raise ValueError("fixed_input_identity_differs:"+relative)
        return blob

    def json(self, relative):
        blob = self.read(relative)
        self.cost["metadata_JSON_parse_attempts"] += 1
        result = json.loads(blob)
        self.cost["metadata_JSON_parse_returns"] += 1
        return result

    def predictions(self, binding):
        paths = ("predictions.jsonl.gz", "predictions.00001.jsonl.gz")
        if (binding.get("format") != "ordered_intact_JSONL_gzip_shards"
                or [part.get("path") for part in binding.get("parts", [])] != list(paths)
                or binding.get("records") != 11772):
            raise ValueError("fixed_full_prediction_stream_required")
        total_hash, total_bytes, total_rows = hashlib.sha256(), 0, 0
        for part in binding["parts"]:
            blob = self.read("raw/"+part["path"])
            if part["stored"] != expected_pin(INPUT_PINS["raw/"+part["path"]]):
                raise ValueError("prediction_manifest_stored_pin_differs")
            digest, size, rows = hashlib.sha256(), 0, 0
            self.cost["gzip_decode_attempts"] += 1
            with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
                while True:
                    line = stream.readline(64_000_001)
                    if not line:
                        break
                    self.cost["prediction_decoded_bytes"] += len(line)
                    size += len(line)
                    if len(line) > 64_000_000 or size > 64_000_000 or not line.endswith(b"\n"):
                        raise ValueError("prediction_decoded_shard_or_line_bound_failed")
                    digest.update(line)
                    total_hash.update(line)
                    self.cost["prediction_decoded_hash_byte_uses"] += 2*len(line)
                    self.cost["prediction_decoded_hash_updates"] += 2
                    rows += 1
                    total_rows += 1
                    self.cost["prediction_decoded_records"] += 1
                    if total_rows > 11772:
                        raise ValueError("prediction_record_budget_exceeded")
                    self.cost["prediction_JSON_parse_attempts"] += 1
                    row = json.loads(line)
                    self.cost["prediction_JSON_parse_returns"] += 1
                    yield row
            self.cost["gzip_decode_returns"] += 1
            total_bytes += size
            if part["records"] != rows or part["decoded"] != {"bytes": size, "sha256": digest.hexdigest()}:
                raise ValueError("prediction_decoded_part_identity_differs")
        if total_rows != 11772 or binding["decoded"] != {"bytes": total_bytes, "sha256": total_hash.hexdigest()}:
            raise ValueError("prediction_decoded_stream_identity_differs")


def source_identity(repo, commit, cost):
    if Path(__file__).resolve() != (repo / SOURCE_PATH).resolve():
        raise ValueError("canonical_runner_module_path_required")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("exact_lowercase_source_commit_required")
    def git(arguments):
        cost["source_git_query_attempts"] += 1
        result = subprocess.run(["git", *arguments], cwd=repo, capture_output=True, check=False)
        cost["source_git_query_returns"] += 1
        cost["source_git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("source_git_query_failed:"+arguments[0])
        return result.stdout
    if git(["rev-parse", "HEAD"]).decode().strip() != commit or git(["status", "--porcelain"]):
        raise ValueError("first_source_must_be_exact_clean_HEAD")
    if PROTOCOL_PIN is None:
        raise ValueError("protocol_pin_must_be_frozen_before_first_run")
    files, blobs = {}, {}
    for name in (SOURCE_PATH, PROTOCOL_PATH):
        cost["source_file_read_attempts"] += 1
        blob = (repo / name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_bytes_read"] += len(blob)
        if blob != git(["show", commit+":"+name]):
            raise ValueError("source_working_bytes_differ_from_exact_commit:"+name)
        files[name], blobs[name] = identity(blob), blob
    if files[PROTOCOL_PATH] != PROTOCOL_PIN:
        raise ValueError("frozen_protocol_pin_differs")
    return {"commit": commit, "clean_committed_bytes_verified": True, "files": files}, blobs


def execute(repo, reader, cost, writer):
    manifest, run, models = (reader.json("raw/"+name) for name in ("manifest.json", "run.json", "models.json"))
    reader.read("audit_first/audit.json")  # Byte/hash binding only: deliberately no JSON parse.
    if (manifest.get("experiment_id") != "EF1B" or manifest.get("status") != "completed"
            or run.get("source", {}).get("commit") != EF1B_SOURCE_COMMIT
            or run.get("source", {}).get("clean_committed_bytes_verified") is not True
            or run.get("status") != "completed" or run.get("failure") is not None
            or run.get("JSONL_streams") != manifest.get("streams")):
        raise ValueError("fixed_completed_EF1B_source_required")
    for name in ("run.json", "models.json", "predictions.jsonl.gz", "predictions.00001.jsonl.gz"):
        if manifest["files"].get(name) != expected_pin(INPUT_PINS["raw/"+name]):
            raise ValueError("fixed_manifest_file_binding_differs:"+name)
    trials = {trial["trial_id"]: trial for trial in run.get("trials", [])}
    expected_trials = {f"EF1B_{seed}_control_{method}" for seed in SEEDS for method in METHODS}
    if set(trials) != expected_trials or len(run["trials"]) != 6 or set(models) != {str(seed) for seed in SEEDS}:
        raise ValueError("six_fresh_trials_and_six_model_population_required")
    snapshots = {}
    for seed in SEEDS:
        if set(models[str(seed)]) != set(METHODS):
            raise ValueError("two_frozen_models_per_seed_required")
        for method in METHODS:
            snapshot = models[str(seed)][method]
            if (snapshot.get("structure") != "coupled_hinge9" or snapshot.get("dt_seconds") != .002
                    or snapshot.get("trainable") is not False or snapshot.get("input_mapping", {}).get("basis") != "known_angle_guard"):
                raise ValueError("frozen_2ms_coupled_guard_model_required")
            theta = finite("saved_theta", snapshot["coefficients"], (2, 9))
            cost["frozen_theta_scalars_read"] += 18
            guard = snapshot["input_mapping"]["public_guard"]
            if guard.get("angle_margin_rad") != .03 or guard.get("request_clip_per_axis_nm") != .5:
                raise ValueError("original_public_guard_required")
            ranges = finite("saved_public_ranges", guard["public_joint_ranges_rad"], (2, 2))
            snapshots[(seed, method)] = (snapshot, theta, ranges)
        expected_fps = {method: snapshots[(seed, method)][0]["parameter_fingerprint"] for method in METHODS}
        for source_method in METHODS:
            trial = trials[f"EF1B_{seed}_control_{source_method}"]
            if trial.get("complete") is not True or any(trial.get(key) != expected_fps for key in
                    ("model_fingerprints_before", "model_fingerprints_after_control", "model_fingerprints_after")):
                raise ValueError("complete_fresh_frozen_model_trial_binding_required")
    population, paired, stats = set(), {}, defaultdict(lambda: {"model_rows": 0, "branches": 0,
        "rows_all_branches_available": 0, "rows_any_branch_available": 0, "rank_counts": Counter(),
        "unavailable_reason_counts": Counter(), "delta_l2_all_branches": [], "delta_l2_available_branches": [],
        "unmapped_l2_all_branches": [], "permission_margin_min_per_row": []})
    for row in reader.predictions(manifest["streams"]["predictions"]):
        if row.get("horizon") != 1:
            cost["other_horizon_records_decoded_without_mathematics"] += 1
            continue
        cost["H1_model_records"] += 1
        seed, trial_id, model, origin = (row.get(key) for key in ("seed", "trial_id", "model", "origin_active_index"))
        reader.current_H1_identity = {"seed": seed, "trial_id": trial_id, "model": model, "origin_active_index": origin}
        key = (trial_id, model, origin)
        if (seed not in SEEDS or trial_id not in trials or seed != trials[trial_id]["seed"] or model not in METHODS
                or type(origin) is not int or origin not in range(0, 2000, 10) or key in population
                or row.get("available") is not True or row.get("scope") != "control_conditional_prediction"):
            raise ValueError("missing_duplicate_unavailable_or_mismatched_H1_population")
        population.add(key)
        reader.h1_seen.add(key)
        snapshot, theta, ranges = snapshots[(seed, model)]
        if row.get("model_parameter_fingerprint") != snapshot["parameter_fingerprint"]:
            raise ValueError("H1_frozen_model_fingerprint_differs")
        inputs = row["model_input"]
        requests = inputs["known_requests2"]
        if len(requests) != 1:
            raise ValueError("H1_must_have_one_saved_known_request")
        native_binding = {key: inputs[key] for key in ("q2", "v2", "known_requests2")}
        pair_key = (trial_id, origin)
        if pair_key in paired and paired[pair_key] != native_binding:
            raise ValueError("cold_learned_saved_native_pair_binding_differs")
        paired[pair_key] = native_binding
        reader.paired_seen.add(pair_key)
        cost["independent_saved_error_scalar_uses"] += 2
        algebra = diagnose_row(inputs["q2"], inputs["v2"], requests[0], row["v_error_rad_s"], theta, ranges, cost=cost)
        result = {"seed": seed, "trial_id": trial_id, "control_source_method": trials[trial_id]["kind"].removeprefix("control_"),
                  "model": model, "origin_active_index": origin,
                  "model_parameter_fingerprint": snapshot["parameter_fingerprint"], **algebra}
        writer(result)
        group = stats[(seed, result["control_source_method"], model)]
        group["model_rows"] += 1
        group["branches"] += len(algebra["branches"])
        availability = [item["mapping_available"] for item in algebra["branches"]]
        group["rows_all_branches_available"] += all(availability)
        group["rows_any_branch_available"] += any(availability)
        group["permission_margin_min_per_row"].append(min(min(item) for item in algebra["permission_margins_nm"]))
        for branch in algebra["branches"]:
            group["rank_counts"][str(branch["rank"])] += 1
            group["unavailable_reason_counts"].update(branch["unavailable_reasons"])
            group["delta_l2_all_branches"].append(branch["delta_l2_nm"])
            group["unmapped_l2_all_branches"].append(branch["unmapped_l2_rad_s"])
            if branch["mapping_available"]:
                group["delta_l2_available_branches"].append(branch["delta_l2_nm"])
    expected_population = {(trial, method, origin) for trial in expected_trials for method in METHODS for origin in range(0, 2000, 10)}
    cost["paired_origins"] = len(paired)
    if population != expected_population or len(paired) != 1200:
        raise ValueError("complete_2400_H1_1200_paired_population_required_no_subset_ranking")
    if any(cost[key] > limit for key, limit in LIMITS.items()):
        raise ValueError("frozen_algebra_budget_exceeded")
    summaries = []
    for (seed, source_method, model), group in sorted(stats.items()):
        summaries.append({"seed": seed, "control_source_method": source_method, "model": model,
            **{key: dict(value) if isinstance(value, Counter) else value for key, value in group.items() if not isinstance(value, list)},
            **{key: distribution(value, cost) for key, value in group.items() if isinstance(value, list)},
            "branch_distribution_denominator": "all_logged_request_adjacent_boxes_kept_without_selection",
            "any_available_is_not_an_action_selection": True})
    return {"complete_model_records": len(population), "complete_paired_origins": len(paired),
            "source_first_audit_declaration": {"status": "passed", "checks": 443, "failures": 0, "unavailable_contracts": 0,
                "binding_only_not_parsed_or_reaudited": True}, "summaries": summaries,
            "scientific_gate_recomputation": False, "partial_subset_ranking": False,
            "rank1_minimum_norm_rejection_does_not_prove_no_nullspace_solution": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    base = (repo / ARCHIVE).resolve()
    if output.exists() or output == repo or repo.is_relative_to(output) or output.is_relative_to(base) or base.is_relative_to(output):
        parser.error("existing_or_input_overlapping_output_refused")
    output.mkdir(parents=True, exist_ok=False)
    cost, result, failure, source = Counter(), None, None, None
    reader, output_hash = Reader(repo, cost), hashlib.sha256()
    wall, cpu = time.perf_counter(), time.process_time()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                source, source_blobs = source_identity(repo, args.source_commit, cost)
                buffer = io.BytesIO()
                cost["source_archive_build_attempts"] += 1
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, blob in source_blobs.items():
                        archive.writestr(name, blob)
                cost["source_archive_build_returns"] += 1
                cost["source_archive_write_attempts"] += 1
                (output / "source.zip").write_bytes(buffer.getvalue())
                cost["source_archive_write_returns"] += 1
                cost["source_archive_bytes_written"] += len(buffer.getvalue())
                with (output / "diagnostic_records.jsonl").open("xb") as records:
                    def write(row):
                        cost["diagnostic_JSON_encode_attempts"] += 1
                        data = (json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
                        cost["diagnostic_JSON_encode_returns"] += 1
                        cost["diagnostic_record_write_attempts"] += 1
                        records.write(data)
                        records.flush()
                        cost["diagnostic_record_write_returns"] += 1
                        cost["diagnostic_bytes_written"] += len(data)
                        output_hash.update(data)
                        cost["diagnostic_hash_byte_uses"] += len(data)
                    try:
                        result = execute(repo, reader, cost, write)
                    except BaseException as exc:
                        if hasattr(exc, "action_error_partial_record"):
                            try:
                                write({"technical_failure_partial": exc.action_error_partial_record})
                            except BaseException as write_exc:
                                exc.action_error_partial_write_failure = {"type": type(write_exc).__name__,
                                    "message": str(write_exc), "traceback": traceback.format_exc()}
                        raise
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc(),
                           "current_H1_identity": reader.current_H1_identity,
                           "partial_record_write_failure": getattr(exc, "action_error_partial_write_failure", None)}
                traceback.print_exc()
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    group_counts = Counter((trial, model) for trial, model, origin in reader.h1_seen)
    cost["population_summary_identity_uses"] = len(reader.h1_seen)
    population = [{"trial_id": f"EF1B_{seed}_control_{method}", "model": model, "planned_records": 200,
                   "unique_identities_seen": group_counts[(f"EF1B_{seed}_control_{method}", model)],
                   "unseen_or_unattempted_records": 200-group_counts[(f"EF1B_{seed}_control_{method}", model)]}
                  for seed in SEEDS for method in METHODS for model in METHODS]
    report = {"experiment_id": "EF1D", "status": "failed" if failure else "completed", "source": source,
        "runtime": {"python": sys.version, "python_version": platform.python_version(), "numpy": np.__version__,
                    "platform": platform.platform()},
        "EF1B_source_commit": EF1B_SOURCE_COMMIT, "EF1B_delivery_commit": EF1B_DELIVERY_COMMIT,
        "fixed_input_identities": reader.inputs, "planned_upper_bounds": LIMITS, "cost": dict(cost),
        "result": result, "first_failure": failure,
        "fixed_population_accounting": {"planned_model_records": 2400, "planned_paired_origins": 1200,
            "unique_model_identities_seen": len(reader.h1_seen), "paired_origins_seen": len(reader.paired_seen),
            "groups": population, "partial_subset_ranking": False},
        "diagnostic_stream": {"records": cost["diagnostic_record_write_returns"],
                              "bytes": cost["diagnostic_bytes_written"], "sha256": output_hash.hexdigest()},
        "timing_excludes": "final_run_JSON_encoding_and_report_writes",
        "unmeasured_filesystem_IO": "unknown_not_zero", "new_physics_calls": 0, "new_control_calls": 0,
        "new_fit_calls": 0, "new_RLS_updates": 0, "model_predict_calls": 0, "trace_reads": 0,
        "old_raw_reads": 0, "other_horizon_mathematics": 0, "scientific_gate_recomputations": 0,
        "constraint_searches": 0, "clipped_deltas": 0, "control_family_reopened": False,
        "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"experiment_id": "EF1D", "status": report["status"], "output": str(output), "first_failure": failure}))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
