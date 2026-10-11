"""Pure numeric and input-boundary tests; no simulator or real holdout reads."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("feedback_development_summary", ROOT/"scripts/summarize_feedback_development.py")
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


def _row():
    request = [.5]+[0.]*7
    return {"requested_torque": request,
            "observation_after": {"joint_velocity": [.2]+[0.]*7,
                                  "joint_position": [.03]+[0.]*6+[2.2]},
            "diagnostics": {"executed_substeps": 2,
                "applied_torque_history": [request, [0.]*8],
                "substep_ground_normal_forces": [1., 3.],
                "substep_kinetic_energies": [.2, .4],
                "substep_minimum_contact_distances": [-.001, -.002]}}


def test_partial_substep_effort_risk_and_native_endpoint_measurements():
    window = SUMMARY.empty_window()
    SUMMARY.consume_window(window, _row(), .04, [[-1., 2.]]*8, 0.)
    result = SUMMARY.finish_window(window)
    assert result["physics_substeps"] == 2
    assert result["tracking_rmse_rad"] == pytest.approx(.01)
    assert result["tail_25_mean_signed_error_rad"] == pytest.approx(-.01)
    assert result["requested_absolute_effort_nms"] == pytest.approx(.002)
    assert result["requested_squared_effort_nm2s"] == pytest.approx(.001)
    assert result["actual_absolute_effort_nms"] == pytest.approx(.001)
    assert result["actual_squared_effort_nm2s"] == pytest.approx(.0005)
    assert result["target_shield_fraction"] == .5
    assert result["saturated_control_calls"] == 1
    assert result["peak_ground_force_n"] == 3.
    assert result["ground_force_impulse_ns"] == pytest.approx(.008)
    assert result["peak_kinetic_energy_j"] == .4
    assert result["maximum_contact_penetration_m"] == .002
    assert result["maximum_native_endpoint_joint_speed_rad_s"] == .2
    assert result["maximum_native_endpoint_joint_limit_overshoot_rad"] == pytest.approx(.2)


def test_no_samples_or_zero_reference_does_not_become_zero_error_or_infinite_gain():
    result = SUMMARY.finish_window(SUMMARY.empty_window())
    assert result["tracking_rmse_rad"] is None
    assert result["peak_ground_force_n"] is None
    assert result["target_shield_fraction"] is None
    assert SUMMARY.relative(1., 0.) is None
    assert SUMMARY.relative(None, 1.) is None


def test_means_require_all_planned_seeds_and_retain_undefined_metrics():
    trials = [{"method": "candidate0", "candidate": 0, "kp": 4., "kd": 0., "seed": s,
               "complete": True, "windows": {"control": {"tracking_rmse_rad": s+1.,
                    "target_shield_fraction": None}}} for s in SUMMARY.SEEDS]
    result = SUMMARY.aggregate_groups(trials)[0]
    assert result["mean_metrics"]["control"]["tracking_rmse_rad"] == 2.
    assert result["mean_metrics"]["control"]["target_shield_fraction"] is None
    changed = deepcopy(trials)
    changed[0]["complete"] = False
    result = SUMMARY.aggregate_groups(changed)[0]
    assert not result["all_three_seeds_complete"] and result["mean_metrics"] is None
    assert len(result["per_seed"]) == 3
    assert SUMMARY.aggregate_groups(trials[1:])[0]["mean_metrics"] is None


def test_holdout_label_is_rejected_before_opening_trajectory(tmp_path, monkeypatch):
    folder = tmp_path/"synthetic_label_only"
    folder.mkdir()
    (folder/"metadata.json").write_text(json.dumps({"split": "holdout", "seeds": [0, 1, 2]}), encoding="utf-8")
    def forbidden(*args, **kwargs):
        pytest.fail("A holdout trajectory must never be opened.")
    monkeypatch.setattr(SUMMARY.gzip, "open", forbidden)
    with pytest.raises(ValueError, match="Only development"):
        SUMMARY.archive_identity(folder)


@pytest.mark.parametrize("location", ["archive", "reference", "audit", "existing"])
def test_cli_protects_inputs_and_existing_outputs(tmp_path, monkeypatch, location):
    archive, reference, audit = tmp_path/"archive", tmp_path/"reference", tmp_path/"audit.json"
    output = {"archive": archive/"summary.json", "reference": reference/"summary.json",
              "audit": audit, "existing": tmp_path/"prior.json"}[location]
    if location == "existing":
        output.write_text("preserve", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["summary", str(archive), "--reference", str(reference),
                      "--audit", str(audit), "--output", str(output)])
    with pytest.raises(SystemExit) as error:
        SUMMARY.main()
    assert error.value.code == 2
    if location == "existing":
        assert output.read_text(encoding="utf-8") == "preserve"
