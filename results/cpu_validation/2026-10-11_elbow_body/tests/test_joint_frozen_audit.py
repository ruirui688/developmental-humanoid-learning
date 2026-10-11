"""Selected-joint audit boundaries on explicit synthetic native logs only."""
from dataclasses import FrozenInstanceError, replace
import copy
import gzip
import json

import pytest
from test_local_frozen_audit import (
    core, TEST_SPEC, native, transition, saved_model, update_item, monitor_payload,
    partial_archive, complete_arithmetic_archive, write_manifest,
    failure_archive, stopped_calibration_archive, gate_fixture,
)

# Synthetic declarations reuse a committed protocol as a source-byte fixture.
# These are not the formal ELBOW_DEVELOPMENT_SPEC or a PD-selection result.
J1_SPEC = replace(TEST_SPEC, suite="synthetic_elbow_development", joint_index=1,
    split="development", claim_boundary="Synthetic elbow schema only; zero physical observations.")


def test_spec_is_immutable_and_copy_properties_cannot_change_it():
    with pytest.raises(FrozenInstanceError):
        J1_SPEC.joint_index = 0
    resets, gains = J1_SPEC.reset_seeds, J1_SPEC.pd_gains
    resets[0], gains["kp"] = 999, 4.
    assert J1_SPEC.reset_seeds[0] == 3757552657 and J1_SPEC.pd_kp == 64.
    with pytest.raises(ValueError):
        replace(J1_SPEC, seeds=[0, 1, 2])
    with pytest.raises(ValueError):
        replace(J1_SPEC, reset_seed_pairs=((0, 1), (0, 2), (2, 3)))
    assert core.SHOULDER_FINAL_SPEC.seeds == (20, 21, 22)
    assert core.SHOULDER_FINAL_SPEC.joint_index == 0


