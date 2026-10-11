"""Audit the frozen nine-PD development grid with the standard library.

Recomputes logged arithmetic and provenance without importing the simulator,
controller implementation, NumPy, or learning code. Selection follows the
frozen protocol's REQUESTED squared effort tie-break, not actual effort.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GAINS = [(kp, kd) for kp in (4., 16., 64.) for kd in (0., .2, 1.)]
SEEDS = [0, 1, 2]
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
          "left_hip", "left_knee", "right_hip", "right_knee")
NATIVE = {"joint_position": 8, "joint_velocity": 8, "imu_gyro": 3,
          "imu_acceleration": 3, "actuator_torque": 8, "previous_command": 8}
ENVIRONMENT = {"physics_dt": .002, "control_substeps": 10, "torque_limit": .5,
               "joint_speed_limit": 20., "joint_limit_margin": .08,
               "kinetic_energy_limit": 50., "reset_clearance": .005,
               "ground_contact_profile": "baseline"}
ASSET = "src/developmental_physics/assets/ground_body.xml"
PROTOCOL = "docs/CLASSICAL_PD_DEVELOPMENT_PROTOCOL.md"
REQUIRED_SOURCES = {ASSET, PROTOCOL, "pyproject.toml"} | {
    "src/developmental_physics/" + name for name in
    ("__init__.py", "environment.py", "collect.py", "probes.py", "feedback_validate.py")}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Checks:
    def __init__(self):
        self.count = self.failed = 0
        self.maximum_difference = 0.
        self.violations = []

    def check(self, condition, label, location=None):
        self.count += 1
        if not condition:
            self.failed += 1
            if len(self.violations) < 200:
                self.violations.append({"check": label, "location": location})

    def near(self, actual, expected, label, location=None):
        valid = type(actual) in (int, float) and type(expected) in (int, float)
        valid = valid and math.isfinite(actual) and math.isfinite(expected)
        difference = abs(actual - expected) if valid else None
        if valid:
            self.maximum_difference = max(self.maximum_difference, difference)
        self.check(valid and difference <= 1e-10, label,
                   {"location": location, "actual": actual, "expected": expected,
                    "difference": difference})


def finite_tree(value):
    if isinstance(value, dict):
        if value.get("invalid_numeric_fields"):
            raise ValueError("archive contains invalid numeric markers")
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite numeric value")


def vector(value, width):
    if not isinstance(value, list) or len(value) != width or any(
        type(item) not in (int, float) or not math.isfinite(item) for item in value
    ):
        raise ValueError(f"expected {width} finite numeric measurements")
    return value


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError("expected nonnegative integer count")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def rmse(values):
    return math.sqrt(math.fsum(x*x for x in values) / len(values)) if values else None


def audit_sources(path, metadata, checks, git_root):
    manifest = load_json(path / "manifest.json")
    checks.check(set(manifest) == {p.name for p in path.iterdir()
                                   if p.is_file() and p.name != "manifest.json"},
                 "manifest_exact_file_coverage")
    checks.check({"metadata.json", "episodes.json", "trace.jsonl.gz", "source_snapshot.zip"}
                 .issubset(manifest), "manifest_core_files")
    for name, expected in manifest.items():
        local = Path(name).name == name and name not in (".", "..")
        checks.check(local, "manifest_local_filename", name)
        if local:
            checks.check((path/name).is_file() and file_hash(path/name) == expected,
                         "manifest_hash", name)
    hashes = metadata["source_sha256"]
    checks.check(REQUIRED_SOURCES.issubset(hashes), "required_source_files")
    protocol = metadata.get("protocol", {})
    checks.check(protocol.get("path") == PROTOCOL and
                 protocol.get("sha256") == hashes.get(PROTOCOL), "frozen_protocol_hash")
    commit = metadata.get("source_commit", "")
    valid_commit = isinstance(commit, str) and bool(re.fullmatch(r"[0-9a-f]{40}", commit))
    checks.check(valid_commit, "source_commit_format")
    checks.check(metadata.get("source_status") == "" and metadata.get("source_dirty") is False,
                 "clean_collection_source")
    with zipfile.ZipFile(path / "source_snapshot.zip") as archive:
        names = archive.namelist()
        checks.check(len(names) == len(set(names)) and set(names) == set(hashes),
                     "source_zip_exact_unique_coverage")
        for name, expected in hashes.items():
            blob = archive.read(name)
            checks.check(hashlib.sha256(blob).hexdigest() == expected, "source_zip_hash", name)
            if git_root is not None and valid_commit:
                result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=git_root,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                checks.check(result.returncode == 0 and result.stdout == blob,
                             "source_git_blob_bytes", name)
        xml = ET.fromstring(archive.read(ASSET))
    compiler = xml.find("compiler")
    factor = math.pi/180. if compiler is not None and compiler.get("angle", "degree") == "degree" else 1.
    ranges = {j.get("name"): [float(x)*factor for x in j.get("range").split()]
              for j in xml.findall(".//joint") if j.get("range")}
    return [vector(ranges[name], 2) for name in JOINTS]


def _new_state(episode):
    return {"episode": episode, "rows": 0, "exception_rows": 0, "physics": 0,
            "phase_rows": {"prefix": 0, "control": 0},
            "phase_physics": {"prefix": 0, "control": 0}, "invalid": False,
            "exception_commands": [],
            "previous_after": None, "prefix": hashlib.sha256(), "anchor": hashlib.sha256(),
            "prefix_rows": 0, "qref": None, "direction": None, "tracking": [],
            "requested_square": 0., "saturated": 0, "max_speed": 0., "peak_force": 0.,
            "actual_absolute": 0., "actual_square": 0.}


def _anchor_payload(row, target_field):
    return {"phase": row["phase"], "observation_before": row["observation_before"],
            "observation_after": row["observation_after"], "requested_torque": row["requested_torque"],
            "target": row[target_field], "qpos": row["qpos"], "qvel": row["qvel"]}


def _consume(state, row, checks, ranges):
    ep = state["episode"]
    location = ep["trial_id"] + "/" + str(state["rows"])
    if "collector_exception" in row:
        state["exception_rows"] += 1
        state["exception_commands"].append({"phase": row.get("phase"),
                                             "requested_torque": row.get("requested_torque")})
        state["invalid"] = True
        checks.check(ep["status"] == "exception", "exception_outcome_matches_row", location)
        return
    index = state["rows"]
    state["rows"] += 1
    start_failed = checks.failed
    try:
        finite_tree(row)
        phase = "prefix" if index < 100 else "control"
        checks.check(index < 300 and row["control_index"] == index, "fixed_control_index", location)
        checks.check(row["phase"] == phase, "fixed_phase", location)
        for key in ("seed", "candidate", "kp", "kd"):
            checks.check(row[key] == ep[key], "row_trial_identity", location + "/" + key)
        before, after = row["observation_before"], row["observation_after"]
        for key, width in NATIVE.items():
            vector(before[key], width)
            vector(after[key], width)
        vector(row["qpos"], 15)
        vector(row["qvel"], 14)
        checks.check(state["previous_after"] is None or before == state["previous_after"],
                     "exact_native_chain", location)
        state["previous_after"] = after
        q, v = before["joint_position"][0], before["joint_velocity"][0]
        if index == 100:
            state["qref"] = q
            lower, upper = ranges[0]
            state["direction"] = 1 if upper-q >= q-lower else -1
            checks.near(ep["prefix_end_q_rad"], q, "paid_prefix_reference", location)
            selection = ep["selection_record"]
            expected_selection = {"joint_index": 0, "joint_position_rad": q,
                                  "lower_limit_rad": lower, "upper_limit_rad": upper,
                                  "positive_room_rad": upper-q, "negative_room_rad": q-lower,
                                  "direction": state["direction"],
                                  "rule": "larger distance to the public joint limit; ties choose positive"}
            checks.check(selection == expected_selection, "public_limit_direction", location)
        request = vector(row["requested_torque"], 8)
        target = None if phase == "prefix" else state["qref"] + state["direction"] * (.04 if index < 200 else .08)
        expected = [0.]*8
        if target is None:
            checks.check(row["raw_pd_torque_nm"] is None and row["target_q_rad"] is None,
                         "prefix_has_no_control_target", location)
        else:
            raw = ep["kp"]*(target-q)-ep["kd"]*v
            checks.near(row["raw_pd_torque_nm"], raw, "independent_raw_pd", location)
            checks.near(row["target_q_rad"], target, "fixed_task_target", location)
            checks.check(ranges[0][0]+.03 <= target <= ranges[0][1]-.03,
                         "target_public_interior", location)
            expected[0] = max(-.5, min(.5, raw))
            state["tracking"].append(after["joint_position"][0]-target)
            state["saturated"] += int(abs(request[0]) == .5)
            state["max_speed"] = max(state["max_speed"], max(abs(x) for x in after["joint_velocity"]))
        checks.check(request == expected, "independent_requested_pd_vector", location)
        diagnostic = row["diagnostics"]
        checks.check(diagnostic["requested_torque"] == request and diagnostic["accepted_torque"] == request,
                     "common_permission_and_logged_request", location)
        n = count(diagnostic["executed_substeps"])
        checks.check(n <= 10 and (n == 10 or diagnostic["terminated"]), "executed_substep_count", location)
        state["physics"] += n
        state["phase_rows"][phase] += 1
        state["phase_physics"][phase] += n
        checks.near(diagnostic["time"], state["physics"]*.002, "executed_physics_time", location)
        history = diagnostic["applied_torque_history"]
        checks.check(len(history) == n, "actual_history_length", location)
        for values in history:
            vector(values, 8)
            checks.check(all(x in (0., request[j]) for j, x in enumerate(values)),
                         "actual_requested_or_shielded", location)
        forces = vector(diagnostic["substep_ground_normal_forces"], n)
        energies = vector(diagnostic["substep_kinetic_energies"], n)
        distances = vector(diagnostic["substep_minimum_contact_distances"], n)
        checks.check(all(x >= 0 for x in forces+energies), "nonnegative_force_energy", location)
        checks.near(diagnostic["peak_substep_ground_normal_force"], max(forces, default=0.), "force_summary", location)
        checks.near(diagnostic["ground_normal_impulse_ns"], math.fsum(forces)*.002, "force_impulse_summary", location)
        checks.near(diagnostic["peak_substep_kinetic_energy"], max(energies, default=0.), "energy_summary", location)
        checks.near(diagnostic["minimum_substep_contact_distance"], min(distances, default=0.), "distance_summary", location)
        state["peak_force"] = max(state["peak_force"], max(forces, default=0.))
        if phase == "control":
            state["requested_square"] += request[0]**2*n*.002
            state["actual_absolute"] += math.fsum(abs(values[0]) for values in history)*.002
            state["actual_square"] += math.fsum(values[0]**2 for values in history)*.002
        checks.check(not diagnostic["terminated"] or ep["status"] == "terminated",
                     "terminated_outcome_matches_row", location)
        if phase == "prefix":
            state["prefix"].update(canonical({key: row[key] for key in
                ("observation_before", "observation_after", "diagnostics", "qpos", "qvel")}))
            state["prefix"].update(b"\n")
            state["prefix_rows"] += 1
        state["anchor"].update(canonical(_anchor_payload(row, "target_q_rad")))
        state["anchor"].update(b"\n")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        checks.check(False, "row_schema_or_arithmetic", {"location": location, "error": str(error)})
    state["invalid"] |= checks.failed != start_failed


def select_candidates(trials, seeds=SEEDS):
    """No truncation, per-seed gain changes, approximate ties, or actual-effort substitution."""
    candidates = []
    for i, (kp, kd) in enumerate(GAINS):
        rows = [trial for trial in trials if trial["candidate"] == i]
        eligible = len(rows) == len(seeds) and {r["seed"] for r in rows} == set(seeds)
        eligible = eligible and all(r["eligible"] for r in rows)
        mean = math.fsum(r["tracking_rmse_rad"] for r in rows)/len(rows) if eligible else None
        effort = math.fsum(r["requested_squared_effort_nm2s"] for r in rows)/len(rows) if eligible else None
        candidates.append({"candidate": i, "kp": kp, "kd": kd, "eligible": eligible,
                           "mean_tracking_rmse_rad": mean, "mean_requested_squared_effort_nm2s": effort,
                           "trial_ids": [r["trial_id"] for r in rows]})
    available = [c for c in candidates if c["eligible"]]
    selected = min(available, key=lambda c: (c["mean_tracking_rmse_rad"],
                    c["mean_requested_squared_effort_nm2s"], c["kp"], c["kd"], c["candidate"])) if available else None
    return {"rule": "complete three-seed mean raw RMSE, exact ties by mean requested squared effort, Kp, Kd, candidate",
            "candidates": candidates, "selected": selected, "selection_success": selected is not None}


def _reference(path, states, metadata, checks):
    if path is None:
        return {"provided": False, "exact_replay_verified": False}
    path = Path(path).resolve()
    failures_before = checks.failed
    reference_meta = load_json(path/"metadata.json")
    checks.check(reference_meta.get("pose") == "supine" and reference_meta.get("joint_index") == 0
                 and reference_meta.get("seeds") == SEEDS and reference_meta.get("split") == "development",
                 "historical_anchor_same_conditions")
    checks.check(reference_meta.get("environment_config") == metadata["environment_config"],
                 "historical_anchor_environment_config")
    historical = {seed: {"hash": hashlib.sha256(), "rows": 0} for seed in SEEDS}
    with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("kind") != "fixed_pd":
                continue
            seed = row.get("seed")
            if seed not in historical or "collector_exception" in row:
                checks.check(False, "historical_anchor_invalid_seed_or_exception")
                continue
            finite_tree(row)
            checks.check(row["step_index"] == historical[seed]["rows"], "historical_anchor_indices", seed)
            historical[seed]["hash"].update(canonical(_anchor_payload(row, "target_q")))
            historical[seed]["hash"].update(b"\n")
            historical[seed]["rows"] += 1
    pairs = []
    for seed in SEEDS:
        state = states.get(f"seed{seed}_candidate1")
        exact = (state is not None and historical[seed]["rows"] == state["rows"] == 300
                 and historical[seed]["hash"].hexdigest() == state["anchor"].hexdigest())
        checks.check(exact, "historical_fixed_pd_exact_native_state_command_target_replay", seed)
        pairs.append({"seed": seed, "historical_rows": historical[seed]["rows"],
                      "historical_trajectory_sha256": historical[seed]["hash"].hexdigest(),
                      "exact_replay": exact})
    return {"provided": True, "path": str(path), "source_commit": reference_meta.get("source_commit"),
            "input_hashes": {name: file_hash(path/name) for name in ("metadata.json", "trace.jsonl.gz")},
            "per_seed": pairs, "exact_replay_verified": checks.failed == failures_before and all(p["exact_replay"] for p in pairs),
            "comparison_fields": ["native before/after", "requested torque", "phase", "current target", "qpos", "qvel"],
            "extra_independent_samples": 0}


def audit(archive, *, reference=None, git_root=ROOT):
    path = Path(archive).resolve()
    checks = Checks()
    result = {"path": str(path), "trials": [], "selection": {"selection_success": False, "selected": None}}
    try:
        metadata, episodes = load_json(path/"metadata.json"), load_json(path/"episodes.json")
        finite_tree(metadata)
        ranges = audit_sources(path, metadata, checks, git_root)
        checks.check(metadata.get("environment_config") == ENVIRONMENT, "frozen_environment")
        checks.check(metadata.get("gains") == [list(g) for g in GAINS], "frozen_gain_grid_order")
        checks.check(metadata.get("seeds") == SEEDS and metadata.get("split") == "development", "frozen_development_seeds")
        checks.check(metadata.get("pose") == "supine" and metadata.get("joint_index") == 0, "frozen_local_condition")
        checks.check(metadata.get("prefix_steps") == 100 and metadata.get("control_steps_per_trial") == 200
                     and metadata.get("target_offsets_rad") == [.04, .08], "frozen_time_target_schedule")
        checks.check(metadata.get("parameter_updates") == {"body_model": 0, "policy": 0}
                     and metadata.get("teacher_calls") == 0 and metadata.get("external_demonstration_samples") == 0
                     and metadata.get("gpu") is None, "no_learning_teacher_or_gpu")
        planned = [{"trial_id": f"seed{s}_candidate{i}", "seed": s, "candidate": i,
                    "kp": kp, "kd": kd, "maximum_control_steps": 300}
                   for s in SEEDS for i, (kp, kd) in enumerate(GAINS)]
        checks.check(metadata.get("planned_episodes") == planned and metadata.get("maximum_control_steps") == 8100,
                     "complete_planned_grid")
        ids = [ep["trial_id"] for ep in episodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate episode IDs")
        checks.check(ids == [p["trial_id"] for p in planned], "all_planned_outcomes_in_order")
        by_id = {ep["trial_id"]: ep for ep in episodes}
        states = {tid: _new_state(ep) for tid, ep in by_id.items()}
        with gzip.open(path/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                checks.check(row.get("trial_id") in states, "known_trace_trial_id", row.get("trial_id"))
                if row.get("trial_id") in states:
                    _consume(states[row["trial_id"]], row, checks, ranges)
        for plan in planned:
            state = states.get(plan["trial_id"])
            if state is None:
                result["trials"].append({**plan, "eligible": False, "status": "missing",
                                         "tracking_rmse_rad": None, "requested_squared_effort_nm2s": None})
                continue
            ep = state["episode"]
            start_failed = checks.failed
            finite_tree(ep)
            checks.check(all(ep.get(k) == v for k, v in plan.items()), "episode_matches_plan", plan["trial_id"])
            checks.check(ep.get("status") in ("completed", "terminated", "exception", "blocked"), "recorded_outcome", plan["trial_id"])
            budget = ep["phase_budgets"]
            for phase in ("prefix", "control"):
                counts = budget[phase]
                for key in ("control_calls_attempted", "control_steps", "physics_steps"):
                    count(counts[key])
                checks.check(counts["control_calls_attempted"] >= counts["control_steps"] >= state["phase_rows"][phase]
                             and counts["physics_steps"] >= state["phase_physics"][phase]
                             and counts["physics_steps"] <= counts["control_calls_attempted"]*10
                             and counts["control_calls_attempted"] <= (100 if phase == "prefix" else 200),
                             "paid_phase_budget_including_unstored_fault_steps", plan["trial_id"]+"/"+phase)
                if ep.get("complete"):
                    checks.check(counts == {"control_calls_attempted": 100 if phase == "prefix" else 200,
                        "control_steps": 100 if phase == "prefix" else 200,
                        "physics_steps": 1000 if phase == "prefix" else 2000}, "complete_phase_budget", plan["trial_id"]+"/"+phase)
            for key in ("control_calls_attempted", "control_steps", "physics_steps"):
                checks.check(ep[key] == sum(budget[p][key] for p in ("prefix", "control")), "episode_budget_sum", plan["trial_id"]+"/"+key)
            # step() or serialization can fail after physical substeps but
            # before a normal row is saved. The exception retains the known
            # request; paid ledger exposure allows requested effort recovery,
            # never inference of missing actual torque or sensory samples.
            missing_control_physics = budget["control"]["physics_steps"]-state["phase_physics"]["control"]
            recovered_requested_square = 0.
            if missing_control_physics > 0:
                commands = [r for r in state["exception_commands"] if r["phase"] == "control"]
                recoverable = len(commands) == 1 and missing_control_physics <= 10
                checks.check(recoverable, "unstored_paid_effort_has_unique_exception_command", plan["trial_id"])
                if recoverable:
                    request = vector(commands[0]["requested_torque"], 8)
                    checks.check(abs(request[0]) <= .5 and request[1:] == [0.]*7,
                                 "exception_command_obeys_common_permission", plan["trial_id"])
                    recovered_requested_square = request[0]**2*missing_control_physics*.002
            requested_square = state["requested_square"] + recovered_requested_square
            tracking = rmse(state["tracking"])
            if tracking is None:
                checks.check(ep.get("tracking_rmse_rad") is None, "empty_tracking_metric", plan["trial_id"])
            else:
                checks.near(ep.get("tracking_rmse_rad"), tracking, "independent_tracking_rmse", plan["trial_id"])
            checks.check(ep.get("metric_control_step_count") == len(state["tracking"]), "metric_transition_count", plan["trial_id"])
            checks.near(ep.get("requested_squared_effort_nm2s"), requested_square, "independent_requested_squared_effort", plan["trial_id"])
            checks.check(ep.get("saturated_control_steps") == state["saturated"], "independent_saturation_count", plan["trial_id"])
            checks.near(ep.get("max_native_control_speed_rad_s"), state["max_speed"], "independent_max_native_control_speed", plan["trial_id"])
            checks.near(ep.get("peak_full_ground_force_n"), state["peak_force"], "independent_full_force_peak", plan["trial_id"])
            telemetry_complete = ep.get("collector_exception") is None and state["physics"] == ep["physics_steps"]
            expected_scope = ("all paid substeps" if telemetry_complete else
                              "available returned-step telemetry only; incomplete, lower bound")
            if ep["status"] != "blocked":
                checks.check(ep.get("observed_diagnostic_substeps") == state["physics"],
                             "observed_diagnostic_substeps_match_stored_trace", plan["trial_id"])
                checks.check(ep.get("telemetry_complete_for_paid_substeps") == telemetry_complete
                             and ep.get("force_peak_scope") == expected_scope,
                             "force_risk_scope_includes_unstored_fault_exposure", plan["trial_id"])
            completed = (ep.get("status") == "completed" and ep.get("complete") is True
                         and ep.get("collector_exception") is None and ep.get("reason") is None)
            checks.check(ep.get("status") != "completed" or completed,
                         "completed_outcome_has_no_error", plan["trial_id"])
            eligible = (completed and not state["invalid"] and checks.failed == start_failed
                        and state["rows"] == 300 and len(state["tracking"]) == 200
                        and state["physics"] == 3000 and state["exception_rows"] == 0)
            checks.check(not completed or eligible, "claimed_completion_has_complete_valid_trace", plan["trial_id"])
            result["trials"].append({**plan, "status": ep["status"], "eligible": eligible,
                "tracking_rmse_rad": tracking, "requested_squared_effort_nm2s": requested_square,
                "requested_squared_effort_from_unstored_paid_substeps_nm2s": recovered_requested_square,
                "actual_absolute_effort_nms": state["actual_absolute"], "actual_squared_effort_nm2s": state["actual_square"],
                "actual_effort_telemetry_complete": state["physics"] == ep["physics_steps"],
                "ground_force_peak_n": state["peak_force"], "ground_force_peak_scope": expected_scope,
                "risk_telemetry_complete_for_paid_substeps": telemetry_complete,
                "saturated_control_steps": state["saturated"], "prefix_rows": state["prefix_rows"],
                "prefix_sha256": state["prefix"].hexdigest(), "trace_rows": state["rows"],
                "observed_physics_steps": state["physics"],
                "paid_budget": {k: ep[k] for k in ("control_calls_attempted", "control_steps", "physics_steps")}})
        for seed in SEEDS:
            trials = [t for t in result["trials"] if t["seed"] == seed and t.get("prefix_rows") == 100]
            same = len({t["prefix_sha256"] for t in trials}) <= 1
            checks.check(same, "exact_native_physical_prefix_across_candidates", seed)
            if not same:
                for trial in trials:
                    trial["eligible"] = False
        for key in ("control_calls_attempted", "control_steps", "physics_steps"):
            checks.check(metadata.get(key) == sum(ep[key] for ep in episodes), "metadata_budget_sum", key)
        for status in ("completed", "terminated", "exception", "blocked"):
            checks.check(metadata.get(status+"_trials") == sum(ep["status"] == status for ep in episodes), "metadata_outcome_count", status)
        checks.check(metadata.get("all_trials_successful") == all(ep["status"] == "completed" for ep in episodes), "metadata_success_summary")
        checks.check(metadata.get("complete") == (metadata.get("archive_status") == "complete"), "archive_completion_definition")
        result["reference"] = _reference(reference, states, metadata, checks)
        result["selection"] = select_candidates(result["trials"])
        result["source_commit"] = metadata.get("source_commit")
        result["source_git_blob_verification_performed"] = git_root is not None
        result["budget"] = {k: metadata[k] for k in ("control_calls_attempted", "control_steps", "physics_steps")}
        result["input_hashes"] = {name: file_hash(path/name) for name in
            ("manifest.json", "metadata.json", "episodes.json", "trace.jsonl.gz", "source_snapshot.zip")}
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, OverflowError, zipfile.BadZipFile) as error:
        checks.check(False, "archive_schema_or_read_error", {"type": type(error).__name__, "message": str(error)})
    selection = result["selection"]
    selection["validated_selection"] = selection["selection_success"] and checks.failed == 0 and git_root is not None
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "Independent frozen nine-PD development audit; no physical interaction or model updates.",
            "audit_script_sha256": file_hash(Path(__file__)), "checks": checks.count, "failed": checks.failed,
            "maximum_recomputation_difference": checks.maximum_difference, "violations": checks.violations,
            "analysis_runtime": {"python": sys.version, "platform": platform.platform(), "third_party_dependencies": []},
            "archive": result, "claim_boundary": "Development-grid controller selection, no unseen method advantage, skill or safety claim."}


def validate_output_path(output, inputs):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing audit output.")
    if any(output.is_relative_to(Path(path).resolve()) for path in inputs if path is not None):
        raise ValueError("Audit output must be outside every input archive and reference.")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = validate_output_path(args.output, [args.archive, args.reference])
    except ValueError as error:
        parser.error(str(error))
    report = audit(args.archive, reference=args.reference)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"checks": report["checks"], "failed": report["failed"],
                      "selected": report["archive"]["selection"].get("selected"), "report": str(output)}))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
