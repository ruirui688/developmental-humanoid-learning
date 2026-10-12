"""IV1: one native continuous dither identification, then fresh fixed prediction."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
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

SOURCE_PATH = "scripts/develop_instrumental_action_response.py"
MODULE_PATH = "src/developmental_physics/instrumental_action_model.py"
PROTOCOL_PATH = "docs/INSTRUMENTAL_ACTION_RESPONSE_PROTOCOL.md"
PROTOCOL_PIN = {'bytes': 11144, 'sha256': '476e3292b52817ab3c3c8686bb9115b09ae7c17105cf4d0f0f6aed1f0f421e33'}
SOURCE_PATHS = (SOURCE_PATH, MODULE_PATH, PROTOCOL_PATH, "src/developmental_physics/__init__.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py",
    "src/developmental_physics/environment.py", "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/guard_coupled_pair_model.py",
    "src/developmental_physics/local_pair_model.py", "src/developmental_physics/full_request_pair_development.py")
MODEL_PATH = "results/cpu_validation/2026-10-12_equilibrium_feedforward_control/raw/models.json"
MODEL_PIN = {"bytes": 60924, "sha256": "3cfbd871c275a8f5d8a07615a239ee9e8192b5e93dcf35104cf61a01f6a6a992"}
EF1B_SOURCE = "f9f500706364aab32bd18047266d4b06358e4473"
FR4A_SOURCE = "f4fca3f4236acddc92a25c6707f9c29150ee3ca6"
SEEDS = (8101, 8102, 8103)
MODEL_NAMES = ("cold", "oldlearned", "corrected")
HORIZONS = (1, 10, 20, 50, 150)
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
    "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
    "c4_contact_scientific_validation": False}
BOUNDS = {"identification_controls": 9000, "prediction_source_controls": 6000,
    "total_controls": 15000, "physics_substeps": 15000, "native_IV_label_scalar_uses": 12000,
    "IV_fit_attempts": 3, "IV_fitted_coefficients": 24, "prediction_records": 4329,
    "prediction_pair_calls": 187020, "RLS": 0, "fork_controls": 0, "old_math_recomputations": 0}


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
    result = np.asarray(value, dtype=np.float64)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(name+"_must_be_finite_"+str(shape))
    return result


def native(observation):
    q = finite("native_q8", observation["joint_position"], (8,))
    v = finite("native_v8", observation["joint_velocity"], (8,))
    return q[:2], v[:2]


def study_abort(observation, qref):
    q, v = native(observation)
    triggers = [{"axis": i, "signal": name} for i in range(2) for name, condition in
        (("q_minus_qref", abs(q[i]-qref[i]) >= .12), ("velocity", abs(v[i]) >= 1.)) if condition]
    return None if not triggers else {"type": "StudyAbort", "triggers": triggers, "q2": q, "v2": v}


def directions_targets(qref, ranges):
    directions = np.where(ranges[:, 1]-qref >= qref-ranges[:, 0], 1., -1.)
    targets = [qref+directions*distance for distance in (.04, .08)]
    if any(np.any(target < ranges[:, 0]+.03) or np.any(target > ranges[:, 1]-.03) for target in targets):
        raise ValueError("fixed_original_target_infeasible_no_clipping")
    return directions, targets


def pd(q, v, target, limit):
    with np.errstate(over="raise", invalid="raise"):
        raw = finite("raw_public_PD", 64.*(target-q)-4.*v, (2,))
    return np.clip(raw, -limit, limit)


def prediction_pulse(index):
    block, slot = divmod(index // 10, 20)
    axes = ((1., 0.), (0., 1.), (1., 1.), (1., -1.), (1., 1.))[block]
    amplitude = (.125, .25, .375, .5, .375)[block]
    sign = 1. if slot == 1 else -1. if slot == 9 else 0.
    return sign*amplitude*np.asarray(axes)


class StudyStop(RuntimeError):
    pass


class NativeMeter:
    """Process-local API counters; original environment and backend unchanged."""
    def __init__(self, module, cost):
        self.module, self.cost = module, cost
        factory = self.wrap("MjModel_from_xml_path", module.MjModel.from_xml_path)
        self.MjModel = type("CountedModelFactory", (), {"from_xml_path": staticmethod(factory)})
        self.MjData = self.wrap("MjData_build", module.MjData)
        for name in ("mj_step", "mj_forward", "mj_resetData", "mj_contactForce"):
            setattr(self, name, self.wrap(name, getattr(module, name)))

    def wrap(self, name, function):
        def counted(*args, **kwargs):
            self.cost[name+"_attempts"] += 1
            try:
                result = function(*args, **kwargs)
            except BaseException:
                self.cost[name+"_exceptions"] += 1
                raise
            self.cost[name+"_returns"] += 1
            return result
        return counted

    def __getattr__(self, name):
        return getattr(self.module, name)


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
    if PROTOCOL_PIN is None:
        raise ValueError("protocol_pin_must_be_frozen")
    blobs = {}
    for name in SOURCE_PATHS:
        cost["source_file_reads"] += 1
        blobs[name] = (repo / name).read_bytes()
        cost["source_bytes_read"] += len(blobs[name])
        if blobs[name] != git(["show", commit+":"+name]):
            raise ValueError("source_bytes_differ:"+name)
    if pin(blobs[PROTOCOL_PATH]) != PROTOCOL_PIN:
        raise ValueError("frozen_protocol_identity_differs")
    return {"commit": commit, "clean_committed_bytes_verified": True,
            "files": {name: pin(blob) for name, blob in blobs.items()}}, blobs


def snapshot_fingerprint(snapshot):
    excluded = {"parameter_fingerprint", "trainable", "vector_update_count", "scalar_update_count", "output_update_counts",
                "update_commit", "initial_prior", "input_boundary"}
    return hashlib.sha256(json.dumps({key: value for key, value in snapshot.items() if key not in excluded},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Collector:
    def __init__(self, repo, output):
        self.repo, self.output, self.cost = repo, output, Counter()
        self.source, self.model_identity, self.context = None, None, None
        self.models, self.initial_snapshots, self.moments, self.fingerprints = {}, {}, {}, {}
        self.handles, self.streams, self.seed_results = {}, {}, []
        self.trials = [{"seed": seed, "kind": kind, "trial_id": f"s{seed}_{kind}",
            "planned_controls": count, "status": "not_attempted", "contact_qualification": None,
            "stage_telemetry": {}, "stop": None} for seed in SEEDS for kind, count in (("identification", 3000), ("prediction", 2000))]
        self.predictions = [{"seed": seed, "model": name, "horizon": h, "origin_active_index": origin,
            "status": "not_attempted", "available": False} for seed in SEEDS for h in HORIZONS
            for name in MODEL_NAMES for origin in range(0, 1000-h+1, 10)]
        self.metrics = {"complete_population": False, "iv1_prediction_gate_passed": False, "checks": [], **FLAGS}

    def open_streams(self):
        for name in ("source_trace", "predictions"):
            self.handles[name] = gzip.open(self.output / (name+".jsonl.gz"), "xb")
            self.streams[name] = {"records": 0, "bytes": 0, "hash": hashlib.sha256()}

    def write(self, name, row):
        self.cost["JSONL_encode_attempts"] += 1
        blob = (json.dumps(safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode()
        self.cost["JSONL_encode_returns"] += 1
        self.cost["JSONL_write_attempts"] += 1
        self.handles[name].write(blob)
        self.handles[name].flush()
        self.cost["JSONL_write_returns"] += 1
        self.cost["JSONL_decoded_bytes_written"] += len(blob)
        item = self.streams[name]
        item["records"] += 1
        item["bytes"] += len(blob)
        item["hash"].update(blob)

    def load_models(self):
        sys.path.insert(0, str(self.repo / "src"))
        self.body = importlib.import_module("developmental_physics.instrumental_action_model")
        if Path(self.body.__file__).resolve() != (self.repo / MODULE_PATH).resolve():
            raise ValueError("canonical_native_model_module_required")
        self.cost["model_file_read_attempts"] += 1
        blob = (self.repo / MODEL_PATH).read_bytes()
        self.cost["model_file_read_returns"] += 1
        self.cost["model_bytes_read"] += len(blob)
        self.model_identity = pin(blob)
        if self.model_identity != MODEL_PIN:
            raise ValueError("fixed_EF1B_model_identity_differs")
        snapshots = json.loads(blob)
        if set(snapshots) != {str(seed) for seed in SEEDS}:
            raise ValueError("three_fixed_development_seeds_required")
        for seed in SEEDS:
            if set(snapshots[str(seed)]) != {"cold", "learned"}:
                raise ValueError("two_original_snapshots_per_seed_required")
            for saved_name, name in (("cold", "cold"), ("learned", "oldlearned")):
                item = snapshots[str(seed)][saved_name]
                updates = 0 if saved_name == "cold" else 4000
                self.cost["initial_snapshot_fingerprint_checks"] += 1
                if (snapshot_fingerprint(item) != item["parameter_fingerprint"] or item["trainable"] is not False
                    or item["structure"] != "coupled_hinge9" or item["dt_seconds"] != .002
                    or item["vector_update_count"] != updates or item["scalar_update_count"] != 2*updates
                    or item["input_mapping"]["basis"] != "known_angle_guard"):
                    raise ValueError("original_frozen_FR4A_snapshot_required")
                guard = item["input_mapping"]["public_guard"]
                if guard["angle_margin_rad"] != .03 or guard["request_clip_per_axis_nm"] != .5:
                    raise ValueError("original_public_guard_required")
                self.cost["initial_theta_scalar_reads"] += 18
                model = self.body.InstrumentalActionBodyModel(item["qref_rad"], guard["public_joint_ranges_rad"], item["coefficients"])
                self.cost["native_model_builds"] += 1
                self.models[(seed, name)] = model
                self.initial_snapshots[(seed, name)] = item
                self.fingerprints[(seed, name)] = model.parameter_fingerprint()

    def step(self, env, request, trial, row, qref):
        self.context = {"seed": trial["seed"], "kind": trial["kind"], "control_index": row["control_index"]}
        if self.cost["total_control_attempts"] >= 15000:
            raise ValueError("fixed_control_budget_exhausted")
        before, original_error = env.physics_steps, None
        kind = trial["kind"]
        self.cost["total_control_attempts"] += 1
        self.cost[kind+"_control_attempts"] += 1
        try:
            result = env.step(request)
            self.cost[kind+"_control_returns"] += 1
            self.cost["total_control_returns"] += 1
            row.update(returned=True, observation_after=safe(result.observation), diagnostics=safe(result.diagnostics))
            paid = env.physics_steps-before
            row["confirmed_physics_substeps"] = paid
            self.write("source_trace", {"paid_native_endpoint": row})
            if paid != 1 or result.diagnostics["executed_substeps"] != 1:
                raise StudyStop("partial_or_stopped_interval")
            native(result.observation)
            actual = finite("actual_actuator_torque8", result.observation["actuator_torque"], (8,))
            guarded = finite("guarded_applied_request8", result.diagnostics["applied_torque"], (8,))
            stage = row["stage"]
            telemetry = trial["stage_telemetry"].setdefault(stage, {"captured_substeps": 0,
                "actual_absolute_axis8_nm_s": np.zeros(8), "actual_squared_axis8_nm2_s": np.zeros(8),
                "requested_absolute_axis8_nm_s": np.zeros(8), "requested_squared_axis8_nm2_s": np.zeros(8),
                "guarded_absolute_axis8_nm_s": np.zeros(8), "guarded_squared_axis8_nm2_s": np.zeros(8),
                "positive_contact_endpoints": {"left_arm": 0, "feet": 0, "other": 0},
                "positive_normal_force_impulse_n_s": {"left_arm": 0., "feet": 0., "other": 0.}})
            telemetry["captured_substeps"] += 1
            telemetry["actual_absolute_axis8_nm_s"] += np.abs(actual)*.002
            telemetry["actual_squared_axis8_nm2_s"] += actual**2*.002
            telemetry["requested_absolute_axis8_nm_s"] += np.abs(request)*.002
            telemetry["requested_squared_axis8_nm2_s"] += request**2*.002
            telemetry["guarded_absolute_axis8_nm_s"] += np.abs(guarded)*.002
            telemetry["guarded_squared_axis8_nm2_s"] += guarded**2*.002
            self.cost["effort_requested_guarded_actual_scalar_samples"] += 24
            abort = study_abort(result.observation, qref) if qref is not None else None
            stop = StudyStop("original_environment_stop_or_StudyAbort") if result.terminated or abort else None
            if stop:
                row["stop"] = {"environment_reason": result.reason, "study_abort": abort}
                trial["stop"] = safe(row["stop"])
            try:
                contacts = env.audit_floor_pairs()
                row["audit_contacts"] = contacts
                for category in ("left_arm", "feet", "other"):
                    positives = [pair["positive_normal_force_n"] for pair in contacts["floor_pairs"] if pair["category"] == category]
                    telemetry["positive_contact_endpoints"][category] += int(any(value > 0. for value in positives))
                    telemetry["positive_normal_force_impulse_n_s"][category] += sum(positives)*.002
            except BaseException as contact_exc:
                if stop is None:
                    raise
                stop.secondary_contact_failure = {"type": type(contact_exc).__name__, "message": str(contact_exc)}
            if stop:
                raise stop
            return result.observation
        except BaseException as exc:
            original_error = exc
            self.cost[kind+("_endpoint_processing_exceptions" if row["returned"] else "_control_exceptions")] += 1
            row["failure"] = {"type": type(exc).__name__, "message": str(exc)}
            raise
        finally:
            paid = env.physics_steps-before
            row["confirmed_physics_substeps"] = paid
            self.cost["confirmed_physics_substeps"] += paid
            self.cost[kind+"_confirmed_physics_substeps"] += paid
            try:
                self.write("source_trace", row)
            except BaseException as write_exc:
                if original_error is None:
                    raise
                original_error.partial_write_failure = {"type": type(write_exc).__name__, "message": str(write_exc)}

    def collect(self, free, seed, kind):
        trial = next(item for item in self.trials if item["seed"] == seed and item["kind"] == kind)
        trial["status"] = "running"
        try:
            self.cost["source_environment_constructor_attempts"] += 1
            env = free.FreeRootFastFeedbackGroundBodyEnv(audit_cost=self.cost)
            self.cost["source_environment_constructor_returns"] += 1
            self.cost["explicit_reset_attempts"] += 1
            observation = env.reset(seed=seed, pose="supine")
            self.cost["explicit_reset_returns"] += 1
            if env.control_dt != .002 or env.config.control_substeps != 1:
                raise ValueError("original_2ms_environment_required")
            trial["metadata_before"] = safe(env.frozen_metadata())
            ranges = finite("fresh_public_ranges", env.model.jnt_range[env._joint_ids][:2], (2, 2))
            qref, targets, active_records = None, None, []
            if kind == "identification":
                rng = np.random.Generator(np.random.PCG64(seed+100000))
                self.cost["PCG64_Generator_builds"] += 1
                trial["random_seed"] = seed+100000
            for index in range(trial["planned_controls"]):
                active = index-1000
                if active == 0:
                    qref, _ = native(observation)
                    names = ("cold", "oldlearned") if kind == "identification" else MODEL_NAMES
                    for name in names:
                        model = self.models[(seed, name)]
                        if not np.array_equal(qref, model.qref) or not np.array_equal(ranges, model.ranges):
                            raise ValueError("fresh_prefix_qref_or_ranges_not_exact_snapshot_match")
                    directions, targets = directions_targets(qref, ranges)
                    trial.update(qref2=qref.tolist(), public_ranges2=ranges.tolist(), directions2=directions.tolist(), targets2=safe(targets))
                    if kind == "identification":
                        self.moments[seed] = self.body.ActionIVMoments(self.models[(seed, "oldlearned")], self.cost)
                request, info = np.zeros(8), {}
                stage = "prefix" if active < 0 else ("A" if active < 1000 else "B") if kind == "identification" else "active"
                if active >= 0:
                    q, v = native(observation)
                    self.cost[kind+"_public_PD_attempts"] += 1
                    if kind == "identification":
                        target = targets[0 if active < 1000 else 1]
                        base = pd(q, v, target, .375)
                        bits = rng.integers(0, 2, size=2)
                        dither = (2*bits-1)*.125
                        self.cost["Rademacher_pair_draws"] += 1
                        request[:2] = base+dither
                        info = {"current_target_q2": target, "known_base2": base, "dither_bits2": bits, "known_dither2": dither}
                    else:
                        base = pd(q, v, qref, .5)
                        excitation = prediction_pulse(active)
                        request[:2] = np.clip(base+excitation, -.5, .5)
                        info = {"current_target_q2": qref, "public_PD_request2": base, "pulse2": excitation}
                    self.cost[kind+"_public_PD_returns"] += 1
                    if np.any(np.abs(request[:2]) > .5) or not np.isfinite(request).all():
                        raise ValueError("finite_final_request_inside_original_permission_required")
                row = {"seed": seed, "trial_id": trial["trial_id"], "kind": kind, "control_index": index,
                    "active_index": active, "stage": stage, "phase": "prefix" if active < 0 else "active",
                    "observation_before": safe(observation), "requested_torque8": request.tolist(), "returned": False, **safe(info)}
                after = self.step(env, request, trial, row, qref)
                if active >= 0:
                    active_records.append(row)
                    if kind == "identification":
                        _, next_v = native(after)
                        annotation = self.moments[seed].add(q, v, base, dither, next_v)
                        row["IV_native_annotation"] = safe(annotation)
                        self.write("source_trace", {"IV_native_annotation": {"seed": seed, "active_index": active, **annotation}})
                observation = after
            trial["metadata_after"] = safe(env.frozen_metadata())
            if trial["metadata_after"] != trial["metadata_before"]:
                raise ValueError("source_environment_metadata_changed")
            required = ("prefix", "A", "B") if kind == "identification" else ("prefix", "active")
            trial["contact_qualification"] = {"required_stages": required, "passed": all(
                trial["stage_telemetry"][stage]["positive_contact_endpoints"]["left_arm"] >= 1 for stage in required),
                "selection_use": "complete_phase_qualification_only_no_actor_or_label_use"}
            if not trial["contact_qualification"]["passed"]:
                raise StudyStop("complete_contact_domain_qualification_failed_no_recollection")
            trial["status"] = "completed"
            return active_records
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
                    rq, rv = (finite("full_population_RMSE", np.sqrt(np.mean(np.square(errors), axis=0)), (2,)) for errors in (errors_q, errors_v))
                self.cost["new_axis_RMSE_vector_computations"] += 2
                hrow["models"][name] = {"available": True, "observed_origin_count": len(errors_q),
                    "q_rmse_axis_rad": rq.tolist(), "v_rmse_axis_rad_s": rv.tolist(), "partial_subset_ranking": False}
        self.seed_results.append({"seed": seed, "prediction_scores": summary, "oldlearned_all_metrics_reported": True})

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
                    base, candidate = models["cold"][key], models["corrected"][key]
                    bases.append(base)
                    candidates.append(candidate)
                    passed = all(candidate[i] < base[i] if strict else candidate[i] <= base[i] for i in range(2))
                    checks.append({"seed": row["seed"], "horizon": h, "signal": signal, "available": True,
                        "gated": gated, "strict": strict, "passed": bool(passed), "cold_axis": base,
                        "corrected_axis": candidate, "oldlearned_axis": models["oldlearned"][key],
                        "oldlearned_minus_cold_axis": [models["oldlearned"][key][i]-base[i] for i in range(2)],
                        "corrected_minus_oldlearned_axis": [candidate[i]-models["oldlearned"][key][i] for i in range(2)]})
                    self.cost["oldlearned_report_RMSE_scalar_differences"] += 4
                if strict:
                    available = len(bases) == 3 and np.isfinite(bases).all() and np.isfinite(candidates).all()
                    bm, cm = (np.mean(values, axis=0) for values in (bases, candidates)) if available else (None, None)
                    fractions = [(float(bm[i]-cm[i])/float(bm[i]) if bm[i] > 0. else None) for i in range(2)] if available else None
                    self.cost["three_seed_raw_RMSE_mean_comparisons"] += 1
                    checks.append({"scope": "three_seed_raw_RMSE_mean", "horizon": h, "signal": signal,
                        "available": bool(available), "cold_axis_mean": safe(bm), "corrected_axis_mean": safe(cm),
                        "improvement_fractions": fractions, "required_improvement": .20,
                        "passed": bool(available and all(value is not None and value >= .20 for value in fractions))})
        passed = complete and all(row["passed"] for row in checks if row.get("gated", True))
        self.metrics = {"complete_population": complete, "iv1_prediction_gate_passed": bool(passed), "checks": checks,
            "mean_type": "arithmetic mean of original per_seed axis RMSE", "partial_subset_ranking": False, **FLAGS}

    def run(self):
        import mujoco
        core = importlib.import_module("developmental_physics.environment")
        free = importlib.import_module("developmental_physics.free_root_fast_feedback_environment")
        for module, relative in ((core, SOURCE_PATHS[5]), (free, SOURCE_PATHS[4])):
            if Path(module.__file__).resolve() != (self.repo / relative).resolve():
                raise ValueError("canonical_environment_module_required")
        meter, original = NativeMeter(mujoco, self.cost), (core.mujoco, free.mujoco)
        self.runtime_mujoco = mujoco.__version__
        core.mujoco = free.mujoco = meter
        try:
            for seed in SEEDS:
                self.collect(free, seed, "identification")
                if self.moments[seed].samples != 2000:
                    raise ValueError("exact_2000_native_IV_pairs_required")
                self.context = {"seed": seed, "stage": "IV_first_fit"}
                corrected = self.moments[seed].fit_once()
                self.models[(seed, "corrected")] = corrected
                self.fingerprints[(seed, "corrected")] = corrected.parameter_fingerprint()
                records = self.collect(free, seed, "prediction")
                self.score(seed, records)
            for key, model in self.models.items():
                self.cost["frozen_native_model_fingerprint_checks"] += 1
                if model.parameter_fingerprint() != self.fingerprints[key]:
                    raise ValueError("frozen_prediction_model_changed")
            for key, snapshot in self.initial_snapshots.items():
                self.cost["original_snapshot_fingerprint_checks_after"] += 1
                if snapshot_fingerprint(snapshot) != snapshot["parameter_fingerprint"]:
                    raise ValueError("original_initial_snapshot_changed")
            if (self.cost["total_control_attempts"] != 15000 or self.cost["confirmed_physics_substeps"] != 15000
                or self.cost["new_IV_scalar_label_uses"] != 12000 or self.cost["IV_fit_returns"] != 3
                or any(item["status"] != "completed" for item in self.trials)
                or any(not item["available"] for item in self.predictions)):
                raise ValueError("full_fixed_IV1_population_required")
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
    if output.exists() or output == repo or repo.is_relative_to(output) or (repo / MODEL_PATH).resolve().is_relative_to(output):
        parser.error("existing_or_repository_or_model_containing_output_refused")
    output.mkdir(parents=True, exist_ok=False)
    collector, failure, status = Collector(repo, output), None, "failed"
    wall, cpu = time.perf_counter(), time.process_time()
    def payload_failure(exc, stage):
        nonlocal failure, status
        collector.metrics["iv1_prediction_gate_passed"] = False
        collector.metrics["complete_population"] = False
        detail = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        if failure is None:
            status, failure = "failed", {**detail, "context": collector.context, "traceback": traceback.format_exc()}
        else:
            failure.setdefault("secondary_payload_failures", []).append(detail)
        traceback.print_exc()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                collector.source, blobs = source_gate(repo, args.source_commit, collector.cost)
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name, blob in blobs.items():
                        archive.writestr(name, blob)
                (output / "source.zip").write_bytes(buffer.getvalue())
                collector.cost["source_archive_bytes_written"] = len(buffer.getvalue())
                collector.load_models()
                collector.open_streams()
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
    collector.cost["wall_seconds"], collector.cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    models = {str(seed): {name: {**model.record(), "parameter_fingerprint": model.parameter_fingerprint(),
        "fingerprint_before_prediction": collector.fingerprints[(seed, name)],
        "initial_snapshot_fingerprint": collector.initial_snapshots.get((seed, "oldlearned" if name == "corrected" else name), {}).get("parameter_fingerprint"),
        "nonaction_columns_frozen": [0, 1, 2, 3, 8] if name == "corrected" else None,
        "action_columns_replaced": [4, 5, 6, 7] if name == "corrected" else None}
        for (model_seed, name), model in collector.models.items() if model_seed == seed} for seed in SEEDS}
    moments = {str(seed): collector.moments[seed].record() if seed in collector.moments else
        {"samples": 0, "fit_attempted": False, "fit": None, "status": "not_attempted",
         "M_z_action_transpose": None, "Y_z_native_residual_transpose": None} for seed in SEEDS}
    for filename, data in (("models.json", models), ("moments.json", moments), ("metrics.json", collector.metrics)):
        try:
            (output / filename).write_text(json.dumps(safe(data), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
        except BaseException as exc:
            payload_failure(exc, filename+"_write")
    report = {"experiment_id": "IV1", "status": status, "first_failure": failure, "source": collector.source,
        "runtime": {"python": sys.version, "python_version": platform.python_version(), "numpy": np.__version__,
            "mujoco": getattr(collector, "runtime_mujoco", None), "platform": platform.platform(),
            "cpu": platform.processor() or "unknown", "logical_cpu_count": os.cpu_count(), "GPU_used": False},
        "config": {"seeds": SEEDS, "prefix": 1000, "identification_active": 2000, "prediction_active": 1000,
            "dt_seconds": .002, "PD_Kp": 64., "PD_Kd": 4., "identification_base_clip_nm": .375,
            "Rademacher_dose_nm": .125, "RNG": "Generator(PCG64(seed+100000))", "RNG_draw_API": "rng.integers(0, 2, size=2)", "RNG_axis_order": [0, 1], "fit_rcond": 128*np.finfo(np.float64).eps,
            "targets_offset_rad": (.04, .08), "H": HORIZONS, "prediction_stride": 10, "study_q_rad": .12, "study_v_rad_s": 1.},
        "model_source": {"path": MODEL_PATH, "identity": collector.model_identity, "EF1B_commit": EF1B_SOURCE, "FR4A_commit": FR4A_SOURCE},
        "planned_upper_bounds": BOUNDS, "cost": dict(collector.cost), "trials": safe(collector.trials),
        "seed_results": collector.seed_results, "metrics": collector.metrics,
        "model_fingerprints": {seed: {name: {key: item[key] for key in
            ("parameter_fingerprint", "fingerprint_before_prediction", "initial_snapshot_fingerprint")}
            for name, item in group.items()} for seed, group in models.items()},
        "complete_prediction_population": [{key: item[key] for key in ("seed", "model", "horizon", "origin_active_index", "status", "available")} for item in collector.predictions],
        "streams": {name: {"path": name+".jsonl.gz", "format": "gzip_jsonl", "identity_scope": "decoded_jsonl",
            "records": item["records"], "bytes": item["bytes"], "sha256": item["hash"].hexdigest()} for name, item in collector.streams.items()},
        "fit_label_source": "fresh_continuous_native_next_velocity_only", "fork_label_uses": 0, "opaque_state_uses": 0,
        "RLS_updates": 0, "controller_inverse_solves": 0, "old_math_recomputations": 0, "old_trace_or_prediction_reads": 0,
        "control_candidate_opened": False, "physics_internal_forward_work": "unmeasured_unknown_not_zero",
        "lstsq_internal_factorization_work": "unmeasured_unknown_not_zero", "unmeasured_filesystem_and_import_IO": "unknown_not_zero",
        "timing_excludes": "final_JSON_encoding_and_payload_writes", "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    try:
        (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    except BaseException as exc:
        payload_failure(exc, "run_JSON_write")
    print(json.dumps({"experiment_id": "IV1", "status": status, "output": str(output), "cost": dict(collector.cost), "failure": failure}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
