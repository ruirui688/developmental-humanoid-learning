"""IV3: fresh near-qref state identification, then one seen saved evaluation."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import importlib.util
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

# Both frozen helpers are pure at import; IV3 never changes their globals.
_spec = importlib.util.spec_from_file_location("_iv3_frozen_iv2_helper", Path(__file__).with_name("refit_instrumental_state.py"))
iv2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iv2)
safe, pin, finite, native, pd = iv2.safe, iv2.pin, iv2.finite, iv2.native, iv2.pd
StudyStop, NativeMeter = iv2.StudyStop, iv2.NativeMeter

SOURCE_PATH = "scripts/run_near_reference_identification.py"
PROTOCOL_PATH = "docs/NEAR_REFERENCE_IDENTIFICATION_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 7211, "sha256": "d1bc8aa379a2e5b06694c851432d89b5b1a72bba6ebc217c2885cf53ceee0b08"}
MODULE_PATH = "src/developmental_physics/consistent_action_state_model.py"
SOURCE_PATHS = (SOURCE_PATH, PROTOCOL_PATH, *iv2.SOURCE_PATHS)
INPUT_BASE = "results/cpu_validation/2026-10-12_consistent_action_state/raw"
IV2_SOURCE = "d8491b2e0f8b3bae649b8bf9a297bebba7f76270"
INPUT_PINS = {
    "run.json": {"bytes": 1145452, "sha256": "a6fd68bb909ac8d8607986aeb55918d76dce18b51f8a0bbcd2d93b8caef2a0ec"},
    "models.json": {"bytes": 21758, "sha256": "96e94bc63311262878114354e1fb4f084564e5116cf14435ee47936415176dcd"},
    "predictions.jsonl.gz": {"bytes": 10936879, "sha256": "de32524abd8f5b8a7f45d6dbc92158143c67b5fe05893656401c38dddfd58685"},
}
SEEDS, HORIZONS = (8101, 8102, 8103), (1, 10, 20, 50, 150)
OLD_NAMES = ("cold", "oldlearned", "IV1", "IV2")
FLAGS = {**iv2.FLAGS, "control_candidate_opened": False}
BOUNDS = {"new_training_controls": 9000, "new_training_substeps": 9000,
    "new_state_fit_scalar_label_uses": 12000, "state_fit_attempts": 3, "state_fitted_coefficients": 30,
    "saved_evaluation_records": 1443, "prediction_pair_calls": 62340, "prediction_velocity_head_outputs": 124680,
    "new_evaluation_controls": 0, "RLS": 0, "fork": 0, "old_model_predictions": 0, "old_fit_or_gate_recomputations": 0}


def near_reference_request(q, v, qref, bits):
    qref = finite("fixed_current_qref_target", qref, (2,))
    bits = np.asarray(bits)
    if bits.shape != (2,) or not np.all(np.isin(bits, (0, 1))):
        raise ValueError("two_independent_saved_Rademacher_bits_required")
    base = pd(q, v, qref, .375)
    dither = (2*bits-1)*.125
    request = finite("near_reference_final_request2", base+dither, (2,))
    if np.any(np.abs(request) > .5):
        raise ValueError("original_final_half_nm_permission_required")
    return {"current_target_q2": qref.copy(), "known_base2": base,
        "dither_bits2": bits.copy(), "known_dither2": dither, "request2": request}


def saved_cold_template(row):
    """Non-cold rows are excluded before their endpoints or paths are read."""
    if not isinstance(row, dict):
        raise ValueError("saved_prediction_row_must_be_object")
    if row.get("model") != "cold":
        return None
    seed, h, origin = row.get("seed"), row.get("horizon"), row.get("origin_active_index")
    if (seed not in SEEDS or type(h) is not int or h not in HORIZONS or type(origin) is not int
        or origin not in range(0, 1000-h+1, 10) or row.get("status") != "completed" or row.get("available") is not True):
        raise ValueError("complete_declared_cold_evaluation_template_required")
    inputs = row["model_input"]
    return {"seed": seed, "horizon": h, "origin_active_index": origin,
        "q2": finite("saved_native_start_q2", inputs["q2"], (2,)).copy(),
        "v2": finite("saved_native_start_v2", inputs["v2"], (2,)).copy(),
        "known_requests2": finite("saved_final_request_path", inputs["known_requests2"], (h, 2)).copy(),
        "actual_endpoint_q2": finite("saved_scoring_endpoint_q2", row["actual_endpoint_q2"], (2,)).copy(),
        "actual_endpoint_v2": finite("saved_scoring_endpoint_v2", row["actual_endpoint_v2"], (2,)).copy(),
        "cold_fingerprint": row["model_fingerprint"]}


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


class Collector(iv2.Collector):
    def __init__(self, repo, output):
        self.repo, self.output, self.cost = repo, output, Counter()
        self.source, self.context, self.input_run = None, None, None
        self.models, self.moments, self.fingerprints, self.input_snapshots = {}, {}, {}, {}
        self.input_identities, self.handles, self.streams, self.seed_results = {}, {}, {}, []
        self.trials = [{"seed": seed, "kind": "identification", "trial_id": f"s{seed}_identification",
            "planned_controls": 3000, "status": "not_attempted", "contact_qualification": None,
            "stage_telemetry": {}, "stop": None} for seed in SEEDS]
        self.fit_slots = [{"seed": seed, "planned_samples": 2000, "status": "not_attempted",
            "fit_attempted": False, "available": False} for seed in SEEDS]
        self.predictions = [{"seed": seed, "model": "IV3", "horizon": h, "origin_active_index": origin,
            "status": "not_attempted", "available": False} for seed in SEEDS for h in HORIZONS
            for origin in range(0, 1000-h+1, 10)]
        self.metrics = {"complete_population": False, "iv3_prediction_gate_passed": False, "checks": [], **FLAGS}
        self.templates, self.prediction_blob = {}, None

    def load_inputs(self):
        sys.path.insert(0, str(self.repo / "src"))
        self.body = importlib.import_module("developmental_physics.consistent_action_state_model")
        if Path(self.body.__file__).resolve() != (self.repo / MODULE_PATH).resolve():
            raise ValueError("canonical_state_fit_module_required")
        blobs = {}
        for name in INPUT_PINS:
            self.context = {"stage": "input_identity", "filename": name}
            self.cost["IV2_input_read_attempts"] += 1
            blobs[name] = (self.repo / INPUT_BASE / name).read_bytes()
            self.cost["IV2_input_read_returns"] += 1
            self.cost["IV2_input_bytes_read"] += len(blobs[name])
            self.cost["IV2_input_hash_attempts"] += 1
            self.input_identities[name] = pin(blobs[name])
            self.cost["IV2_input_hash_returns"] += 1
            self.cost["IV2_input_bytes_hashed"] += len(blobs[name])
            if self.input_identities[name] != INPUT_PINS[name]:
                raise ValueError("fixed_IV2_input_identity_differs:"+name)
        self.cost["IV2_JSON_parse_attempts"] += 2
        run, snapshots = json.loads(blobs["run.json"]), json.loads(blobs["models.json"])
        self.cost["IV2_JSON_parse_returns"] += 2
        self.input_run, self.prediction_blob = run, blobs["predictions.jsonl.gz"]
        if (run.get("experiment_id") != "IV2" or run.get("status") != "completed" or run.get("first_failure") is not None
            or run.get("source", {}).get("commit") != IV2_SOURCE or run.get("source", {}).get("clean_committed_bytes_verified") is not True
            or run.get("metrics", {}).get("complete_population") is not True or run.get("config", {}).get("seeds") != list(SEEDS)
            or run.get("config", {}).get("H") != list(HORIZONS) or run.get("config", {}).get("dt_seconds") != .002
            or set(snapshots) != {str(seed) for seed in SEEDS}):
            raise ValueError("completed_frozen_IV2_source_required")
        self.source_trials = {item["seed"]: item for item in run["trials"]}
        if set(self.source_trials) != set(SEEDS) or len(run["trials"]) != 3:
            raise ValueError("all_three_original_prediction_trials_required")
        for seed in SEEDS:
            group = snapshots[str(seed)]
            if set(group) != {"cold", "oldlearned", "IV1", "newmatched"}:
                raise ValueError("all_four_original_frozen_snapshots_required")
            trial = self.source_trials[seed]
            if (trial.get("status") != "completed" or trial.get("stop") is not None
                or trial.get("contact_qualification", {}).get("passed") is not True
                or trial.get("metadata_before") != trial.get("metadata_after")):
                raise ValueError("original_complete_contact_and_physical_identity_required")
            for input_name, name in (("cold", "cold"), ("oldlearned", "oldlearned"), ("IV1", "IV1"), ("newmatched", "IV2")):
                item = group[input_name]
                self.cost["initial_theta_scalar_reads"] += 18
                model = self.body.InstrumentalActionBodyModel(item["qref_rad"], item["public_joint_ranges_rad"], item["coefficients"])
                self.cost["frozen_native_model_builds"] += 1
                fingerprint = model.parameter_fingerprint()
                identity = run.get("model_fingerprints", {}).get(str(seed), {}).get(input_name, {})
                if (item.get("parameter_fingerprint") != fingerprint or item.get("fingerprint_before_prediction") != fingerprint
                    or identity.get("parameter_fingerprint") != fingerprint or any(item.get(key) != value for key, value in model.record().items())
                    or model.qref.tobytes() != np.asarray(trial["qref2"], dtype=np.float64).tobytes()
                    or model.ranges.tobytes() != np.asarray(trial["public_ranges2"], dtype=np.float64).tobytes()):
                    raise ValueError("frozen_snapshot_guard_qref_ranges_and_fingerprint_required")
                self.cost["frozen_native_model_identity_checks"] += 1
                self.models[(seed, name)], self.fingerprints[(seed, name)], self.input_snapshots[(seed, name)] = model, fingerprint, item
            self.moments[seed] = self.body.StateConsistencyFit(self.models[(seed, "IV1")], self.cost)

    def step(self, env, request, trial, row, qref):
        if self.cost["total_control_attempts"] >= 9000:
            raise ValueError("fixed_IV3_training_budget_exhausted")
        # The IV2 override has a 6000 budget; call the frozen paid-first helper.
        return iv2.iv1.Collector.step(self, env, request, trial, row, qref)

    def collect(self, free, seed):
        trial = next(item for item in self.trials if item["seed"] == seed)
        trial["status"] = "running"
        try:
            self.context = {"stage": "near_reference_constructor", "seed": seed}
            self.cost["source_environment_constructor_attempts"] += 1
            env = free.FreeRootFastFeedbackGroundBodyEnv(audit_cost=self.cost)
            self.cost["source_environment_constructor_returns"] += 1
            self.cost["explicit_reset_attempts"] += 1
            observation = env.reset(seed=seed, pose="supine")
            self.cost["explicit_reset_returns"] += 1
            if env.control_dt != .002 or env.config.control_substeps != 1:
                raise ValueError("original_2ms_environment_required")
            trial["metadata_before"] = safe(env.frozen_metadata())
            if trial["metadata_before"] != self.source_trials[seed]["metadata_before"]:
                raise ValueError("original_free_root_physics_and_protection_required")
            ranges = finite("fresh_public_ranges", env.model.jnt_range[env._joint_ids][:2], (2, 2))
            rng = np.random.Generator(np.random.PCG64(seed+100000))
            self.cost["PCG64_Generator_builds"] += 1
            trial["random_seed"] = seed+100000
            qref, previous = None, None
            for index in range(3000):
                active = index-1000
                if active == 0:
                    qref, _ = native(observation)
                    qref = qref.copy()
                    for name in OLD_NAMES:
                        model = self.models[(seed, name)]
                        if qref.tobytes() != model.qref.tobytes() or ranges.tobytes() != model.ranges.tobytes():
                            raise ValueError("fresh_qref_and_ranges_must_exactly_match_all_frozen_snapshots")
                    trial.update(qref2=qref.tolist(), public_ranges2=ranges.tolist(), active_target="constant_fresh_qref")
                request, info = np.zeros(8), {}
                if active >= 0:
                    q, v = native(observation)
                    if previous is not None and (q.tobytes(), v.tobytes()) != previous:
                        raise ValueError("fresh_same_trial_native_training_must_be_exactly_continuous")
                    self.cost["identification_public_PD_attempts"] += 1
                    bits = rng.integers(0, 2, size=2)
                    self.cost["Rademacher_pair_draws"] += 1
                    info = near_reference_request(q, v, qref, bits)
                    request[:2] = info.pop("request2")
                    self.cost["identification_public_PD_returns"] += 1
                row = {"seed": seed, "trial_id": trial["trial_id"], "kind": "identification", "control_index": index,
                    "active_index": active, "stage": "prefix" if active < 0 else "A" if active < 1000 else "B",
                    "phase": "prefix" if active < 0 else "active", "observation_before": safe(observation),
                    "requested_torque8": request.tolist(), "returned": False, **safe(info)}
                after = self.step(env, request, trial, row, qref)
                if active >= 0:
                    next_q, next_v = native(after)
                    previous = (next_q.tobytes(), next_v.tobytes())
                    if self.moments[seed].samples != active:
                        raise ValueError("all_ordered_2000_fresh_native_pairs_required")
                    try:
                        annotation = self.moments[seed].add(q, v, request[:2], next_v)
                    finally:
                        # The unchanged shared IV2 kernel names this counter reused;
                        # IV3 supplies only fresh labels, translated at this boundary.
                        self.cost["new_state_fit_scalar_label_uses"] += self.cost.pop("reused_state_fit_scalar_label_uses", 0)
                    self.write("source_trace", {"IV3_native_fit_annotation": {"seed": seed, "active_index": active, **annotation}})
                observation = after
            trial["metadata_after"] = safe(env.frozen_metadata())
            if trial["metadata_after"] != trial["metadata_before"]:
                raise ValueError("original_environment_identity_changed")
            trial["contact_qualification"] = {"required_stages": ["prefix", "A", "B"], "passed": all(
                trial["stage_telemetry"][stage]["captured_substeps"] == 1000 and
                trial["stage_telemetry"][stage]["positive_contact_endpoints"]["left_arm"] >= 1 for stage in ("prefix", "A", "B")),
                "selection_use": "complete_phase_qualification_only_no_actor_or_label_use"}
            if not trial["contact_qualification"]["passed"]:
                raise StudyStop("complete_contact_qualification_failed_no_recollection")
            trial["status"] = "completed"
        except BaseException as exc:
            trial["status"] = "stopped" if isinstance(exc, StudyStop) else "failed"
            trial["failure"] = {"type": type(exc).__name__, "message": str(exc)}
            raise

    def fit_all_once(self):
        if any(trial["status"] != "completed" for trial in self.trials) or any(self.moments[seed].samples != 2000 for seed in SEEDS):
            raise ValueError("complete_all_three_fresh_populations_required_before_any_fit")
        for slot in self.fit_slots:
            seed = slot["seed"]
            self.context = {"stage": "IV3_first_state_fit", "seed": seed}
            slot.update(status="attempted", fit_attempted=True)
            try:
                model = self.moments[seed].fit_once()
                if model.theta[:, 4:8].tobytes() != self.models[(seed, "IV1")].theta[:, 4:8].tobytes():
                    raise ValueError("original_IV1_action8_must_remain_byte_frozen")
                self.models[(seed, "IV3")] = model
                self.fingerprints[(seed, "IV3")] = model.parameter_fingerprint()
                slot.update(status="completed", available=True, frozen_fingerprint=self.fingerprints[(seed, "IV3")])
            except BaseException as exc:
                slot.update(status="failed", failure={"type": type(exc).__name__, "message": str(exc)})
                raise

    def load_templates(self):
        if any(slot["status"] != "completed" for slot in self.fit_slots):
            raise ValueError("evaluation_endpoint_decode_forbidden_before_all_frozen_fits")
        self.context = {"stage": "seen_saved_evaluation_decode"}
        with gzip.GzipFile(fileobj=io.BytesIO(self.prediction_blob), mode="rb") as stream:
            for line_index, line in enumerate(stream):
                self.context = {"stage": "seen_saved_evaluation_decode", "line_index": line_index}
                self.cost["IV2_prediction_decoded_lines"] += 1
                self.cost["IV2_prediction_decoded_bytes"] += len(line)
                self.cost["IV2_JSON_parse_attempts"] += 1
                row = json.loads(line)
                self.cost["IV2_JSON_parse_returns"] += 1
                template = saved_cold_template(row)
                if template is None:
                    self.cost["noncold_saved_rows_skipped_no_label_use"] += 1
                    continue
                key = tuple(template[name] for name in ("seed", "horizon", "origin_active_index"))
                if key in self.templates or template["cold_fingerprint"] != self.fingerprints[(template["seed"], "cold")]:
                    raise ValueError("unique_original_cold_saved_template_identity_required")
                if np.any(np.abs(template["known_requests2"]) > .5):
                    raise ValueError("saved_known_requests_inside_original_permission_required")
                template["source_decoded_line_index"] = line_index
                self.templates[key] = template
                self.cost["cold_saved_template_returns"] += 1
                self.cost["saved_evaluation_input_scalar_reads"] += 4+2*template["horizon"]
                self.cost["saved_evaluation_endpoint_scalar_reads_after_all_fits"] += 4
        expected = {(slot["seed"], slot["horizon"], slot["origin_active_index"]) for slot in self.predictions}
        if set(self.templates) != expected or self.cost["IV2_prediction_decoded_lines"] != 5772:
            raise ValueError("complete_saved_1443_cold_population_required_before_scoring")

    def score(self):
        for seed in SEEDS:
            old = next(item for item in self.input_run["seed_results"] if item["seed"] == seed)["prediction_scores"]
            summary = {"horizons": {}, "condition": "seen_saved_IV2_cold_native_origins_and_known_future_requests_not_new_holdout"}
            for h in HORIZONS:
                models = {("IV2" if name == "newmatched" else name): {**item, "transcribed_not_recomputed": True}
                    for name, item in old["horizons"][str(h)]["models"].items()}
                self.cost["old_RMSE_scalar_transcriptions"] += 16
                errors_q, errors_v = [], []
                model = self.models[(seed, "IV3")]
                for slot in (item for item in self.predictions if item["seed"] == seed and item["horizon"] == h):
                    key = (seed, h, slot["origin_active_index"])
                    template = self.templates[key]
                    self.context = {name: slot[name] for name in ("seed", "model", "horizon", "origin_active_index")}
                    slot.update(status="attempted", model_fingerprint=self.fingerprints[(seed, "IV3")],
                        source_cold_decoded_line_index=template["source_decoded_line_index"],
                        model_input={"q2": template["q2"], "v2": template["v2"], "known_requests2": template["known_requests2"]},
                        predicted_q_path=[], predicted_v_path=[])
                    original_error = None
                    try:
                        q, v = template["q2"].copy(), template["v2"].copy()
                        for request in template["known_requests2"]:
                            q, v = model.predict(q, v, request, self.cost)
                            slot["predicted_q_path"].append(q.tolist())
                            slot["predicted_v_path"].append(v.tolist())
                        with np.errstate(over="raise", invalid="raise"):
                            dq = finite("IV3_endpoint_q_error", q-template["actual_endpoint_q2"], (2,))
                            dv = finite("IV3_endpoint_v_error", v-template["actual_endpoint_v2"], (2,))
                        self.cost["seen_saved_scoring_scalar_label_uses"] += 4
                        slot.update(status="completed", available=True, actual_endpoint_q2=template["actual_endpoint_q2"],
                            actual_endpoint_v2=template["actual_endpoint_v2"], q_error_rad=dq, v_error_rad_s=dv)
                        errors_q.append(dq)
                        errors_v.append(dv)
                    except BaseException as exc:
                        original_error = exc
                        slot.update(status="failed", failure={"type": type(exc).__name__, "message": str(exc)})
                        raise
                    finally:
                        try:
                            self.write("predictions", slot)
                        except BaseException as write_exc:
                            if original_error is None:
                                raise
                            original_error.partial_write_failure = {"type": type(write_exc).__name__, "message": str(write_exc)}
                with np.errstate(over="raise", invalid="raise"):
                    rq, rv = (finite("IV3_full_population_RMSE", np.sqrt(np.mean(np.square(errors), axis=0)), (2,)) for errors in (errors_q, errors_v))
                self.cost["IV3_axis_RMSE_vector_computations"] += 2
                models["IV3"] = {"available": True, "observed_origin_count": len(errors_q), "q_rmse_axis_rad": rq.tolist(),
                    "v_rmse_axis_rad_s": rv.tolist(), "partial_subset_ranking": False}
                summary["horizons"][str(h)] = {"planned_origin_count": len(range(0, 1000-h+1, 10)), "models": models}
            self.seed_results.append({"seed": seed, "prediction_scores": summary})

    def gate(self):
        checks = []
        for h in HORIZONS:
            for signal in ("q", "v"):
                metric = "q_rmse_axis_rad" if signal == "q" else "v_rmse_axis_rad_s"
                strict, gated = (h, signal) in ((10, "v"), (150, "q")), h != 1 and (h, signal) != (10, "q")
                candidates = []
                for result in self.seed_results:
                    models = result["prediction_scores"]["horizons"][str(h)]["models"]
                    base, candidate = models["cold"][metric], models["IV3"][metric]
                    candidates.append(candidate)
                    checks.append({"seed": result["seed"], "horizon": h, "signal": signal, "available": True,
                        "cold_axis": base, "IV3_axis": candidate, "strict": strict, "gated": gated,
                        "passed": bool(all(candidate[i] < base[i] if strict else candidate[i] <= base[i] for i in range(2)))})
                if strict:
                    saved = next(item for item in self.input_run["metrics"]["checks"] if item.get("scope") == "three_seed_raw_RMSE_mean"
                        and item["horizon"] == h and item["signal"] == signal)
                    bm = finite("cold_axis_mean_transcribed", saved["cold_axis_mean"], (2,))
                    with np.errstate(over="raise", invalid="raise"):
                        cm = finite("new_IV3_three_seed_raw_RMSE_mean", np.mean(candidates, axis=0), (2,))
                    fractions = [(float(bm[i]-cm[i])/float(bm[i]) if bm[i] > 0. else None) for i in range(2)]
                    self.cost["new_IV3_mean_gate_comparisons"] += 1
                    checks.append({"scope": "three_seed_raw_RMSE_mean", "horizon": h, "signal": signal,
                        "cold_axis_mean_transcribed": bm.tolist(), "IV3_axis_mean": cm.tolist(), "improvement_fractions": fractions,
                        "available": all(value is not None for value in fractions), "required_improvement": .20,
                        "passed": all(value is not None and value >= .20 for value in fractions)})
        self.metrics = {"complete_population": True, "iv3_prediction_gate_passed": bool(all(item["passed"] for item in checks if item.get("gated", True))),
            "checks": checks, "mean_type": "arithmetic mean of original per_seed axis RMSE", "evaluation_seen_development": True,
            "original_IV2_gate_transcribed": self.input_run["metrics"]["iv2_prediction_gate_passed"], **FLAGS}

    def run(self):
        import mujoco
        core = importlib.import_module("developmental_physics.environment")
        free = importlib.import_module("developmental_physics.free_root_fast_feedback_environment")
        for module, relative in ((core, "src/developmental_physics/environment.py"), (free, "src/developmental_physics/free_root_fast_feedback_environment.py")):
            if Path(module.__file__).resolve() != (self.repo / relative).resolve():
                raise ValueError("canonical_environment_modules_required")
        meter, original = NativeMeter(mujoco, self.cost), (core.mujoco, free.mujoco)
        self.runtime_mujoco = mujoco.__version__
        core.mujoco = free.mujoco = meter
        try:
            for seed in SEEDS:
                self.collect(free, seed)
            self.fit_all_once()
        finally:
            core.mujoco, free.mujoco = original
        self.load_templates()
        self.score()
        for key, model in self.models.items():
            self.cost["final_frozen_model_fingerprint_checks"] += 1
            if model.parameter_fingerprint() != self.fingerprints[key]:
                raise ValueError("frozen_model_parameters_changed")
        if (self.cost["total_control_attempts"] != 9000 or self.cost["confirmed_physics_substeps"] != 9000
            or self.cost["new_state_fit_scalar_label_uses"] != 12000 or self.cost["state_fit_returns"] != 3
            or self.cost["state_fitted_coefficient_scalar_outputs"] != 30 or self.cost["pair_prediction_returns"] != 62340
            or self.cost["scalar_velocity_head_returns"] != 124680 or any(not item["available"] for item in self.predictions)):
            raise ValueError("complete_fixed_IV3_population_required_no_partial_ranking")
        self.gate()


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
    collector, failure, status = Collector(repo, output), None, "failed"
    wall, cpu = time.perf_counter(), time.process_time()
    def payload_failure(exc, stage):
        nonlocal failure, status
        collector.metrics.update(complete_population=False, iv3_prediction_gate_passed=False)
        detail = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        if failure is None:
            failure, status = {**detail, "context": collector.context}, "failed"
        else:
            failure.setdefault("secondary_payload_failures", []).append(detail)
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                collector.open_streams()
                collector.source, blobs = source_gate(repo, args.source_commit, collector.cost)
                with zipfile.ZipFile(output / "source.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, blob in blobs.items():
                        archive.writestr(name, blob)
                collector.cost["source_archive_bytes_written"] = (output / "source.zip").stat().st_size
                collector.load_inputs()
                collector.run()
                status = "completed"
            except BaseException as exc:
                status = "stopped" if isinstance(exc, StudyStop) else "failed"
                failure = {"type": type(exc).__name__, "message": str(exc), "context": collector.context, "traceback": traceback.format_exc(),
                    "partial_write_failure": getattr(exc, "partial_write_failure", None), "secondary_contact_failure": getattr(exc, "secondary_contact_failure", None),
                    "unconfirmed_native_work": "unknown_if_native_exception"}
                traceback.print_exc()
            finally:
                for handle in collector.handles.values():
                    try:
                        handle.close()
                    except BaseException as exc:
                        payload_failure(exc, "stream_close")
                        traceback.print_exc()
    collector.cost["wall_seconds"], collector.cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    models = {str(seed): {name: {**model.record(), "parameter_fingerprint": model.parameter_fingerprint(),
        "fingerprint_before_prediction": collector.fingerprints[(seed, name)], "initial_IV1_fingerprint": collector.fingerprints.get((seed, "IV1")) if name == "IV3" else None,
        "state_columns_replaced": [0, 1, 2, 3, 8] if name == "IV3" else None, "action_columns_frozen": [4, 5, 6, 7] if name == "IV3" else None}
        for (model_seed, name), model in collector.models.items() if model_seed == seed} for seed in SEEDS}
    moments = {str(seed): collector.moments[seed].record() if seed in collector.moments else
        {"samples": 0, "fit_attempted": False, "fit": None, "status": "not_attempted"} for seed in SEEDS}
    for name, data in (("models.json", models), ("moments.json", moments), ("metrics.json", collector.metrics)):
        try:
            (output / name).write_text(json.dumps(safe(data), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
        except BaseException as exc:
            payload_failure(exc, name+"_write")
    report = {"experiment_id": "IV3", "status": status, "first_failure": failure, "source": collector.source,
        "input_source": {"base": INPUT_BASE, "IV2_source_commit": IV2_SOURCE, "required_pins": INPUT_PINS, "actual_identities": collector.input_identities},
        "config": {"seeds": SEEDS, "prefix": 1000, "identification_active": 2000, "training_target": "constant_fresh_qref",
            "PD_Kp": 64., "PD_Kd": 4., "base_clip_nm": .375, "Rademacher_dose_nm": .125, "final_permission_nm": .5,
            "RNG": "Generator(PCG64(seed+100000))", "draw_API": "rng.integers(0, 2, size=2)", "axis_order": [0, 1],
            "dt_seconds": .002, "fit_rcond": 128*np.finfo(np.float64).eps, "H": HORIZONS, "prediction_stride": 10,
            "study_q_rad": .12, "study_v_rad_s": 1., "evaluation": "seen_IV2_cold_saved_origins_no_new_evaluation_physics"},
        "planned_upper_bounds": BOUNDS, "cost": dict(collector.cost), "trials": safe(collector.trials), "fits": collector.fit_slots,
        "seed_results": collector.seed_results, "metrics": collector.metrics,
        "model_fingerprints": {seed: {name: item["parameter_fingerprint"] for name, item in group.items()} for seed, group in models.items()},
        "complete_prediction_population": [{key: item[key] for key in ("seed", "model", "horizon", "origin_active_index", "status", "available")} for item in collector.predictions],
        "streams": {name: {"path": name+".jsonl.gz", "format": "gzip_jsonl", "identity_scope": "decoded_jsonl",
            "records": item["records"], "bytes": item["bytes"], "sha256": item["hash"].hexdigest()} for name, item in collector.streams.items()},
        "training_label_source": "fresh_same_trial_native_next_v_only_not_seen_prediction_endpoints",
        "state_fit_counter_translation": "shared_IV2_reused_state_fit_scalar_label_uses_renamed_new_state_fit_scalar_label_uses_at_each_fresh_add",
        "new_unique_training_scalar_labels": collector.cost["new_state_fit_scalar_label_uses"], "reused_training_labels": 0,
        "seen_evaluation_development_only": True, "heldout_validation": False, "bias_calibration_label_uses": 0,
        "evaluation_fit_label_uses": 0, "new_evaluation_physics": 0, "old_model_prediction_calls": 0, "old_fit_or_gate_recomputations": 0,
        "RLS_updates": 0, "prior_physics_control_calls": 535345, "prior_physics_substeps": 2815018, "historical_RLS_scalar_updates": 125652,
        "runtime": {"python": sys.version, "numpy": np.__version__, "mujoco": getattr(collector, "runtime_mujoco", None),
            "platform": platform.platform(), "cpu": platform.processor() or "unknown", "logical_cpu_count": os.cpu_count(), "GPU_used": False},
        "physics_and_lstsq_internal_work": "unmeasured_unknown_not_zero", "unmeasured_import_IO": "unknown_not_zero",
        "timing_excludes": "final_JSON_encoding_and_payload_writes", "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    try:
        (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    except BaseException as exc:
        payload_failure(exc, "run_JSON_write")
    print(json.dumps({"experiment_id": "IV3", "status": status, "output": str(output), "cost": dict(collector.cost), "failure": failure}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
