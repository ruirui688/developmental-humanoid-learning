"""PAR1: fixed matched-state finite action response; no learned controller."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
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

SOURCE_PATH = "scripts/diagnose_paired_action_response.py"
PROTOCOL_PATH = "docs/PAIRED_ACTION_RESPONSE_DIAGNOSTIC_PROTOCOL.md"
PROTOCOL_PIN = {'bytes': 10425, 'sha256': '8ce717c5a80b9c70185c8bbc3c0839417e3ee9209423d3fb27de80687c79526d'}
SOURCE_PATHS = (SOURCE_PATH, PROTOCOL_PATH, "src/developmental_physics/__init__.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py",
    "src/developmental_physics/environment.py", "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/guard_pair_model.py")
MODEL_PATH = "results/cpu_validation/2026-10-12_equilibrium_feedforward_control/raw/models.json"
MODEL_PIN = {"bytes": 60924, "sha256": "3cfbd871c275a8f5d8a07615a239ee9e8192b5e93dcf35104cf61a01f6a6a992"}
EF1B_SOURCE = "f9f500706364aab32bd18047266d4b06358e4473"
FR4A_SOURCE = "f4fca3f4236acddc92a25c6707f9c29150ee3ca6"
SEEDS, MODELS, ORIGINS = (8101, 8102, 8103), ("cold", "learned"), (0, 500, 1000, 1500)
SIDES = ((0, -1), (0, 1), (1, -1), (1, 1))
ATTRS = ("last_command", "step_id", "physics_steps", "_reset_done", "terminated", "reason")
EPS = 128. * np.finfo(np.float64).eps
FLAGS = {"scientific_adoption": False, "old_free_root_C4_validation": False,
    "c4_scientific_validation": False, "c5_scientific_dependency_released": False,
    "c4_contact_scientific_validation": False}
BOUNDS = {"source_controls": 9000, "qualification_controls": 12, "side_controls": 48,
    "total_controls": 9060, "physics_substeps": 9060, "origins": 12, "planned_sides": 48,
    "pre_data_copies": 12, "fork_data_copies": 60, "theta_scalars_read": 108,
    "finite_effect_pairs": 48, "model_response_pairs": 96, "fit": 0, "RLS": 0, "model_predict": 0}


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


def native(observation):
    q = finite("native_q8", observation["joint_position"], (8,))
    v = finite("native_v8", observation["joint_velocity"], (8,))
    return q[:2], v[:2]


def study_abort(observation, qref):
    q, v = native(observation)
    triggers = [{"axis": i, "signal": signal} for i in range(2) for signal, condition in
        (("q_minus_qref", abs(q[i]-qref[i]) >= .12), ("velocity", abs(v[i]) >= 1.)) if condition]
    return None if not triggers else {"type": "StudyAbort", "triggers": triggers, "q2": q.tolist(), "v2": v.tolist()}


def project(q, request, ranges, cost=None):
    if cost is not None:
        cost["public_projection_pair_attempts"] += 1
        cost["public_projection_input_scalar_uses"] += 8
    q, request = finite("q", q, (2,)), finite("request", request, (2,))
    ranges = finite("public_ranges", ranges, (2, 2))
    if np.any(np.abs(request) > .5):
        raise ValueError("model_input_request_outside_permission_no_clip")
    blocked = ((q <= ranges[:, 0]+.03) & (request < 0.)) | ((q >= ranges[:, 1]-.03) & (request > 0.))
    projected = np.where(blocked, 0., request)
    if cost is not None:
        cost["public_projection_pair_returns"] += 1
        cost["projected_command_scalar_outputs"] += 2
    return projected, blocked


def side_request(base, axis, sign):
    request = finite("base_request", base, (2,)).copy()
    request[axis] += sign*.125
    return request, bool(np.all(np.abs(request) <= .5))


def model_effect(q, base, side, ranges, theta, cost):
    cost["model_response_pair_attempts"] += 1
    try:
        theta = finite("theta", theta, (2, 9))
        g0, _ = project(q, base, ranges, cost)
        g1, _ = project(q, side, ranges, cost)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            h0, h1 = (np.sign(g)*np.maximum(np.abs(g)-.25, 0.) for g in (g0, g1))
            cost["signed_hinge_scalar_evaluations"] += 4
            features = finite("finite_input_difference", [*(g1-g0), *(h1-h0)], (4,))
            cost["finite_input_difference_scalar_outputs"] += 4
            cost["finite_input_difference_scalar_uses"] += 8
            cost["model_coefficient_scalar_uses"] += 8
            cost["model_algebra_2x4_matvec_attempts"] += 1
            result = finite("model_finite_response", theta[:, 4:8] @ features, (2,))
            cost["model_algebra_2x4_matvec_returns"] += 1
        cost["model_response_pair_returns"] += 1
        cost["model_response_scalar_outputs"] += 2
        return result
    except BaseException:
        cost["model_response_pair_exceptions"] += 1
        raise


def effect_summary(base_v, side_v, predicted, cost):
    base_v, side_v = finite("base_v", base_v, (2,)), finite("side_v", side_v, (2,))
    cost["finite_effect_pair_attempts"] += 1
    cost["endpoint_velocity_scalar_uses_for_response"] += 4
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        effect = finite("actual_finite_response", side_v-base_v, (2,))
        tolerance = float(EPS*max(1., float(np.sum(np.abs(base_v))+np.sum(np.abs(side_v)))))
        cost["signal_tolerance_evaluations"] += 1
        cost["endpoint_velocity_scalar_uses_for_tolerance"] += 4
        finite("signal_tolerance", tolerance, ())
        errors = {name: finite("model_response_error", finite(name, value, (2,))-effect, (2,)).tolist()
                  for name, value in predicted.items()}
        cost["response_residual_scalar_outputs"] += 2*len(predicted)
        cost["response_residual_operand_scalar_uses"] += 4*len(predicted)
    cost["finite_effect_pair_returns"] += 1
    cost["new_response_scalar_labels"] += 2
    cost["model_comparison_scalar_label_uses"] += 2*len(predicted)
    weak_axes = np.abs(effect) <= tolerance
    cost["weak_signal_axis_comparisons"] += 2
    return {"actual_response_v2": effect.tolist(), "model_response_v2": safe(predicted), "model_error_v2": errors,
            "signal_tolerance_rad_s": tolerance, "weak_signal_axis": weak_axes.tolist(),
            "weak_signal": bool(np.all(weak_axes))}


def python_state(env):
    return {key: deepcopy(getattr(env, key)) for key in ATTRS}


def restore_python(env, state):
    for key in ATTRS:
        setattr(env, key, deepcopy(state[key]))


def same_python(first, second):
    return all(first[key].tobytes() == second[key].tobytes() if isinstance(first[key], np.ndarray)
               else type(first[key]) is type(second[key]) and first[key] == second[key] for key in ATTRS)


class StudyStop(RuntimeError):
    pass


class NativeMeter:
    """Process-local transparent API counters; production source is unchanged."""
    def __init__(self, module, cost):
        self.module, self.cost = module, cost
        factory = self.wrap("MjModel_from_xml_path", module.MjModel.from_xml_path)
        self.MjModel = type("CountedModelFactory", (), {"from_xml_path": staticmethod(factory)})
        self.MjData = self.wrap("MjData_build", module.MjData)
        for name in ("mj_step", "mj_forward", "mj_resetData", "mj_copyData", "mj_getState", "mj_stateSize", "mj_contactForce"):
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
    return {"commit": commit, "clean_committed_bytes_verified": True, "files": {name: pin(blob) for name, blob in blobs.items()}}, blobs


def fingerprint(snapshot):
    excluded = {"parameter_fingerprint", "trainable", "vector_update_count", "scalar_update_count", "output_update_counts",
                "update_commit", "initial_prior", "input_boundary"}
    record = {key: value for key, value in snapshot.items() if key not in excluded}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Collector:
    def __init__(self, repo, output):
        self.repo, self.output, self.cost = repo, output, Counter()
        self.source, self.model_identity, self.models, self.opaque = None, None, {}, {}
        self.origins, self.source_trials, self.context = [], [], None
        self.sides = [{"seed": seed, "origin_active_index": origin, "axis": axis, "sign": sign, "status": "not_attempted"}
                      for seed in SEEDS for origin in ORIGINS for axis, sign in SIDES]
        self.effort = {name: {"captured_substeps": 0, "actual_absolute_axis_nm_s": [0., 0.],
            "actual_squared_axis_nm2_s": [0., 0.]} for name in ("source", "qualification", "side")}
        self.streams, self.handles = {}, {}

    def open_streams(self):
        for name in ("source_trace", "fork_trace"):
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
        self.cost["JSONL_bytes_written"] += len(blob)
        entry = self.streams[name]
        entry["records"] += 1
        entry["bytes"] += len(blob)
        entry["hash"].update(blob)

    def load_models(self):
        self.cost["model_file_read_attempts"] += 1
        blob = (self.repo / MODEL_PATH).read_bytes()
        self.cost["model_file_read_returns"] += 1
        self.cost["model_bytes_read"] += len(blob)
        self.model_identity = pin(blob)
        if self.model_identity != MODEL_PIN:
            raise ValueError("fixed_EF1B_model_file_identity_differs")
        snapshots = json.loads(blob)
        if set(snapshots) != {str(seed) for seed in SEEDS}:
            raise ValueError("three_fixed_development_seeds_required")
        for seed in SEEDS:
            if set(snapshots[str(seed)]) != set(MODELS):
                raise ValueError("two_models_per_seed_required")
            for name in MODELS:
                item = snapshots[str(seed)][name]
                count = 0 if name == "cold" else 4000
                self.cost["snapshot_fingerprint_checks"] += 1
                if (fingerprint(item) != item["parameter_fingerprint"] or item["trainable"] is not False
                    or item["structure"] != "coupled_hinge9" or item["dt_seconds"] != .002
                    or item["vector_update_count"] != count or item["scalar_update_count"] != 2*count
                    or item["input_mapping"]["basis"] != "known_angle_guard"):
                    raise ValueError("fixed_frozen_FR4A_snapshot_required")
                guard = item["input_mapping"]["public_guard"]
                if guard["angle_margin_rad"] != .03 or guard["request_clip_per_axis_nm"] != .5:
                    raise ValueError("original_public_guard_required")
                arrays = {"theta": finite("theta", item["coefficients"], (2, 9)),
                    "qref": finite("qref", item["qref_rad"], (2,)),
                    "ranges": finite("ranges", guard["public_joint_ranges_rad"], (2, 2))}
                self.cost["theta_scalars_read"] += 18
                for array in arrays.values():
                    array.flags.writeable = False
                self.models[(seed, name)] = {"snapshot": item, "before": item["parameter_fingerprint"],
                    "theta_bytes_before": pin(arrays["theta"].tobytes()), **arrays}

    def state(self, env, key):
        vector = np.empty(self.state_size)
        self.mj.mj_getState(env.model, env.data, vector, self.state_spec)
        finite("opaque_integration_state", vector, (self.state_size,))
        self.opaque[key] = vector.copy()
        return vector, python_state(env)

    def step(self, env, request, group, row, qref):
        self.context = {key: row.get(key) for key in ("seed", "origin_active_index", "control_index", "axis", "sign")}
        row.update(requested_torque8=safe(request), observation_before=safe(env.observation()), returned=False)
        before = env.physics_steps
        if self.cost["total_control_attempts"] >= 9060:
            raise ValueError("fixed_control_budget_exhausted")
        original_error = None
        self.cost[group+"_control_attempts"] += 1
        self.cost["total_control_attempts"] += 1
        try:
            result = env.step(request)
            self.cost[group+"_control_returns"] += 1
            row.update(returned=True, observation_after=safe(result.observation), diagnostics=safe(result.diagnostics))
        except BaseException as exc:
            original_error = exc
            self.cost[group+"_control_exceptions"] += 1
            row["failure"] = {"type": type(exc).__name__, "message": str(exc), "unconfirmed_native_work": "unknown_not_zero"}
            raise
        finally:
            paid = env.physics_steps-before
            row["confirmed_physics_substeps"] = paid
            self.cost["confirmed_physics_substeps"] += paid
            self.cost[group+"_confirmed_physics_substeps"] += paid
            try:
                self.write("source_trace" if group == "source" else "fork_trace", row)
            except BaseException as write_exc:
                if original_error is None:
                    raise
                original_error.partial_write_failure = {"type": type(write_exc).__name__, "message": str(write_exc)}
        if paid != 1 or result.diagnostics["executed_substeps"] != 1:
            raise StudyStop("partial_or_stopped_interval")
        native(result.observation)
        actual = finite("actual_actuator_torque8", result.observation["actuator_torque"], (8,))
        for axis in range(2):
            self.effort[group]["actual_absolute_axis_nm_s"][axis] += abs(float(actual[axis]))*.002
            self.effort[group]["actual_squared_axis_nm2_s"][axis] += float(actual[axis])**2*.002
        self.effort[group]["captured_substeps"] += 1
        abort = study_abort(result.observation, qref) if qref is not None else None
        if result.terminated or abort:
            row["stop"] = {"environment_reason": result.reason, "study_abort": abort}
            stop = StudyStop("original_environment_stop_or_StudyAbort")
            try:
                self.write("source_trace" if group == "source" else "fork_trace", {"stop_annotation": row})
            except BaseException as write_exc:
                stop.partial_write_failure = {"type": type(write_exc).__name__, "message": str(write_exc)}
            raise stop
        if self.cost["total_control_attempts"] > 9060 or self.cost["confirmed_physics_substeps"] > 9060:
            raise ValueError("fixed_control_or_physics_budget_exceeded")
        return result.observation

    def forks(self, env, original_data, pre_data, fork_data, before, after, observation, base_observation, u0, seed, origin, qref, ranges):
        label = f"s{seed}_o{origin}"
        before_vector, before_attrs = before
        after_vector, after_attrs = after
        saved = {"seed": seed, "origin_active_index": origin, "pre_python_state": safe(before_attrs),
                 "base_endpoint_python_state": safe(after_attrs), "qualification": "not_attempted", "sides": []}
        self.origins.append(saved)
        original_error = None
        try:
            for group, axis, sign in (("qualification", None, None), *(("side", axis, sign) for axis, sign in SIDES)):
                slot = saved if group == "qualification" else next(item for item in self.sides if
                    (item["seed"], item["origin_active_index"], item["axis"], item["sign"]) == (seed, origin, axis, sign))
                request, permitted = (u0.copy(), True) if axis is None else side_request(u0, axis, sign)
                if not permitted:
                    slot.update(status="unavailable", unavailable_reason="outside_permission_no_clip", requested2=request.tolist())
                    saved["sides"].append(slot)
                    continue
                self.cost["fork_data_copy_attempts"] += 1
                self.mj.mj_copyData(fork_data, env.model, pre_data)
                self.cost["fork_data_copy_returns"] += 1
                env.data = fork_data
                restore_python(env, before_attrs)
                key = label+("_qualification" if axis is None else f"_a{axis}_{sign}")
                state, attrs = self.state(env, key+"_pre")
                if state.tobytes() != before_vector.tobytes() or not same_python(attrs, before_attrs):
                    raise ValueError("complete_fork_prestate_not_exact")
                slot.update(status="attempted", requested2=request.tolist(), pre_python_state=safe(attrs))
                row = {"seed": seed, "origin_active_index": origin, "group": group, "axis": axis, "sign": sign}
                request8 = np.zeros(8)
                request8[:2] = request
                side_observation = self.step(env, request8, group, row, qref)
                endpoint, endpoint_attrs = self.state(env, key+"_endpoint")
                if group == "qualification":
                    if endpoint.tobytes() != after_vector.tobytes() or not same_python(endpoint_attrs, after_attrs):
                        raise ValueError("same_request_clone_endpoint_not_exact")
                    saved["qualification"] = "passed_exact_pre_and_endpoint"
                    continue
                q, _ = native(observation)
                g0, block0 = project(q, u0, ranges, self.cost)
                g1, block1 = project(q, request, ranges, self.cost)
                self.cost["base_endpoint_reuse_pair_reads"] += 1
                self.cost["side_endpoint_pair_reads"] += 1
                predicted = {name: model_effect(q, u0, request, ranges, self.models[(seed, name)]["theta"], self.cost) for name in MODELS}
                _, base_v = native(base_observation)
                _, side_v = native(side_observation)
                values = effect_summary(base_v, side_v, predicted, self.cost)
                no_input = bool(np.array_equal(g0, g1))
                slot.update(status="unavailable" if no_input or values["weak_signal"] else "finite_response_available",
                    unavailable_reason="guard_zero_effective_input" if no_input else "weak_signal" if values["weak_signal"] else None,
                    base_request2=u0.tolist(), projected_base2=g0.tolist(), projected_side2=g1.tolist(),
                    base_guard_blocked=block0.tolist(), side_guard_blocked=block1.tolist(),
                    crossed_hinge_axis=[any(min(g0[i], g1[i]) < cut < max(g0[i], g1[i]) for cut in (-.25, .25)) for i in range(2)],
                    hinge_cut_at_start_axis=[bool(g0[i] in (-.25, .25)) for i in range(2)],
                    hinge_cut_at_endpoint_axis=[bool(g1[i] in (-.25, .25)) for i in range(2)],
                    zero_request_cut_at_start_axis=(u0 == 0.).tolist(),
                    zero_request_cut_at_endpoint_axis=(request == 0.).tolist(),
                    crossed_zero_request_axis=[bool(min(u0[i], request[i]) < 0. < max(u0[i], request[i])) for i in range(2)],
                    guard_branch_changed_axis=(block0 != block1).tolist(), endpoint_python_state=safe(endpoint_attrs), **values)
                saved["sides"].append(slot)
                self.write("fork_trace", {"finite_response_annotation": slot})
        except BaseException as exc:
            original_error = exc
            raise
        finally:
            try:
                env.data = original_data
                restore_python(env, after_attrs)
                restored, attrs = self.state(env, label+"_source_restored")
                if restored.tobytes() != after_vector.tobytes() or not same_python(attrs, after_attrs):
                    raise ValueError("original_source_endpoint_was_polluted")
            except BaseException as restore_exc:
                if original_error is None:
                    raise
                original_error.source_restore_failure = {"type": type(restore_exc).__name__, "message": str(restore_exc)}

    def run_physics(self):
        import mujoco
        sys.path.insert(0, str(self.repo / "src"))
        core = importlib.import_module("developmental_physics.environment")
        free = importlib.import_module("developmental_physics.free_root_fast_feedback_environment")
        for module, path in ((core, SOURCE_PATHS[4]), (free, SOURCE_PATHS[3])):
            if Path(module.__file__).resolve() != (self.repo / path).resolve():
                raise ValueError("canonical_environment_module_required")
        self.mj = NativeMeter(mujoco, self.cost)
        self.runtime_mujoco = mujoco.__version__
        old = (core.mujoco, free.mujoco)
        core.mujoco = free.mujoco = self.mj
        try:
            for seed in SEEDS:
                self.cost["source_environment_constructor_attempts"] += 1
                env = free.FreeRootFastFeedbackGroundBodyEnv(audit_cost=self.cost)
                self.cost["source_environment_constructor_returns"] += 1
                self.cost["explicit_reset_attempts"] += 1
                observation = env.reset(seed=seed, pose="supine")
                self.cost["explicit_reset_returns"] += 1
                if env.control_dt != .002 or env.config.control_substeps != 1:
                    raise ValueError("original_2ms_environment_required")
                metadata = safe(env.frozen_metadata())
                trial = {"seed": seed, "planned_source_controls": 3000, "status": "running", "metadata_before": metadata}
                self.source_trials.append(trial)
                self.state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
                self.state_size = self.mj.mj_stateSize(env.model, self.state_spec)
                pre_data, fork_data = self.mj.MjData(env.model), self.mj.MjData(env.model)
                ranges = finite("fresh_public_ranges", env.model.jnt_range[env._joint_ids][:2], (2, 2))
                qref, targets = None, None
                for index in range(3000):
                    active = index-1000
                    if index == 1000:
                        qref, _ = native(observation)
                        for name in MODELS:
                            if not np.array_equal(qref, self.models[(seed, name)]["qref"]) or not np.array_equal(ranges, self.models[(seed, name)]["ranges"]):
                                raise ValueError("fresh_prefix_qref_or_ranges_not_exact_snapshot_match")
                        direction = np.where(ranges[:, 1]-qref >= qref-ranges[:, 0], 1., -1.)
                        targets = [qref+direction*distance for distance in (.04, .08)]
                        if any(np.any(target < ranges[:, 0]+.03) or np.any(target > ranges[:, 1]-.03) for target in targets):
                            raise ValueError("fixed_original_target_infeasible")
                        trial.update(qref2=qref.tolist(), public_ranges2=ranges.tolist(), targets2=safe(targets))
                    request = np.zeros(8)
                    if active >= 0:
                        q, v = native(observation)
                        with np.errstate(over="raise", invalid="raise"):
                            raw_pd = finite("raw_public_PD", 64.*(targets[0 if active < 1000 else 1]-q)-4.*v, (2,))
                        request[:2] = np.clip(raw_pd, -.5, .5)
                    original_data = env.data
                    if active in ORIGINS:
                        self.cost["pre_data_copy_attempts"] += 1
                        self.mj.mj_copyData(pre_data, env.model, original_data)
                        self.cost["pre_data_copy_returns"] += 1
                        before = self.state(env, f"s{seed}_o{active}_pre")
                    row = {"seed": seed, "control_index": index, "phase": "prefix" if active < 0 else "active",
                           "origin_active_index": active, "group": "source"}
                    after_observation = self.step(env, request, "source", row, qref)
                    if active in ORIGINS:
                        after = self.state(env, f"s{seed}_o{active}_base_endpoint")
                        self.forks(env, original_data, pre_data, fork_data, before, after, observation, after_observation,
                                   request[:2], seed, active, qref, ranges)
                    observation = after_observation
                trial["metadata_after"] = safe(env.frozen_metadata())
                if trial["metadata_after"] != metadata:
                    raise ValueError("source_environment_metadata_changed")
                trial["status"] = "completed"
        finally:
            core.mujoco, free.mujoco = old


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    model = (repo / MODEL_PATH).resolve()
    if output.exists() or output == repo or repo.is_relative_to(output) or model.is_relative_to(output):
        parser.error("existing_or_repository_or_model_containing_output_refused")
    output.mkdir(parents=True, exist_ok=False)
    collector, failure, status = Collector(repo, output), None, "failed"
    wall, cpu = time.perf_counter(), time.process_time()
    def payload_failure(exc, stage):
        nonlocal failure, status
        detail = {"stage": stage, "type": type(exc).__name__, "message": str(exc)}
        if failure is None:
            status = "failed"
            failure = {**detail, "context": collector.context, "traceback": traceback.format_exc()}
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
                collector.run_physics()
                for item in collector.models.values():
                    collector.cost["snapshot_fingerprint_checks"] += 1
                    if fingerprint(item["snapshot"]) != item["before"] or pin(item["theta"].tobytes()) != item["theta_bytes_before"]:
                        raise ValueError("frozen_model_fingerprint_changed")
                if collector.cost["source_control_returns"] != 9000 or len(collector.origins) != 12 or any(item["status"] == "not_attempted" for item in collector.sides):
                    raise ValueError("full_predeclared_population_not_completed")
                status = "completed"
            except BaseException as exc:
                status = "stopped" if isinstance(exc, StudyStop) else "failed"
                failure = {"type": type(exc).__name__, "message": str(exc), "context": collector.context,
                           "traceback": traceback.format_exc(), "unconfirmed_native_work": "unknown_if_native_exception",
                           "partial_write_failure": getattr(exc, "partial_write_failure", None),
                           "source_restore_failure": getattr(exc, "source_restore_failure", None)}
                traceback.print_exc()
            finally:
                for handle in collector.handles.values():
                    try:
                        handle.close()
                    except BaseException as exc:
                        payload_failure(exc, "stream_close")
    collector.cost["wall_seconds"], collector.cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    try:
        np.savez(output / "opaque_integration_states.npz", **collector.opaque)
    except BaseException as exc:
        payload_failure(exc, "opaque_npz_write")
    report = {"experiment_id": "PAR1", "status": status, "source": collector.source, "first_failure": failure,
        "runtime": {"python": sys.version, "python_version": platform.python_version(), "numpy": np.__version__,
                    "mujoco": getattr(collector, "runtime_mujoco", None), "platform": platform.platform(),
                    "cpu": platform.processor() or "unknown", "logical_cpu_count": os.cpu_count(), "GPU_used": False},
        "config": {"seeds": SEEDS, "origins_before_active_step": ORIGINS, "side_order": SIDES, "dose_nm": .125,
                   "prefix": 1000, "active": 2000, "dt_seconds": .002, "PD_Kp": 64., "PD_Kd": 4.,
                   "study_q_rad": .12, "study_v_rad_s": 1., "signal_tolerance": "128eps*max(1,sumabs(basev)+sumabs(sidev))"},
        "model_source": {"path": MODEL_PATH, "identity": collector.model_identity, "EF1B_commit": EF1B_SOURCE, "FR4A_commit": FR4A_SOURCE},
        "model_fingerprints": {f"{seed}_{name}": {"before": item["before"], "after": fingerprint(item["snapshot"]),
            "theta_bytes_before": item["theta_bytes_before"], "theta_bytes_after": pin(item["theta"].tobytes())} for (seed, name), item in collector.models.items()},
        "planned_upper_bounds": BOUNDS, "cost": dict(collector.cost), "source_trials": collector.source_trials,
        "origins": collector.origins, "complete_planned_side_population": collector.sides, "actual_effort_separate": collector.effort,
        "streams": {name: {"path": name+".jsonl.gz", "format": "gzip_jsonl", "identity_scope": "decoded_jsonl",
            "records": item["records"], "bytes": item["bytes"], "sha256": item["hash"].hexdigest()} for name, item in collector.streams.items()},
        "opaque_states_use": "diagnostic_matching_only_not_PD_or_model_inputs", "partial_subset_ranking": False,
        "physics_internal_forward_work": "unmeasured_unknown_not_zero", "unmeasured_filesystem_and_import_IO": "unknown_not_zero",
        "timing_excludes": "opaque_npz_and_final_JSON_encoding_and_payload_writes", "fit_calls": 0, "RLS_updates": 0,
        "model_predict_calls": 0, "SVD_calls": 0, "inverse_solves": 0, "old_math_recomputations": 0,
        "control_candidate_opened": False, "completed_utc": datetime.now(timezone.utc).isoformat(), **FLAGS}
    try:
        (output / "run.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    except BaseException as exc:
        payload_failure(exc, "run_JSON_write")
    print(json.dumps({"experiment_id": "PAR1", "status": status, "output": str(output), "cost": dict(collector.cost), "failure": failure}))
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
