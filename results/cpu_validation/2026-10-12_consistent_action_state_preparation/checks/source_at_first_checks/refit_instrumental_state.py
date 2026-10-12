"""IV2: one fixed-action native state refit, then fresh phase-shift prediction."""
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

# This frozen helper imports no physical backend at module import. Its globals
# are never changed; IV2 owns its population, phase, source gate and scoring.
_spec = importlib.util.spec_from_file_location("_iv2_frozen_iv1_helper",
    Path(__file__).with_name("develop_instrumental_action_response.py"))
iv1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(iv1)
safe, pin, finite, native, pd = iv1.safe, iv1.pin, iv1.finite, iv1.native, iv1.pd
StudyStop, NativeMeter = iv1.StudyStop, iv1.NativeMeter

SOURCE_PATH = "scripts/refit_instrumental_state.py"
MODULE_PATH = "src/developmental_physics/consistent_action_state_model.py"
PROTOCOL_PATH = "docs/CONSISTENT_ACTION_STATE_PROTOCOL.md"
PROTOCOL_PIN = {"bytes": 9884, "sha256": "69e95dc62732a2da1e9d6879125e0419bd57d4796d9e2970c654510380554914"}
SOURCE_PATHS = (SOURCE_PATH, MODULE_PATH, PROTOCOL_PATH,
    "scripts/develop_instrumental_action_response.py",
    "src/developmental_physics/instrumental_action_model.py",
    "src/developmental_physics/__init__.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py",
    "src/developmental_physics/environment.py", "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/guard_coupled_pair_model.py",
    "src/developmental_physics/local_pair_model.py", "src/developmental_physics/full_request_pair_development.py")
INPUT_BASE = "results/cpu_validation/2026-10-12_instrumental_action_response/raw"
INPUT_PINS = {
    "run.json": {"bytes": 875053, "sha256": "d8531ce2a63819451ac0a294b28c1cf60a5ffd376945cd9ea3c383a3ded354f5"},
    "models.json": {"bytes": 15911, "sha256": "923f73ffea0de6f200204e0961134297a50abe128df840eb1f872505e6fc7756"},
    "source_trace.jsonl.gz": {"bytes": 15282107, "sha256": "c2ded7e3a54fc74befb0cea7eba17bf6b65dd2ac6e3562c3d40f4900abc354a6"},
}
IV1_SOURCE = "d7eb8508f2872e24212d7e3580951c7c44fe8228"
SEEDS = (8101, 8102, 8103)
MODEL_NAMES = ("cold", "oldlearned", "IV1", "newmatched")
HORIZONS = (1, 10, 20, 50, 150)
FLAGS = dict(iv1.FLAGS)
BOUNDS = {"new_training_controls": 0, "prediction_source_controls": 6000,
    "total_controls": 6000, "physics_substeps": 6000, "reused_state_fit_scalar_label_uses": 12000,
    "state_fit_attempts": 3, "state_fitted_coefficients": 30, "prediction_records": 5772,
    "prediction_pair_calls": 249360, "prediction_velocity_head_outputs": 498720,
    "RLS": 0, "fork_controls": 0, "old_math_recomputations": 0}