def test_unfrozen_elbow_rejects_before_any_archive_metadata_is_read(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unfrozen spec must reject before metadata read")
    monkeypatch.setattr(core, "load_json", forbidden)
    unfrozen = replace(core.ELBOW_DEVELOPMENT_SPEC, pd_kp=None, pd_kd=None)
    with pytest.raises(ValueError, match="frozen"):
        core.require_final("unread synthetic path", spec=unfrozen)
    report = core.audit("unread synthetic path", git_root=None, spec=unfrozen)
    assert report["failed"] == 1 and report["archive"] is None
    assert report["reported_paid_budget_if_replay_incomplete"] is None


@pytest.mark.parametrize("source", [[], (("audit", []),), (("audit", True),), (("audit", "a"), ("audit", "b"))])
def test_pd_selection_source_rejects_mutable_or_ambiguous_values(source):
    with pytest.raises(ValueError, match="Immutable unique PD"):
        replace(J1_SPEC, pd_selection_source=source)


@pytest.mark.parametrize("fault", ["missing", "hash", "calls", "bool_calls", "bool_updates"])
def test_pd_selection_source_mismatch_rejects_before_zip_and_trace(tmp_path, monkeypatch, fault):
    archive = partial_archive(tmp_path/"source", spec=J1_SPEC)
    provenance = dict(core.ELBOW_DEVELOPMENT_SPEC.pd_selection_source)
    declared = replace(J1_SPEC, pd_selection_source=core.ELBOW_DEVELOPMENT_SPEC.pd_selection_source)
    metadata = core.load_json(archive/"metadata.json")
    if fault == "hash": provenance["audit_sha256"] = "wrong"
    elif fault == "calls": provenance["development_control_calls"] = 8100
    elif fault == "bool_calls": provenance["development_control_calls"] = True
    elif fault == "bool_updates": provenance["body_model_updates"] = False
    if fault != "missing": metadata["pd_selection_source"] = provenance
    (archive/"metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Provenance must reject before ZIP/trace read")
    monkeypatch.setattr(core.zipfile, "ZipFile", forbidden)
    monkeypatch.setattr(core.gzip, "open", forbidden)
    report = core.audit(archive, git_root=None, spec=declared)
    assert report["failed"] == 1 and report["archive"] is None


@pytest.mark.parametrize("fault", ["suite", "joint", "seed", "protocol", "gains", "bool_gain", "bool_joint", "split"])
def test_scope_and_gain_reject_before_zip_or_trace(tmp_path, monkeypatch, fault):
    archive = partial_archive(tmp_path/"scope", spec=J1_SPEC)
    metadata = core.load_json(archive/"metadata.json")
    if fault == "suite": metadata["suite"] = "shoulder_final"
    elif fault == "joint": metadata["joint_index"] = 0
    elif fault == "seed": metadata["seeds"] = [20, 21, 22]
    elif fault == "protocol": metadata["protocol"]["path"] = "docs/other.md"
    elif fault == "gains": metadata["pd_gains"]["kp"] = 4.
    elif fault == "bool_gain": metadata["pd_gains"]["kd"] = False
    elif fault == "bool_joint": metadata["suite_spec"]["joint"] = True
    else: metadata["split"] = "final_holdout"
    (archive/"metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Scope rejection must precede sources/trace")
    monkeypatch.setattr(core, "verify_sources", forbidden)
    report = core.audit(archive, git_root=None, spec=J1_SPEC)
    assert report["failed"] == 1 and report["archive"] is None


def j1row(index=100, **kwargs):
    return transition(index, spec=J1_SPEC, inactive_q=.4, inactive_v=-.3, **kwargs)


@pytest.mark.parametrize("fault", [None, "j0_command", "other_command", "native_swap", "qpos_wrong_joint"])
def test_j1_transition_permission_and_native_mapping_remain_eight_dimensional(fault):
    row = j1row(q=-.005, v=.2, u=.125, next_q=.001, next_v=.3)
    if fault == "j0_command":
        row["requested_torque"] = [.125]+[0.]*7
    elif fault == "other_command":
        row["requested_torque"][2] = .1
    elif fault == "native_swap":
        row["observation_after"]["joint_position"][0:2] = row["observation_after"]["joint_position"][1::-1]
    elif fault == "qpos_wrong_joint":
        row["qpos"][8] = .4
    checks = core.Checks()
    core.verify_transition(row, None, {"physics": 1000}, [[-2., 2.]]*8, checks, "j1", joint_index=1)
    assert (checks.failed == 0) == (fault is None)
    assert row["observation_before"]["joint_position"][0] == .4
    assert row["observation_before"]["joint_position"][1] == -.005


def test_selected_risk_effort_coverage_and_tail_keep_j0_distinct():
    row = j1row(u=.5, next_q=.03, next_v=.3)
    for history in row["diagnostics"]["applied_torque_history"]:
        history[1] = 0.
    row["diagnostics"]["guarded_substeps"] = 10
    risk = core.new_risk()
    core.record_risk(risk, row, [[-2., 2.]]*8, joint_index=1)
    assert risk["target_guarded_substeps"] == 10
    assert risk["permission_screened_substeps_by_joint"] == [0, 10, 0, 0, 0, 0, 0, 0]
    assert risk["native_joint_speed_peak_rad_s"][:2] == [.3, .3]
    cal = [j1row(q=-.02, v=0.), j1row(101, q=.02, v=.2)]
    control = [j1row(q=.03, v=.3)]
    selected = core.state_coverage(cal, control, 0., joint_index=1)
    assert selected["q_outside_fraction"] == selected["v_outside_fraction"] == 1.
    assert selected["nearest_q_distance_mean_rad"] == pytest.approx(.01)
    assert core.state_coverage(cal, control, 0.)["either_outside_fraction"] == 0.
    row["target_q"] = .04
    row["step_index"] = 180
    tail = core.control_tail_metrics([row], joint_index=1)["first"]
    assert tail["tracking_rmse_rad"] == pytest.approx(.01)
    conditional = core.conditional_metrics([row], joint_index=1)["abs_u=0.5"]
    assert conditional["known_substep_effort"]["requested_absolute_nm_s"] == pytest.approx(.01)
    assert conditional["known_substep_effort"]["actual_absolute_nm_s"] == 0.


def test_j1_rls_reads_j1_and_preserves_scalar_feature_and_matrix_indices():
    row = j1row(kind="calibration", phase="calibration", q=-.005, v=.1, u=.125, next_v=.15)
    state = core.initial_state("hinge5")
    item = update_item(row, state, "hinge5", qref=-.005, joint_index=1)
    checks, replay = core.Checks(), core.initial_state("hinge5")
    core.replay_update(item, row, "hinge5", replay, -.005, checks, "j1", joint_index=1)
    assert checks.failed == 0
    assert item["features"] == [.1, 0., .125, 0., 1.]
    assert replay["theta"] == state["theta"] and replay["covariance"] == state["covariance"]
    wrong = core.Checks()
    core.replay_update(item, row, "hinge5", core.initial_state("hinge5"), -.005, wrong, "wrong j0")
    assert wrong.failed > 0


@pytest.mark.parametrize("environment", [False, True])
@pytest.mark.parametrize("substeps", [3, 10])
def test_j1_study_abort_is_independent_of_environment_and_partial_not_scored(environment, substeps):
    row = j1row(q=-.005, u=.5, next_q=.115, next_v=1., n=substeps, terminated=environment)
    row["target_q"] = .075
    row["predicted_next_qv"] = {"nominal_mpc": (.005, .2)}
    row["study_abort"] = monitor_payload(.115, 1., 100, "control", qref=-.005)
    checks = core.Checks()
    condition = core.normalize_study_row(row, -.005, checks, "j1", joint_index=1)
    assert checks.failed == 0 and condition["triggered"]
    flags = core.stop_flags(row)
    assert flags["study"] and flags["environment"] == environment
    metrics = core.conditional_metrics([row], joint_index=1)["abs_u=0.5"]
    assert metrics["known_substep_effort"]["actual_absolute_nm_s"] == pytest.approx(.5*substeps*.002)
    if substeps == 3:
        assert metrics["position_prediction_rmse"] == {} and metrics["tracking_rmse_rad"] is None
        assert core.window_denominators({100: row}, 1, 1, joint_index=1)["valid_physical_windows"] == 0
    else:
        assert metrics["tracking_rmse_rad"] == pytest.approx(.04)
        assert core.window_denominators({100: row}, 1, 1, joint_index=1)["valid_windows_ending_in_termination"] == 1


def test_j1_missing_actual_history_keeps_requested_paid_and_actual_lower_bound():
    ev = {"phase_effort": {"calibration": core.new_effort()},
        "phase_actual_effort_substeps": {"calibration": 0},
        "phase_actual_effort_complete": {"calibration": False}}
    ev["phase_effort"]["calibration"].update(requested_absolute_nm_s=.01, requested_squared_nm2_s=.005)
    exception = {"phase": "calibration", "requested_torque": [0., .5]+[0.]*6}
    checks = core.Checks()
    recovered = core.reconcile_effort(ev, "calibration", core.new_effort(), 10, 0, [exception], checks, "j1", joint_index=1)
    assert checks.failed == 0
    assert recovered["requested_effort_reconstruction_complete"]
    assert recovered["independent_effort"]["requested_absolute_nm_s"] == pytest.approx(.01)
    assert recovered["actual_effort_is_lower_bound"] and recovered["unreconstructed_actual_effort_substeps"] == 10
    assert recovered["independent_effort"]["actual_absolute_nm_s"] == 0.


def test_j1_rollout_uses_selected_native_joint_without_changing_pair_coordinates():
    q, v = -.005, .1
    next_q, next_v = core.predict(core.INITIAL["linear4"], -.005, q, v, .5)
    row = j1row(q=q, v=v, u=.5, next_q=next_q, next_v=next_v)
    result = core.diagnose_windows([row], 1, -.005, {"nominal_mpc": core.INITIAL["linear4"]}, joint_index=1)[0]
    assert result["predictors"]["nominal_mpc"]["terminal_position_rmse_rad"] == 0.
    assert result["predictors"]["nominal_mpc"]["terminal_velocity_rmse_rad_s"] == 0.
    row["observation_before"]["joint_velocity"][1] = float("nan")
    assert core.valid_window({100: row}, 100, 1, joint_index=1)[1] == "invalid_native_state"


def test_full_j1_negative_reference_synthetic_archive_keeps_native_array_order_and_budget(tmp_path):
    archive = complete_arithmetic_archive(tmp_path/"j1", spec=J1_SPEC, qref=-.005, inactive_q=.4, inactive_v=-.3)
    report = core.audit(archive, git_root=None, spec=J1_SPEC)
    assert report["failed"] == 0, report["violations"]
    assert report["archive"]["split"] == "development"
    assert report["archive"]["budget"] == {"control_calls_attempted": 6000, "control_steps": 6000, "physics_steps": 60000, "model_updates": 900}
    with gzip.open(archive/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    control = next(r for r in rows if r["phase"] == "control")
    assert control["observation_before"]["joint_position"][:2] == [.4, -.005]
    assert control["target_q"] == pytest.approx(.035)
    assert control["requested_torque"][0] == 0.
    assert not core.audit(archive, git_root=None)["final_gates"]["data_consistency_verified"]


@pytest.mark.parametrize("qref,target", [(-.02, .02), (.01, .03), (.005, .035), (2.34, 2.38), (.005, .16)])
def test_j1_target_margin_and_local_domain_reject_without_clipping(qref, target):
    limits = [0., 135.*3.141592653589793/180.]
    feasible = max(qref-.15, limits[0]+.03) <= target <= min(qref+.15, limits[1]-.03)
    if feasible:
        result = core.replay_mpc(core.INITIAL["linear4"], qref, qref, 0., target, 0., limits)
        assert result["feasible_candidates"] > 0
    else:
        with pytest.raises(ValueError, match="target"):
            core.replay_mpc(core.INITIAL["linear4"], qref, qref, 0., target, 0., limits)


@pytest.mark.parametrize("missing_item", [False, True])
def test_j1_atomic_exception_with_or_without_returned_item_reconstructs_rls_and_paid_cost(tmp_path, missing_item):
    archive = failure_archive(tmp_path/"atomic", missing_item=missing_item, spec=J1_SPEC,
        qref=-.005, inactive_q=.4, inactive_v=-.3)
    report = core.audit(archive, git_root=None, spec=J1_SPEC)
    assert report["failed"] == 0, report["violations"]
    seed = report["archive"]["seeds"][0]
    assert seed["model_updates"] == seed["independently_replayed_updates"] == 2
    assert seed["exception_snapshot_replayed_updates"] == 1
    evaluation = seed["evaluations"]["calibration"]
    assert evaluation["missing_risk_substeps"] == 10
    effort = evaluation["phase_effort"]["calibration"]
    assert effort["actual_effort_is_lower_bound"]
    assert effort["independent_effort"]["requested_absolute_nm_s"] == pytest.approx(.005)


@pytest.mark.parametrize("n,environment", [(3, False), (3, True), (10, False), (10, True)])
def test_j1_calibration_partial_or_complete_terminal_has_correct_update_and_stop_union(tmp_path, n, environment):
    archive = stopped_calibration_archive(tmp_path/"partial", count=1, last_substeps=n,
        env_stop=environment, spec=J1_SPEC, qref=-.005, inactive_q=.4, inactive_v=-.3)
    report = core.audit(archive, git_root=None, spec=J1_SPEC)
    # StudyAbort is checked after the returned endpoint, so it cannot alone
    # shorten a physics interval. A partial return needs an environment stop.
    if n < 10 and not environment:
        assert report["failed"] == 1
        assert report["violations"][0]["check"] == "legal_partial_substeps"
    else:
        assert report["failed"] == 0, report["violations"]
    seed = report["archive"]["seeds"][0]
    assert seed["model_updates"] == int(n == 10)
    evaluation = seed["evaluations"]["calibration"]
    assert not evaluation["eligible"] and evaluation["study_aborted"]
    assert (evaluation["velocity_prediction_rmse"]["hinge5"] is None) == (n == 3)
    assert report["archive"]["stops"] == {"study": 1, "environment": int(environment), "both": int(environment)}
    assert evaluation["phase_effort"]["calibration"]["independent_effort"]["requested_absolute_nm_s"] == pytest.approx(.125*n*.002)


def test_j1_last_planned_calibration_study_stop_keeps_three_hundred_updates_but_never_completes(tmp_path):
    archive = stopped_calibration_archive(tmp_path/"last", spec=J1_SPEC,
        qref=-.005, inactive_q=.4, inactive_v=-.3)
    report = core.audit(archive, git_root=None, spec=J1_SPEC)
    assert report["failed"] == 0, report["violations"]
    seed = report["archive"]["seeds"][0]
    assert seed["model_updates"] == 300
    evaluation = seed["evaluations"]["calibration"]
    assert not evaluation["completed"] and not evaluation["eligible"] and evaluation["study_aborted"]
    assert evaluation["paid_budget"]["physics_steps"] == 4000


def test_j1_gates_use_explicit_declared_seed_bank_and_keep_five_six_seven_scope():
    rows = gate_fixture()
    result = core.final_gates(rows, spec=J1_SPEC)
    assert result["model_contribution_gate"]["passed"]
    assert result["classical_comparison_gate"]["passed"] and result["complete_matrix"]
    rows[0]["evaluations"]["zero_torque"]["status"] = "terminated"
    result = core.final_gates(rows, spec=J1_SPEC)
    assert result["model_contribution_gate"]["passed"] and result["classical_comparison_gate"]["passed"]
    assert not result["complete_matrix"]
    assert not core.final_gates(rows)["model_contribution_gate"]["passed"]
