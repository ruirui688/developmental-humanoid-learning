"""Prepared-only new pure protocol/paid-row checks; no MuJoCo import or physics.

Draft production path: tests/test_free_root_fast_feedback_engineering.py.
The runner is imported for stdlib-only helpers; its production imports are deferred.
"""
import ast
from collections import Counter
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fr0_engineering_pure", ROOT / "scripts/validate_free_root_fast_feedback_engineering.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def complete_records():
    records = []
    for index in range(3000):
        records.append({"index": index, "phase": RUNNER.phase(index),
                        "active_index": None if index < 1000 else index - 1000,
                        "confirmed_physics_substeps": 1, "complete_endpoint": True,
                        "complete_native_endpoint": True, "contact_audit_complete": True,
                        "requested_torque": [0.] * 8,
                        "observation_after": {"actuator_torque": [.2, .1] + [0.] * 6},
                        "target_error_rad": None if index < 1000 else [.005, .009],
                        "contacts": {"floor_pairs": [{"category": "left_arm", "positive_normal_force_n": 1.}]}})
    return records


class PublicRanges:
    def __getitem__(self, _):
        return [[-1., 1.], [0., 2.4]]


class NativeEndpointFixture:
    """Synthetic API endpoint ledger, not simulated motion or a body model."""
    def __init__(self, cost, *, audit_failure=False):
        self.cost, self.audit_failure = cost, audit_failure
        self.physics_steps = 0
        self.model = SimpleNamespace(jnt_range=PublicRanges())
        self._joint_ids = [0, 1]

    def observation(self):
        return {"joint_position": [0., .12] + [0.] * 6,
                "joint_velocity": [0., 1.] + [0.] * 6,
                "imu_gyro": [0.] * 3, "imu_acceleration": [0.] * 3,
                "actuator_torque": [.2, .1] + [0.] * 6, "previous_command": [0.] * 8}

    def reset(self, *, seed, pose):
        assert seed == 7800 and pose == "supine"
        return self.observation()

    def frozen_metadata(self):
        return {"physical_fingerprint": "same", "execution_fingerprint": "same"}

    def step(self, request):
        assert len(request) == 8 and request[2:] == [0.] * 6
        self.physics_steps += 1
        return SimpleNamespace(observation=self.observation(), diagnostics={"executed_substeps": 1},
                               terminated=False, reason=None)

    def audit_floor_pairs(self):
        self.cost["audit_contact_snapshot_attempts"] += 1
        if self.audit_failure:
            self.cost["audit_contact_snapshot_exceptions"] += 1
            raise ValueError("synthetic_audit_query_failure")
        self.cost["audit_contact_snapshot_returns"] += 1
        return {"time_s": self.physics_steps * .002,
                "floor_pairs": [{"category": "left_arm", "positive_normal_force_n": 1.}]}


def test_fixed_public_pd_and_target_infeasibility_do_not_relax_permission():
    bounded, raw = RUNNER.pd_request([0., 0.], [0., 1.], [.04, .08])
    assert raw == [2.56, 1.12]
    assert bounded == [.5, .5]
    directions, targets = RUNNER.bind_targets([0., .12], [[-1., 1.], [0., 2.4]])
    assert directions == [1, 1] and targets == [[.04, .16], [.08, .2]]
    with pytest.raises(ValueError, match="no_clip_or_direction_retry"):
        RUNNER.bind_targets([.045, .12], [[0., .09], [0., 2.4]])


def test_partial_window_population_cannot_pass_even_with_zero_errors():
    records = complete_records()[:2000]
    metrics = RUNNER.engineering_metrics(records, complete=False, metadata_stable=True)
    assert metrics["windows"][0]["observed_count"] == 200
    assert all(not w["available"] and w["mae_axis_rad"] is None for w in metrics["windows"])
    assert not metrics["engineering_qualification_passed"]


def test_contact_requires_each_full_phase_and_mae_all_four_axes():
    records = complete_records()
    assert RUNNER.engineering_metrics(records, complete=True, metadata_stable=True)["engineering_qualification_passed"]
    for row in records[2000:]:
        row["contacts"]["floor_pairs"] = [{"category": "other", "positive_normal_force_n": 2.}]
    failed = RUNNER.engineering_metrics(records, complete=True, metadata_stable=True)
    assert not failed["left_arm_contact_checks"]["target_B"]
    assert not failed["engineering_qualification_passed"]
    assert all(all(w["passed_axis"]) for w in failed["windows"])
    records = complete_records()
    records[-1]["target_error_rad"] = [.005, 3.]
    failed = RUNNER.engineering_metrics(records, complete=True, metadata_stable=True)
    assert failed["windows"][1]["passed_axis"] == [True, False]
    assert not failed["engineering_qualification_passed"]


def test_audit_failure_keeps_paid_native_row_effort_and_unknown_contact():
    cost, journal = Counter(), io.StringIO()
    result = RUNNER.collect(NativeEndpointFixture(cost, audit_failure=True), cost, journal)
    assert cost["control_call_attempts"] == cost["control_call_returns"] == cost["confirmed_physics_substeps"] == 1
    assert cost["captured_native_endpoints"] == 1 and cost["captured_complete_endpoints"] == 0
    assert result["failure"] and not result["complete"]
    entries = [json.loads(line) for line in journal.getvalue().splitlines()]
    assert entries[0]["entry_kind"] == "paid_native_endpoint"
    assert entries[0]["record"]["observation_after"]["actuator_torque"][:2] == [.2, .1]
    assert entries[0]["record"]["confirmed_physics_substeps"] == 1
    summary = result["metrics"]["phase_effort_and_contacts"]["prefix"]
    assert summary["observed_native_endpoints"] == 1 and summary["observed_contact_endpoints"] == 0
    assert summary["actual_effort_complete"]
    assert summary["actual_endpoint_sample_absolute_nm_s_axis"] == [.0004, .0002]
    assert summary["classes"]["left_arm"]["full_positive_contact_count_unknown"]


def test_prefix_has_no_study_check_but_first_active_equality_stops():
    cost, journal = Counter(), io.StringIO()
    result = RUNNER.collect(NativeEndpointFixture(cost), cost, journal)
    assert cost["confirmed_physics_substeps"] == 1001 and cost["pd_request_returns"] == 1
    assert cost["study_check_returns"] == 1 and result["stop"]["study_abort"]["type"] == "StudyAbort"
    assert not result["complete"] and all(not w["available"] for w in result["metrics"]["windows"])
    assert RUNNER.study_abort([.12, 0.], [0., 0.], [0., 0.]) is not None


def test_wrapper_inherits_original_reset_step_observation_and_audit_has_no_forward():
    path = ROOT / "src/developmental_physics/free_root_fast_feedback_environment.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wrapper = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    methods = {n.name: n for n in wrapper.body if isinstance(n, ast.FunctionDef)}
    assert {"reset", "step", "observation", "_stop_reason"}.isdisjoint(methods)
    for name in ("audit_floor_pairs", "_audit_floor_pairs"):
        calls = [n.func.attr for n in ast.walk(methods[name]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        assert not {"mj_step", "mj_forward", "step", "reset"}.intersection(calls)