def prediction_pulse(index):
    if type(index) is not int or not 0 <= index < 1000:
        raise ValueError("fixed_prediction_active_index_required")
    block, slot = divmod(index // 10, 20)
    axes = ((1., 0.), (0., 1.), (1., 1.), (1., -1.), (1., 1.))[block]
    amplitude = (.125, .25, .375, .5, .375)[block]
    sign = 1. if slot == 3 else -1. if slot == 13 else 0.
    return sign*amplitude*np.asarray(axes)


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
        cost["source_file_read_attempts"] += 1
        blobs[name] = (repo / name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_bytes_read"] += len(blobs[name])
        if blobs[name] != git(["show", commit+":"+name]):
            raise ValueError("source_bytes_differ:"+name)
    if pin(blobs[PROTOCOL_PATH]) != PROTOCOL_PIN:
        raise ValueError("frozen_protocol_identity_differs")
    return {"commit": commit, "clean_committed_bytes_verified": True,
        "files": {name: pin(blob) for name, blob in blobs.items()}}, blobs


class Collector(iv1.Collector):
    def __init__(self, repo, output):
        # Do not construct the old three-model/identification population.
        self.repo, self.output, self.cost = repo, output, Counter()
        self.source, self.context, self.input_run = None, None, None
        self.input_identities, self.input_snapshots = {}, {}
        self.models, self.moments, self.fingerprints = {}, {}, {}
        self.handles, self.streams, self.seed_results = {}, {}, []
        self.source_trials = {}
        self.trials = [{"seed": seed, "kind": "prediction", "trial_id": f"s{seed}_prediction",
            "planned_controls": 2000, "status": "not_attempted", "contact_qualification": None,
            "stage_telemetry": {}, "stop": None} for seed in SEEDS]
        self.fit_slots = [{"seed": seed, "planned_samples": 2000, "status": "not_attempted",
            "fit_attempted": False, "available": False} for seed in SEEDS]
        self.predictions = [{"seed": seed, "model": name, "horizon": h, "origin_active_index": origin,
            "status": "not_attempted", "available": False} for seed in SEEDS for h in HORIZONS
            for name in MODEL_NAMES for origin in range(0, 1000-h+1, 10)]
        self.metrics = {"complete_population": False, "iv2_prediction_gate_passed": False, "checks": [], **FLAGS}

    def input_blob(self, filename):
        self.context = {"stage": "input_identity", "filename": filename}
        self.cost["IV1_input_file_read_attempts"] += 1
        blob = (self.repo / INPUT_BASE / filename).read_bytes()
        self.cost["IV1_input_file_read_returns"] += 1
        self.cost["IV1_input_bytes_read"] += len(blob)
        self.cost["IV1_input_hash_attempts"] += 1
        identity = pin(blob)
        self.cost["IV1_input_hash_returns"] += 1
        self.cost["IV1_input_bytes_hashed"] += len(blob)
        self.input_identities[filename] = identity
        if identity != INPUT_PINS[filename]:
            raise ValueError("fixed_IV1_input_identity_differs:"+filename)
        return blob

    def parse_json(self, blob):
        self.cost["IV1_JSON_parse_attempts"] += 1
        result = json.loads(blob)
        self.cost["IV1_JSON_parse_returns"] += 1
        return result

    def load_and_fit(self):
        sys.path.insert(0, str(self.repo / "src"))
        self.body = importlib.import_module("developmental_physics.consistent_action_state_model")
        if Path(self.body.__file__).resolve() != (self.repo / MODULE_PATH).resolve():
            raise ValueError("canonical_native_state_model_module_required")
        run_blob, model_blob, trace_blob = (self.input_blob(name) for name in INPUT_PINS)
        run, snapshots = self.parse_json(run_blob), self.parse_json(model_blob)
        self.input_run = run
        expected = {(seed, kind): count for seed in SEEDS for kind, count in
            (("identification", 3000), ("prediction", 2000))}
        trials = run.get("trials", [])
        config, source, cost = run.get("config", {}), run.get("source", {}), run.get("cost", {})
        if (run.get("experiment_id") != "IV1" or run.get("status") != "completed" or run.get("first_failure") is not None
            or source.get("commit") != IV1_SOURCE or source.get("clean_committed_bytes_verified") is not True
            or config.get("seeds") != list(SEEDS) or config.get("prefix") != 1000
            or config.get("identification_active") != 2000 or config.get("prediction_active") != 1000
            or config.get("dt_seconds") != .002 or config.get("PD_Kp") != 64. or config.get("PD_Kd") != 4.
            or config.get("study_q_rad") != .12 or config.get("study_v_rad_s") != 1.
            or cost.get("total_control_attempts") != 15000 or cost.get("confirmed_physics_substeps") != 15000
            or cost.get("new_IV_scalar_label_uses") != 12000 or cost.get("IV_fit_returns") != 3
            or run.get("RLS_updates") != 0 or run.get("metrics", {}).get("complete_population") is not True
            or len(trials) != 6 or set(snapshots) != {str(seed) for seed in SEEDS}):
            raise ValueError("complete_fixed_IV1_source_identity_and_population_required")
        for trial in trials:
            key = (trial.get("seed"), trial.get("kind"))
            qualification = trial.get("contact_qualification") or {}
            stages = ["prefix", "A", "B"] if key[1] == "identification" else ["prefix", "active"]
            if (key not in expected or key in self.source_trials or trial.get("planned_controls") != expected[key]
                or trial.get("trial_id") != f"s{key[0]}_{key[1]}" or trial.get("status") != "completed"
                or trial.get("stop") is not None or qualification.get("passed") is not True
                or qualification.get("required_stages") != stages
                or trial.get("metadata_before") != trial.get("metadata_after")
                or any(trial.get("stage_telemetry", {}).get(stage, {}).get("captured_substeps") != 1000
                       or trial.get("stage_telemetry", {}).get(stage, {}).get("positive_contact_endpoints", {}).get("left_arm", 0) < 1
                       for stage in stages)):
                raise ValueError("saved_original_complete_contact_and_effort_qualification_required")
            self.source_trials[key] = trial
        if set(self.source_trials) != set(expected):
            raise ValueError("all_six_original_IV1_trials_required")
        for seed in SEEDS:
            group = snapshots[str(seed)]
            if set(group) != {"cold", "oldlearned", "corrected"}:
                raise ValueError("all_three_original_frozen_models_required")
            for input_name, name in (("cold", "cold"), ("oldlearned", "oldlearned"), ("corrected", "IV1")):
                item = group[input_name]
                self.context = {"stage": "frozen_model_restore", "seed": seed, "model": name}
                self.cost["initial_theta_scalar_reads"] += 18
                model = self.body.InstrumentalActionBodyModel(item["qref_rad"], item["public_joint_ranges_rad"], item["coefficients"])
                self.cost["native_model_builds"] += 1
                self.cost["input_native_fingerprint_checks"] += 1
                fingerprint = model.parameter_fingerprint()
                if (item.get("parameter_fingerprint") != fingerprint or item.get("fingerprint_before_prediction") != fingerprint
                    or any(item.get(key) != value for key, value in model.record().items())
                    or run.get("model_fingerprints", {}).get(str(seed), {}).get(input_name, {}).get("parameter_fingerprint") != fingerprint):
                    raise ValueError("original_immutable_coupled_hinge9_snapshot_required")
                trial = self.source_trials[(seed, "identification")]
                if model.qref.tobytes() != np.asarray(trial["qref2"], dtype=np.float64).tobytes() or model.ranges.tobytes() != np.asarray(trial["public_ranges2"], dtype=np.float64).tobytes():
                    raise ValueError("source_qref_and_public_ranges_exact_model_identity_required")
                self.models[(seed, name)] = model
                self.input_snapshots[(seed, name)] = item
                self.fingerprints[(seed, name)] = fingerprint
            self.moments[seed] = self.body.StateConsistencyFit(self.models[(seed, "IV1")], self.cost)
        selector = self.body.NativeIdentificationStream(SEEDS, 2000, self.cost)
        with gzip.GzipFile(fileobj=io.BytesIO(trace_blob), mode="rb") as stream:
            for line_index, line in enumerate(stream):
                self.context = {"stage": "saved_native_selection", "line_index": line_index}
                self.cost["IV1_gzip_decoded_lines"] += 1
                self.cost["IV1_gzip_decoded_bytes"] += len(line)
                row = self.parse_json(line)
                selected = selector.accept(row)
                if selected is not None:
                    seed, index = selected["seed"], selected["index"]
                    self.context.update(seed=seed, active_index=index)
                    annotation = self.moments[seed].add(selected["q"], selected["v"], selected["request"], selected["next_v"])
                    self.write("source_trace", {"kind": "reused_native_state_fit", "source_file": "IV1/source_trace.jsonl.gz",
                        "source_decoded_line_index": line_index, "seed": seed, "active_index": index,
                        "q2": selected["q"], "v2": selected["v"], "next_q2": selected["next_q"],
                        "known_final_request2": selected["request"], **annotation})
        self.selected_source_counts = selector.finish()
        if any(self.moments[seed].samples != 2000 for seed in SEEDS):
            raise ValueError("complete_three_seed_2000_population_required_before_any_fit")
        for slot in self.fit_slots:
            seed = slot["seed"]
            self.context = {"stage": "state_first_fit", "seed": seed}
            slot.update(status="attempted", fit_attempted=True)
            try:
                model = self.moments[seed].fit_once()
                self.models[(seed, "newmatched")] = model
                self.fingerprints[(seed, "newmatched")] = model.parameter_fingerprint()
                if model.theta[:, 4:8].tobytes() != self.models[(seed, "IV1")].theta[:, 4:8].tobytes():
                    raise ValueError("eight_frozen_action_coefficients_must_be_bitwise_unchanged")
                slot.update(status="completed", available=True, fitted_coefficient_count=10,
                    initial_IV1_fingerprint=self.fingerprints[(seed, "IV1")], frozen_fingerprint=self.fingerprints[(seed, "newmatched")])
            except BaseException as exc:
                slot.update(status="failed", failure={"type": type(exc).__name__, "message": str(exc)})
                raise

    def step(self, env, request, trial, row, qref):
        if self.cost["total_control_attempts"] >= 6000:
            raise ValueError("fixed_IV2_control_budget_exhausted")
        return super().step(env, request, trial, row, qref)

    def collect(self, free, seed):
        trial = next(item for item in self.trials if item["seed"] == seed)
        trial["status"] = "running"
        try:
            self.context = {"stage": "fresh_prediction_constructor", "seed": seed}
            self.cost["source_environment_constructor_attempts"] += 1
            env = free.FreeRootFastFeedbackGroundBodyEnv(audit_cost=self.cost)
            self.cost["source_environment_constructor_returns"] += 1
            self.cost["explicit_reset_attempts"] += 1
            observation = env.reset(seed=seed, pose="supine")
            self.cost["explicit_reset_returns"] += 1
            if env.control_dt != .002 or env.config.control_substeps != 1:
                raise ValueError("original_2ms_environment_required")
            trial["metadata_before"] = safe(env.frozen_metadata())
            if trial["metadata_before"] != self.source_trials[(seed, "prediction")]["metadata_before"]:
                raise ValueError("original_physical_and_protection_identity_required")
            ranges = finite("fresh_public_ranges", env.model.jnt_range[env._joint_ids][:2], (2, 2))
            qref, records = None, []
            for index in range(2000):
                active = index-1000
                if active == 0:
                    qref, _ = native(observation)
                    qref = qref.copy()
                    for name in MODEL_NAMES:
                        model = self.models[(seed, name)]
                        if qref.tobytes() != model.qref.tobytes() or ranges.tobytes() != model.ranges.tobytes():
                            raise ValueError("fresh_prefix_qref_or_ranges_not_exact_snapshot_match")
                    trial.update(qref2=qref.tolist(), public_ranges2=ranges.tolist())
                request, info = np.zeros(8), {}
                if active >= 0:
                    q, v = native(observation)
                    self.cost["prediction_public_PD_attempts"] += 1
                    base = pd(q, v, qref, .5)
                    excitation = prediction_pulse(active)
                    request[:2] = np.clip(base+excitation, -.5, .5)
                    info = {"current_target_q2": qref, "public_PD_request2": base, "pulse2": excitation}
                    self.cost["prediction_public_PD_returns"] += 1
                    self.cost["new_phase_pulse_pair_outputs"] += 1
                    if np.any(np.abs(request[:2]) > .5) or not np.isfinite(request).all():
                        raise ValueError("finite_final_request_inside_original_permission_required")
                row = {"seed": seed, "trial_id": trial["trial_id"], "kind": "prediction", "control_index": index,
                    "active_index": active, "stage": "prefix" if active < 0 else "active",
                    "phase": "prefix" if active < 0 else "active", "observation_before": safe(observation),
                    "requested_torque8": request.tolist(), "returned": False, **safe(info)}
                observation = self.step(env, request, trial, row, qref)
                if active >= 0:
                    records.append(row)
            trial["metadata_after"] = safe(env.frozen_metadata())
            if trial["metadata_after"] != trial["metadata_before"]:
                raise ValueError("source_environment_metadata_changed")
            trial["contact_qualification"] = {"required_stages": ["prefix", "active"], "passed": all(
                trial["stage_telemetry"][stage]["captured_substeps"] == 1000 and
                trial["stage_telemetry"][stage]["positive_contact_endpoints"]["left_arm"] >= 1
                for stage in ("prefix", "active")),
                "selection_use": "complete_phase_qualification_only_no_actor_or_label_use"}
            if not trial["contact_qualification"]["passed"]:
                raise StudyStop("complete_contact_domain_qualification_failed_no_recollection")
            trial["status"] = "completed"
            return records
        except BaseException as exc:
            trial["status"] = "stopped" if isinstance(exc, StudyStop) else "failed"
            trial["failure"] = {"type": type(exc).__name__, "message": str(exc)}
            raise

    def score(self, seed, records):
        summary = {"horizons": {}, "condition": "saved known future requests offline; recursive own predicted q/v"}
        for h in HORIZONS:
            hrow = summary["horizons"][str(h)] = {"planned_origin_count": len(range(0, 1000-h+1, 10)), "models": {}}
            for name in MODEL_NAMES:
                model = self.models[(seed, name)]
                errors_q, errors_v = [], []
                for slot in (item for item in self.predictions if item["seed"] == seed and item["horizon"] == h and item["model"] == name):
                    self.context = {key: slot[key] for key in ("seed", "model", "horizon", "origin_active_index")}
                    slot["status"] = "attempted"
                    segment = records[slot["origin_active_index"]:slot["origin_active_index"]+h]
                    if len(segment) != h or not all(row["returned"] and row["confirmed_physics_substeps"] == 1 for row in segment):
                        raise ValueError("full_fixed_prediction_population_required_no_partial_ranking")
                    q, v = native(segment[0]["observation_before"])
                    requests = [row["requested_torque8"][:2] for row in segment]
                    slot.update(model_input={"q2": q.tolist(), "v2": v.tolist(), "known_requests2": requests},
                        model_fingerprint=model.parameter_fingerprint(), predicted_q_path=[], predicted_v_path=[])
                    original_error = None
                    try:
                        for request in requests:
                            q, v = model.predict(q, v, request, self.cost)
                            slot["predicted_q_path"].append(q.tolist())
                            slot["predicted_v_path"].append(v.tolist())
                        aq, av = native(segment[-1]["observation_after"])
                        with np.errstate(over="raise", invalid="raise"):
                            dq, dv = finite("endpoint_q_error", q-aq, (2,)), finite("endpoint_v_error", v-av, (2,))
                        self.cost["new_prediction_endpoint_scalar_label_uses"] += 4
                        self.cost["prediction_endpoint_error_scalar_outputs"] += 4
                        slot.update(status="completed", available=True, actual_endpoint_q2=aq.tolist(), actual_endpoint_v2=av.tolist(),
                            q_error_rad=dq.tolist(), v_error_rad_s=dv.tolist())
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
                    rq, rv = (finite("full_population_RMSE", np.sqrt(np.mean(np.square(errors), axis=0)), (2,))
                        for errors in (errors_q, errors_v))
                self.cost["new_axis_RMSE_vector_computations"] += 2
                hrow["models"][name] = {"available": True, "observed_origin_count": len(errors_q),
                    "q_rmse_axis_rad": rq.tolist(), "v_rmse_axis_rad_s": rv.tolist(), "partial_subset_ranking": False}
        self.seed_results.append({"seed": seed, "prediction_scores": summary, "oldlearned_and_IV1_all_metrics_reported": True})

    def gate(self):
        checks = []
        complete = len(self.seed_results) == 3 and {row["seed"] for row in self.seed_results} == set(SEEDS)
        for h in HORIZONS:
            for signal in ("q", "v"):
                key = "q_rmse_axis_rad" if signal == "q" else "v_rmse_axis_rad_s"
                strict = (h, signal) in ((10, "v"), (150, "q"))
                gated = h != 1 and (h, signal) != (10, "q")
                bases, candidates = [], []
                for row in self.seed_results:
                    models = row["prediction_scores"]["horizons"][str(h)]["models"]
                    base, candidate = models["cold"][key], models["newmatched"][key]
                    bases.append(base)
                    candidates.append(candidate)
                    passed = all(candidate[i] < base[i] if strict else candidate[i] <= base[i] for i in range(2))
                    checks.append({"seed": row["seed"], "horizon": h, "signal": signal, "available": True,
                        "gated": gated, "strict": strict, "passed": bool(passed), "cold_axis": base,
                        "newmatched_axis": candidate, "oldlearned_axis": models["oldlearned"][key], "IV1_axis": models["IV1"][key],
                        "model_minus_cold_axis": {name: [models[name][key][i]-base[i] for i in range(2)] for name in MODEL_NAMES[1:]},
                        "newmatched_minus_oldlearned_axis": [candidate[i]-models["oldlearned"][key][i] for i in range(2)],
                        "newmatched_minus_IV1_axis": [candidate[i]-models["IV1"][key][i] for i in range(2)]})
                    self.cost["all_model_report_RMSE_scalar_differences"] += 10
                if strict:
                    available = len(bases) == 3 and np.isfinite(bases).all() and np.isfinite(candidates).all()
                    bm, cm = (np.mean(values, axis=0) for values in (bases, candidates)) if available else (None, None)
                    fractions = [(float(bm[i]-cm[i])/float(bm[i]) if bm[i] > 0. else None) for i in range(2)] if available else None
                    self.cost["three_seed_raw_RMSE_mean_comparisons"] += 1
                    checks.append({"scope": "three_seed_raw_RMSE_mean", "horizon": h, "signal": signal,
                        "available": bool(available and all(value is not None for value in fractions)),
                        "cold_axis_mean": safe(bm), "newmatched_axis_mean": safe(cm),
                        "improvement_fractions": fractions, "required_improvement": .20,
                        "passed": bool(available and all(value is not None and value >= .20 for value in fractions))})
        passed = complete and all(row["passed"] for row in checks if row.get("gated", True))
        self.metrics = {"complete_population": complete, "iv2_prediction_gate_passed": bool(passed), "checks": checks,
            "mean_type": "arithmetic mean of original per_seed axis RMSE", "partial_subset_ranking": False, **FLAGS}

    def run(self):
        import mujoco
        core = importlib.import_module("developmental_physics.environment")
        free = importlib.import_module("developmental_physics.free_root_fast_feedback_environment")
        for module, relative in ((core, "src/developmental_physics/environment.py"),
                                 (free, "src/developmental_physics/free_root_fast_feedback_environment.py")):
            if Path(module.__file__).resolve() != (self.repo / relative).resolve():
                raise ValueError("canonical_environment_module_required")
        meter, original = NativeMeter(mujoco, self.cost), (core.mujoco, free.mujoco)
        self.runtime_mujoco = mujoco.__version__
        core.mujoco = free.mujoco = meter
        try:
            for seed in SEEDS:
                records = self.collect(free, seed)
                self.score(seed, records)
            for key, model in self.models.items():
                self.cost["frozen_native_model_fingerprint_checks"] += 1
                if model.parameter_fingerprint() != self.fingerprints[key]:
                    raise ValueError("frozen_prediction_model_changed")
            if (self.cost["total_control_attempts"] != 6000 or self.cost["confirmed_physics_substeps"] != 6000
                or self.cost["reused_state_fit_scalar_label_uses"] != 12000 or self.cost["state_fit_returns"] != 3
                or self.cost["state_fitted_coefficient_scalar_outputs"] != 30 or self.cost["pair_prediction_returns"] != 249360
                or self.cost["scalar_velocity_head_returns"] != 498720
                or any(item["status"] != "completed" for item in self.trials)
                or any(not item["available"] for item in self.predictions)):
                raise ValueError("full_fixed_IV2_population_required")
            self.gate()
        finally:
            core.mujoco, free.mujoco = original


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
        collector.metrics["iv2_prediction_gate_passed"] = False
        collector.metrics["complete_population"] = False
        detail = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        if failure is None:
            status, failure = "failed", {**detail, "context": collector.context, "traceback": traceback.format_exc()}
        else:
            failure.setdefault("secondary_payload_failures", []).append(detail)
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                collector.open_streams()
                collector.source, blobs = source_gate(repo, args.source_commit, collector.cost)
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, blob in blobs.items():
                        archive.writestr(name, blob)
                archive_blob = buffer.getvalue()
                (output / "source.zip").write_bytes(archive_blob)
                collector.cost["source_archive_bytes_written"] = len(archive_blob)
                collector.load_and_fit()
                collector.run()
                status = "completed"
            except BaseException as exc:
                status = "stopped" if isinstance(exc, StudyStop) else "failed"
                failure = {"type": type(exc).__name__, "message": str(exc), "context": collector.context,
                    "traceback": traceback.format_exc(), "unconfirmed_native_work": "unknown_if_native_exception",
                    "partial_write_failure": getattr(exc, "partial_write_failure", None),
                    "secondary_contact_failure": getattr(exc, "secondary_contact_failure", None)}
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
        "fingerprint_before_prediction": collector.fingerprints[(seed, name)],
        "initial_IV1_fingerprint": collector.fingerprints.get((seed, "IV1")) if name == "newmatched" else None,
        "input_snapshot_fingerprint": collector.input_snapshots.get((seed, name), {}).get("parameter_fingerprint"),
        "state_columns_replaced": [0, 1, 2, 3, 8] if name == "newmatched" else None,
        "action_columns_frozen": [4, 5, 6, 7] if name == "newmatched" else None}
        for (model_seed, name), model in collector.models.items() if model_seed == seed} for seed in SEEDS}
    moments = {str(seed): collector.moments[seed].record() if seed in collector.moments else
        {"samples": 0, "fit_attempted": False, "fit": None, "status": "not_attempted",
         "Psi_native_state_5": [], "Y_native_minus_fixed_action_2": []} for seed in SEEDS}
    for filename, data in (("models.json", models), ("moments.json", moments), ("metrics.json", collector.metrics)):
        try:
            (output / filename).write_text(json.dumps(safe(data), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
        except BaseException as exc:
            payload_failure(exc, filename+"_write")
    report = {"experiment_id": "IV2", "status": status, "first_failure": failure, "source": collector.source,
        "runtime": {"python": sys.version, "python_version": platform.python_version(), "numpy": np.__version__,
            "mujoco": getattr(collector, "runtime_mujoco", None), "platform": platform.platform(),
            "cpu": platform.processor() or "unknown", "logical_cpu_count": os.cpu_count(), "GPU_used": False},
        "config": {"seeds": SEEDS, "prefix": 1000, "reused_identification_active": 2000, "prediction_active": 1000,
            "dt_seconds": .002, "PD_Kp": 64., "PD_Kd": 4., "PD_clip_nm": .5, "final_request_clip_nm": .5,
            "pulse_directions": [[1, 0], [0, 1], [1, 1], [1, -1], [1, 1]], "pulse_amplitudes_nm": [.125, .25, .375, .5, .375],
            "pulse_block_microsteps": 200, "positive_slot": 3, "negative_slot": 13, "slot_microsteps": 10,
            "fit_rcond": 128*np.finfo(np.float64).eps, "fit_design_shape": [2000, 5], "fit_label_shape": [2000, 2],
            "state_columns_replaced": [0, 1, 2, 3, 8], "action_columns_frozen": [4, 5, 6, 7],
            "models": MODEL_NAMES, "H": HORIZONS, "prediction_stride": 10, "study_q_rad": .12, "study_v_rad_s": 1.},
        "model_source": {"base": INPUT_BASE, "IV1_source_commit": IV1_SOURCE, "required_pins": INPUT_PINS,
            "actual_identities": collector.input_identities, "old_prediction_trace_read": False},
        "input_saved_qualification": [{"seed": trial["seed"], "kind": trial["kind"], "status": trial["status"],
            "contact_qualification": trial["contact_qualification"], "stage_telemetry": trial["stage_telemetry"]}
            for trial in collector.source_trials.values()],
        "selected_source_counts": getattr(collector, "selected_source_counts", None),
        "planned_upper_bounds": BOUNDS, "cost": dict(collector.cost), "fits": collector.fit_slots,
        "trials": safe(collector.trials), "seed_results": collector.seed_results, "metrics": collector.metrics,
        "model_fingerprints": {seed: {name: {key: item[key] for key in
            ("parameter_fingerprint", "fingerprint_before_prediction", "initial_IV1_fingerprint", "input_snapshot_fingerprint")}
            for name, item in group.items()} for seed, group in models.items()},
        "complete_prediction_population": [{key: item[key] for key in ("seed", "model", "horizon", "origin_active_index", "status", "available")} for item in collector.predictions],
        "streams": {name: {"path": name+".jsonl.gz", "format": "gzip_jsonl", "identity_scope": "decoded_jsonl",
            "records": item["records"], "bytes": item["bytes"], "sha256": item["hash"].hexdigest()} for name, item in collector.streams.items()},
        "fit_label_source": "IV1_top_level_continuous_active_identification_native_next_velocity_only",
        "new_unique_training_scalar_labels": 0, "new_training_physics_controls": 0, "RLS_updates": 0,
        "historical_RLS_scalar_updates": 125652, "prior_physics_control_calls": 529345, "prior_physics_substeps": 2809018,
        "fork_label_uses": 0, "opaque_state_uses": 0, "controller_inverse_solves": 0, "old_math_recomputations": 0,
        "old_prediction_file_reads": 0, "old_source_trace_reads": int("source_trace.jsonl.gz" in collector.input_identities),
        "control_candidate_opened": False, "physics_internal_forward_work": "unmeasured_unknown_not_zero",
        "lstsq_internal_factorization_work": "unmeasured_unknown_not_zero", "unmeasured_filesystem_and_import_IO": "unknown_not_zero",
        "timing_excludes": "final_JSON_encoding_and_payload_writes", "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    try:
        (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    except BaseException as exc:
        payload_failure(exc, "run_JSON_write")
    print(json.dumps({"experiment_id": "IV2", "status": status, "output": str(output), "cost": dict(collector.cost), "failure": failure}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
