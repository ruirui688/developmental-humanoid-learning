"""Synthetic archives only: independent arithmetic, failures, provenance and selection."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("feedback_development_audit", ROOT / "scripts/audit_feedback_development.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def _observation(command=0.):
    return {"joint_position": [0.]*8, "joint_velocity": [0.]*8,
            "imu_gyro": [0.]*3, "imu_acceleration": [0., 0., 9.81],
            "actuator_torque": [command]+[0.]*7, "previous_command": [command]+[0.]*7}


def _rehash(folder):
    manifest = {p.name: AUDIT.file_hash(p) for p in folder.iterdir()
                if p.is_file() and p.name != "manifest.json"}
    (folder/"manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _write(folder, metadata, episodes, rows, sources):
    folder.mkdir()
    for name, data in (("metadata.json", metadata), ("episodes.json", episodes)):
        (folder/name).write_text(json.dumps(data), encoding="utf-8")
    with gzip.open(folder/"trace.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row)+"\n")
    with zipfile.ZipFile(folder/"source_snapshot.zip", "w") as archive:
        for name, blob in sources.items():
            archive.writestr(name, blob)
    _rehash(folder)


@pytest.fixture(scope="module")
def records(tmp_path_factory):
    git_root = tmp_path_factory.mktemp("feedback_git")
    xml = '<mujoco><compiler angle="radian"/><worldbody><body>' + ''.join(
        f'<joint name="{name}" range="-1 2"/>' for name in AUDIT.JOINTS) + '</body></worldbody></mujoco>'
    sources = {name: (xml.encode() if name == AUDIT.ASSET else b"Synthetic provenance fixture\n")
               for name in AUDIT.REQUIRED_SOURCES}
    for name, blob in sources.items():
        path = git_root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    for command in (["git", "init"], ["git", "config", "core.autocrlf", "false"],
                    ["git", "add", "."], ["git", "-c", "user.name=Audit Test", "-c",
                    "user.email=audit@example.invalid", "commit", "-m", "Synthetic source"]):
        subprocess.run(command, cwd=git_root, check=True, capture_output=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_root, text=True).strip()
    episodes, rows, planned = [], [], []
    for seed in AUDIT.SEEDS:
        for candidate, (kp, kd) in enumerate(AUDIT.GAINS):
            plan = {"trial_id": f"seed{seed}_candidate{candidate}", "seed": seed,
                    "candidate": candidate, "kp": kp, "kd": kd, "maximum_control_steps": 300}
            planned.append(plan)
            before = _observation()
            effort, errors, saturated = 0., [], 0
            for index in range(300):
                phase = "prefix" if index < 100 else "control"
                target = None if index < 100 else (.04 if index < 200 else .08)
                raw = None if target is None else kp*target
                command = 0. if target is None else max(-.5, min(.5, raw))
                request = [command]+[0.]*7
                after = _observation(command)
                if target is not None:
                    errors.append(-target)
                    effort += command**2*.02
                    saturated += int(abs(command) == .5)
                diagnostic = {"requested_torque": request, "accepted_torque": request,
                    "applied_torque_history": [request]*10, "executed_substeps": 10,
                    "substep_ground_normal_forces": [1.]*10,
                    "substep_kinetic_energies": [.1]*10,
                    "substep_minimum_contact_distances": [-.001]*10,
                    "peak_substep_ground_normal_force": 1., "ground_normal_impulse_ns": .02,
                    "peak_substep_kinetic_energy": .1, "minimum_substep_contact_distance": -.001,
                    "time": (index+1)*.02, "terminated": False}
                rows.append({"trial_id": plan["trial_id"], "seed": seed, "candidate": candidate,
                    "kp": kp, "kd": kd, "control_index": index, "phase": phase,
                    "requested_torque": request, "raw_pd_torque_nm": raw, "target_q_rad": target,
                    "observation_before": before, "observation_after": after, "diagnostics": diagnostic,
                    "qpos": [0.]*15, "qvel": [0.]*14, "invalid_numeric_fields": []})
                before = after
            episodes.append({**plan, "status": "completed", "reason": None, "collector_exception": None,
                "complete": True, "control_calls_attempted": 300, "control_steps": 300, "physics_steps": 3000,
                "phase_budgets": {"prefix": {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000},
                                  "control": {"control_calls_attempted": 200, "control_steps": 200, "physics_steps": 2000}},
                "prefix_end_q_rad": 0., "selection_record": {
                    "joint_index": 0, "joint_position_rad": 0., "lower_limit_rad": -1., "upper_limit_rad": 2.,
                    "positive_room_rad": 2., "negative_room_rad": 1., "direction": 1,
                    "rule": "larger distance to the public joint limit; ties choose positive"},
                "metric_control_step_count": 200, "tracking_rmse_rad": AUDIT.rmse(errors),
                "requested_squared_effort_nm2s": effort, "saturated_control_steps": saturated,
                "max_native_control_speed_rad_s": 0., "peak_full_ground_force_n": 1.,
                "observed_diagnostic_substeps": 3000, "telemetry_complete_for_paid_substeps": True,
                "force_peak_scope": "all paid substeps"})
    metadata = {"environment_config": deepcopy(AUDIT.ENVIRONMENT),
        "gains": [list(g) for g in AUDIT.GAINS], "seeds": AUDIT.SEEDS, "split": "development",
        "pose": "supine", "joint_index": 0, "prefix_steps": 100, "control_steps_per_trial": 200,
        "target_offsets_rad": [.04, .08], "parameter_updates": {"body_model": 0, "policy": 0},
        "teacher_calls": 0, "external_demonstration_samples": 0, "gpu": None,
        "planned_episodes": planned, "maximum_control_steps": 8100,
        "source_commit": commit, "source_status": "", "source_dirty": False,
        "source_sha256": {name: hashlib.sha256(blob).hexdigest() for name, blob in sources.items()},
        "protocol": {"path": AUDIT.PROTOCOL, "sha256": hashlib.sha256(sources[AUDIT.PROTOCOL]).hexdigest()},
        "complete": True, "archive_status": "complete", "all_trials_successful": True,
        "control_calls_attempted": 8100, "control_steps": 8100, "physics_steps": 81000,
        "completed_trials": 27, "exception_trials": 0, "terminated_trials": 0, "blocked_trials": 0}
    return metadata, episodes, rows, sources, git_root


def test_complete_grid_independently_selects_and_matches_historical_anchor(records, tmp_path):
    metadata, episodes, rows, sources, git_root = records
    folder = tmp_path/"grid"
    _write(folder, metadata, episodes, rows, sources)
    reference = tmp_path/"reference"
    reference.mkdir()
    (reference/"metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    with gzip.open(reference/"trace.jsonl.gz", "wt", encoding="utf-8") as stream:
        for source in rows:
            if source["candidate"] == 1:
                row = deepcopy(source)
                row["kind"] = "fixed_pd"
                row["step_index"] = row.pop("control_index")
                row["target_q"] = row.pop("target_q_rad")
                stream.write(json.dumps(row)+"\n")
    report = AUDIT.audit(folder, reference=reference, git_root=git_root)
    assert report["failed"] == 0, report["violations"]
    assert report["archive"]["reference"]["exact_replay_verified"]
    assert report["archive"]["selection"]["validated_selection"]
    assert report["archive"]["selection"]["selected"]["candidate"] == 0
    trial = report["archive"]["trials"][0]
    assert trial["tracking_rmse_rad"] == pytest.approx(math.sqrt((.04**2+.08**2)/2))
    assert trial["requested_squared_effort_nm2s"] == pytest.approx((.16**2+.32**2)*2)
    assert trial["actual_squared_effort_nm2s"] == pytest.approx(trial["requested_squared_effort_nm2s"])
    assert trial["actual_absolute_effort_nms"] == pytest.approx((.16+.32)*2)
    assert report["archive"]["budget"]["physics_steps"] == 81000
    assert report["analysis_runtime"]["third_party_dependencies"] == []


@pytest.mark.parametrize("mutation,label", [
    ("request", "independent_requested_pd_vector"), ("target", "fixed_task_target"),
    ("metric", "independent_tracking_rmse"), ("budget", "episode_budget_sum"),
    ("prefix", "exact_native_physical_prefix_across_candidates"),
    ("source", "source_git_blob_bytes"), ("manifest", "manifest_hash"),
    ("invalid", "row_schema_or_arithmetic")])
def test_tampered_records_fail_audit_and_never_validate_selection(records, tmp_path, mutation, label):
    original_meta, original_episodes, original_rows, original_sources, git_root = records
    metadata, episodes, rows, sources = deepcopy((original_meta, original_episodes, original_rows, original_sources))
    if mutation == "request":
        rows[100]["requested_torque"][0] = .1
    elif mutation == "target":
        rows[100]["target_q_rad"] = .05
    elif mutation == "metric":
        episodes[0]["tracking_rmse_rad"] = 0.
    elif mutation == "budget":
        episodes[0]["physics_steps"] += 1
        metadata["physics_steps"] += 1
    elif mutation == "prefix":
        for row in rows[:100]:
            row["qpos"][0] = .01
    elif mutation == "source":
        sources["pyproject.toml"] += b"changed bytes\r\n"
        metadata["source_sha256"]["pyproject.toml"] = hashlib.sha256(sources["pyproject.toml"]).hexdigest()
    elif mutation == "invalid":
        rows[100]["invalid_numeric_fields"] = [{"path": "/joint_position/0", "value": "nan"}]
    folder = tmp_path/"grid"
    _write(folder, metadata, episodes, rows, sources)
    if mutation == "manifest":
        (folder/"metadata.json").write_text(json.dumps(metadata)+"\n", encoding="utf-8")
    report = AUDIT.audit(folder, git_root=git_root)
    assert report["failed"] > 0
    assert any(v["check"] == label for v in report["violations"]), report["violations"]
    assert not report["archive"]["selection"]["validated_selection"]


def test_missing_trial_remains_missing_and_disqualifies_candidate(records, tmp_path):
    metadata, episodes, rows, sources, git_root = records
    episodes = deepcopy(episodes[1:])
    rows = [r for r in rows if r["trial_id"] != "seed0_candidate0"]
    folder = tmp_path/"missing"
    _write(folder, metadata, episodes, rows, sources)
    report = AUDIT.audit(folder, git_root=git_root)
    missing = report["archive"]["trials"][0]
    assert missing["status"] == "missing" and not missing["eligible"]
    assert not report["archive"]["selection"]["candidates"][0]["eligible"]
    assert not report["archive"]["selection"]["validated_selection"]


def test_partial_exception_preserves_unstored_physics_budget_and_is_excluded(records, tmp_path):
    metadata, episodes, rows, sources, git_root = deepcopy(records)
    ep = episodes[0]
    ep.update(status="exception", complete=False, collector_exception={"type": "RuntimeError", "message": "fault"},
              control_calls_attempted=2, control_steps=1, physics_steps=13, metric_control_step_count=0,
              tracking_rmse_rad=None, requested_squared_effort_nm2s=0., saturated_control_steps=0,
              observed_diagnostic_substeps=10, telemetry_complete_for_paid_substeps=False,
              force_peak_scope="available returned-step telemetry only; incomplete, lower bound")
    ep["phase_budgets"] = {"prefix": {"control_calls_attempted": 2, "control_steps": 1, "physics_steps": 13},
                            "control": {"control_calls_attempted": 0, "control_steps": 0, "physics_steps": 0}}
    keep = [rows[0], {"trial_id": ep["trial_id"], "collector_exception": ep["collector_exception"]}]
    rows = keep + [r for r in rows if r["trial_id"] != ep["trial_id"]]
    metadata.update(control_calls_attempted=7802, control_steps=7801, physics_steps=78013,
                    all_trials_successful=False, completed_trials=26, exception_trials=1)
    folder = tmp_path/"partial"
    _write(folder, metadata, episodes, rows, sources)
    report = AUDIT.audit(folder, git_root=git_root)
    assert report["failed"] == 0, report["violations"]
    trial = report["archive"]["trials"][0]
    assert not trial["eligible"] and trial["paid_budget"]["physics_steps"] == 13
    assert trial["observed_physics_steps"] == 10 and not trial["actual_effort_telemetry_complete"]
    assert report["archive"]["selection"]["selected"]["candidate"] == 1


@pytest.mark.parametrize("failure", ["one_substep_stop", "three_substep_fault"])
def test_partial_active_exposure_uses_paid_substeps_for_requested_effort(records, tmp_path, failure):
    metadata, episodes, rows, sources, git_root = deepcopy(records)
    ep = episodes[0]
    stopped = failure == "one_substep_stop"
    paid = 1 if stopped else 3
    request = rows[100]["requested_torque"]
    ep.update(status="terminated" if stopped else "exception", complete=False,
              reason="injected stop" if stopped else {"type": "RuntimeError", "message": "fault"},
              collector_exception=None if stopped else {"type": "RuntimeError", "message": "fault"},
              control_calls_attempted=101, control_steps=101 if stopped else 100,
              physics_steps=1000+paid, metric_control_step_count=1 if stopped else 0,
              tracking_rmse_rad=.04 if stopped else None,
              requested_squared_effort_nm2s=request[0]**2*paid*.002, saturated_control_steps=0,
              observed_diagnostic_substeps=1001 if stopped else 1000,
              telemetry_complete_for_paid_substeps=stopped,
              force_peak_scope="all paid substeps" if stopped else
                               "available returned-step telemetry only; incomplete, lower bound")
    ep["phase_budgets"] = {"prefix": {"control_calls_attempted": 100, "control_steps": 100, "physics_steps": 1000},
                            "control": {"control_calls_attempted": 1, "control_steps": 1 if stopped else 0, "physics_steps": paid}}
    keep = deepcopy(rows[:100])
    if stopped:
        row = deepcopy(rows[100])
        diag = row["diagnostics"]
        diag.update(executed_substeps=1, time=2.002, terminated=True, ground_normal_impulse_ns=.002)
        for key in ("applied_torque_history", "substep_ground_normal_forces", "substep_kinetic_energies", "substep_minimum_contact_distances"):
            diag[key] = diag[key][:1]
        keep.append(row)
    else:
        keep.append({"trial_id": ep["trial_id"], "collector_exception": ep["collector_exception"],
                     "phase": "control", "requested_torque": request})
    rows = keep + [r for r in rows if r["trial_id"] != ep["trial_id"]]
    metadata.update(control_calls_attempted=7901, control_steps=7901 if stopped else 7900,
                    physics_steps=79000+paid, all_trials_successful=False, completed_trials=26,
                    terminated_trials=1 if stopped else 0, exception_trials=0 if stopped else 1)
    folder = tmp_path/failure
    _write(folder, metadata, episodes, rows, sources)
    report = AUDIT.audit(folder, git_root=git_root)
    assert report["failed"] == 0, report["violations"]
    trial = report["archive"]["trials"][0]
    assert not trial["eligible"]
    assert trial["requested_squared_effort_nm2s"] == pytest.approx(request[0]**2*paid*.002)
    assert trial["paid_budget"]["physics_steps"] == 1000+paid
    assert trial["actual_effort_telemetry_complete"] == stopped
    assert trial["requested_squared_effort_from_unstored_paid_substeps_nm2s"] == pytest.approx(0. if stopped else request[0]**2*paid*.002)


def test_selection_uses_exact_protocol_order_and_requested_effort():
    trials = [{"trial_id": f"s{s}c{i}", "seed": s, "candidate": i, "eligible": True,
               "tracking_rmse_rad": 1., "requested_squared_effort_nm2s": 2.,
               "actual_squared_effort_nm2s": 0. if i == 8 else 100.}
              for s in AUDIT.SEEDS for i in range(9)]
    assert AUDIT.select_candidates(trials)["selected"]["candidate"] == 0
    for trial in trials:
        if trial["candidate"] == 2:
            trial["requested_squared_effort_nm2s"] = 1.
    assert AUDIT.select_candidates(trials)["selected"]["candidate"] == 2
    # A smaller raw mean wins even if the difference is very small and effort is larger.
    for trial in trials:
        if trial["candidate"] == 1:
            trial["tracking_rmse_rad"] = 1.-1e-12
    assert AUDIT.select_candidates(trials)["selected"]["candidate"] == 1
    for trial in trials:
        trial["eligible"] = False
    assert AUDIT.select_candidates(trials)["selected"] is None


def test_reference_condition_failure_cannot_be_reported_as_verified(records, tmp_path):
    metadata, _, rows, _, _ = records
    reference = tmp_path/"reference"
    reference.mkdir()
    changed = deepcopy(metadata)
    changed["environment_config"]["ground_contact_profile"] = "compliant"
    (reference/"metadata.json").write_text(json.dumps(changed), encoding="utf-8")
    states = {}
    with gzip.open(reference/"trace.jsonl.gz", "wt", encoding="utf-8") as stream:
        for source in rows:
            if source["candidate"] != 1:
                continue
            seed = source["seed"]
            state = states.setdefault(f"seed{seed}_candidate1", {"rows": 0, "anchor": hashlib.sha256()})
            state["anchor"].update(AUDIT.canonical(AUDIT._anchor_payload(source, "target_q_rad")))
            state["anchor"].update(b"\n")
            state["rows"] += 1
            row = deepcopy(source)
            row["kind"] = "fixed_pd"
            row["step_index"] = row.pop("control_index")
            row["target_q"] = row.pop("target_q_rad")
            stream.write(json.dumps(row)+"\n")
    checks = AUDIT.Checks()
    result = AUDIT._reference(reference, states, metadata, checks)
    assert checks.failed == 1
    assert all(pair["exact_replay"] for pair in result["per_seed"])
    assert not result["exact_replay_verified"]


@pytest.mark.parametrize("location", ["archive", "reference", "existing"])
def test_cli_rejects_input_directory_outputs_and_overwrite(tmp_path, monkeypatch, location):
    archive, reference = tmp_path/"archive", tmp_path/"reference"
    output = archive/"audit.json" if location == "archive" else reference/"audit.json"
    if location == "existing":
        output = tmp_path/"prior.json"
        output.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["audit", str(archive), "--reference", str(reference), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        AUDIT.main()
    assert error.value.code == 2
    if location == "existing":
        assert output.read_text(encoding="utf-8") == "preserve"
