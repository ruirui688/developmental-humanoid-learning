"""New one-substep evidence boundary only; no physical fixtures or old RLS."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "_fast_feedback_engineering_checks", Path(__file__).resolve().parents[1] / "scripts/validate_fast_feedback_engineering.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def sample(index):
    return {"physics_step": index+1, "time": (index+1)*.002,
            "applied_command8": [0.]*8, "actual_actuator_torque8": [0.]*8,
            "observation": {name: [0.]*size for name, size in (
                ("joint_position", 8), ("joint_velocity", 8), ("imu_gyro", 3),
                ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8))},
            "floor_contacts": [], "diagnostics": {"root_position": [0., 0., 1.], "root_quaternion": [1., 0., 0., 0.]}}


def row(index):
    return {"seed": 7600, "control_index": index,
            "phase": "prefix" if index < 1000 else "active",
            "phase_index": index if index < 1000 else index-1000,
            "returned": True, "environment_terminated": False, "study_abort": None,
            "target_error_rad": None if index < 1000 else [.005, -.006],
            "diagnostics": {"executed_substeps": 1, "substep_native_and_contact_records": [sample(index)]}}


def test_missing_contact_diagnostics_cannot_be_empty_observation():
    item = row(0)
    assert runner.complete_fast_telemetry(item)
    del item["diagnostics"]["substep_native_and_contact_records"][0]["floor_contacts"]
    assert not runner.complete_fast_telemetry(item)


def test_old_20ms_capture_is_not_one_substep_evidence():
    item = row(0)
    item["diagnostics"]["substep_native_and_contact_records"] = [sample(i) for i in range(10)]
    assert not runner.complete_fast_telemetry(item)


def test_completed_first_window_does_not_rank_stopped_population():
    records = [row(i) for i in range(2003)]
    records[-1]["study_abort"] = {"type": "StudyAbort"}
    support = {"installation": {"fixed_torso_world_position": [0., 0., 1.],
                                "fixed_torso_world_quaternion": [1., 0., 0., 0.]}}
    def no_old_gate(*args):
        raise AssertionError("old 20ms gate must not run")
    result = runner.qualification(records, support, SimpleNamespace(qualification=no_old_gate))
    assert not result["full_1000_prefix_2000_active"]
    assert not result["engineering_qualification_passed"]
    first, second = result["last200_post_step_windows"]
    assert first["observed_count"] == 200 and first["available"] is False
    assert first["per_axis_mae_rad"] is None and second["observed_count"] == 0
