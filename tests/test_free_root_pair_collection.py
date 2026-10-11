"""Six new bounded collector checks; synthetic native endpoints, no MuJoCo physics.

Draft production path: tests/test_free_root_pair_collection.py.
Each fixture uses PREFIX=2 and at most two active calls. The real environment
factory and XML path are replaced; no body model, PD, RLS or MPC is invoked.
The update callback is only an observer, not an algorithm implementation.
"""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from developmental_physics import free_root_pair_development as collector


class FakeEndpointEnv:
    """Native API ledger with chosen return failures; no motion simulation."""

    def __init__(self, *, audit_cost, events, options):
        self.cost, self.events, self.options = audit_cost, events, options
        self.physics_steps = 0
        self.step_attempts = 0
        self.metadata_calls = 0
        self.reset_calls = []
        self.requests = []
        self.data = SimpleNamespace(time=0.)
        self._joint_ids = np.arange(8)
        self.model = SimpleNamespace(jnt_range=np.repeat([[-2., 2.]], 8, axis=0))

    def observation(self, request=None, *, boundary=False):
        q, v = [0.] * 8, [0.] * 8
        if boundary:
            q[0], v[1] = .12, 1.
        return {
            "joint_position": q,
            "joint_velocity": v,
            "imu_gyro": [0.] * 3,
            "imu_acceleration": [0.] * 3,
            "actuator_torque": [2., -3.] + [0.] * 6,
            "previous_command": [0.] * 8 if request is None else list(request),
        }

    def reset(self, *, seed, pose):
        self.reset_calls.append((seed, pose))
        self.events.append(("reset", seed, pose))
        assert self.physics_steps == 0 and len(self.reset_calls) == 1
        return self.observation()

    def frozen_metadata(self):
        self.metadata_calls += 1
        drift = self.options.get("metadata_drift") and self.metadata_calls > 1
        return {
            "support": {"root": "original_asset_freejoint", "mount": None,
                        "initial_pose": "supine", "external_support": False},
            "physical_fingerprint": "synthetic-physical",
            "execution_fingerprint": "synthetic-drift" if drift else "synthetic-execution",
            "action_interface": {"active_control_dt_s": .002,
                                 "requested_control_substeps": 1},
        }

    def step(self, request):
        self.step_attempts += 1
        self.requests.append(list(request))
        self.events.append(("step", self.step_attempts))
        assert len(request) == 8 and request[2:] == [0.] * 6
        if self.step_attempts == self.options.get("zero_substep_stop_on"):
            return SimpleNamespace(
                observation=self.observation(request), terminated=True,
                reason="synthetic_base_protection_stop",
                diagnostics={"executed_substeps": 0, "applied_torque": list(request)},
            )
        self.physics_steps += 1
        self.data.time = self.physics_steps * .002
        if self.step_attempts == self.options.get("core_exception_on"):
            raise RuntimeError("synthetic_core_failure_after_paid_substep")
        boundary = self.step_attempts == self.options.get("boundary_on")
        return SimpleNamespace(
            observation=self.observation(request, boundary=boundary), terminated=False,
            reason=None,
            diagnostics={"executed_substeps": 1, "applied_torque": list(request)},
        )

    def audit_floor_pairs(self):
        self.events.append(("audit", self.step_attempts))
        self.cost["audit_contact_snapshot_attempts"] += 1
        if self.step_attempts == self.options.get("audit_failure_on"):
            self.cost["audit_contact_snapshot_exceptions"] += 1
            raise RuntimeError("synthetic_audit_query_failure")
        self.cost["audit_contact_snapshot_returns"] += 1
        return {
            "time_s": self.data.time, "all_contact_count": 1,
            "floor_pairs": [{"category": "left_arm", "other_geom_name": "left_forearm_geom",
                             "positive_normal_force_n": 1., "signed_normal_force_n": 1.,
                             "distance_m": -.001}],
        }


@pytest.fixture
def run_synthetic(monkeypatch, tmp_path):
    """Each invocation has its own one-reset fake instance and paid ledger."""
    monkeypatch.setattr(collector, "PREFIX", 2)
    asset = tmp_path / "synthetic_original_body.xml"
    asset.write_text("<synthetic-original-free-root/>", encoding="utf-8")
    monkeypatch.setattr(collector, "MODEL_PATH", asset)

    def run(**options):
        cost, trace, journal, trial, updates, events, instances = Counter(), [], [], {}, [], [], []

        def factory(*, audit_cost):
            env = FakeEndpointEnv(audit_cost=audit_cost, events=events, options=options)
            instances.append(env)
            return env

        def paid_writer(entry):
            events.append(("journal", entry["entry_kind"], entry["record"]["control_index"]))
            journal.append(deepcopy(entry))

        def observe_update(row):
            assert row["phase"] == "active" and row["contact_audit_complete"] is True
            assert row["study_abort"] is None and row["complete_native_endpoint"] is True
            events.append(("update_callback", row["control_index"]))
            updates.append(deepcopy(row))

        def actor(_observation, _index, current):
            return (.2, -.3), {"current_target_q2": current["qref2"]}

        monkeypatch.setattr(collector, "FreeRootFastFeedbackGroundBodyEnv", factory)
        collector.collect_trial(
            trial, trace, cost, seed=7901, active_steps=2, kind="calibration",
            actor=actor, after_transition=observe_update, paid_writer=paid_writer,
        )
        return SimpleNamespace(cost=cost, trace=trace, journal=journal, trial=trial,
                               updates=updates, events=events, env=instances[0])

    return run


def test_new_supine_collector_completes_one_reset_and_paid_before_audit(run_synthetic):
    saved = run_synthetic()
    assert saved.env.reset_calls == [(7901, "supine")]
    assert saved.cost["environment_constructor_returns"] == saved.cost["reset_returns"] == 1
    assert saved.cost["control_call_returns"] == saved.cost["confirmed_physics_substeps"] == 4
    assert saved.trial["complete"] is True and saved.trial["metadata_stable"] is True
    assert saved.trial["free_root_domain_qualification_passed"] is True
    assert saved.trial["qref2"] == [0., 0.]
    assert len(saved.trace) == 4 and len(saved.updates) == 2
    assert saved.env.requests[:2] == [[0.] * 8] * 2
    assert saved.env.requests[2:] == [[.2, -.3] + [0.] * 6] * 2
    for index in range(4):
        paid = saved.events.index(("journal", "paid_native_endpoint", index))
        audit = saved.events.index(("audit", index + 1))
        annotated = saved.events.index(("journal", "endpoint_audit_annotation", index))
        assert paid < audit < annotated
        if index >= 2:
            assert annotated < saved.events.index(("update_callback", index))
    assert saved.trial["actual_effort"]["active"]["actual_absolute_axis_nm_s"] == pytest.approx([.008, .012])
    assert saved.trial["actual_effort"]["active"]["complete"] is True
    assert saved.trial["actual_effort"]["active"]["unknown_actual_effort_substeps"] == 0
    assert saved.trial["actual_effort"]["active"]["actual_effort_population_complete"] is True
    for phase in ("prefix", "active"):
        contact = saved.trial["contact_population"]["phases"][phase]
        assert contact["classes"]["left_arm"]["positive_contact_endpoint_count"] == 2
        assert contact["unknown_paid_contact_substeps"] == 0 and contact["qualification_passed"] is True
    assert saved.cost["body_model_build_attempts"] == saved.cost["RLS_vector_update_attempts"] == 0


def test_new_audit_failure_retains_paid_actual_effort_and_never_updates(run_synthetic):
    saved = run_synthetic(audit_failure_on=3)
    row = saved.trace[-1]
    assert saved.cost["control_call_returns"] == saved.cost["confirmed_physics_substeps"] == 3
    assert row["complete_native_endpoint"] is True and row["contact_audit_complete"] is False
    assert row["confirmed_completed_substeps"] == 1 and row["study_abort"] is None
    assert saved.trial["complete"] is False and saved.trial["failure"]["type"] == "RuntimeError"
    assert saved.updates == []
    paid = next(entry for entry in saved.journal
                if entry["entry_kind"] == "paid_native_endpoint" and entry["record"]["control_index"] == 2)
    assert paid["record"]["observation_after"]["actuator_torque"][:2] == [2., -3.]
    assert saved.events.index(("journal", "paid_native_endpoint", 2)) < saved.events.index(("audit", 3))
    phase = saved.trial["actual_effort"]["active"]
    assert phase["captured_substeps"] == 1 and phase["complete"] is False
    assert phase["actual_absolute_axis_nm_s"] == pytest.approx([.004, .006])
    assert phase["actual_squared_axis_nm2_s"] == pytest.approx([.008, .018])
    assert phase["counts_are_lower_bounds_if_incomplete"] is True
    assert phase["unknown_actual_effort_substeps"] == 0 and phase["actual_effort_population_complete"] is True
    contact = saved.trial["contact_population"]["phases"]["active"]
    assert contact["unknown_paid_contact_substeps"] == 1 and contact["qualification_passed"] is False
    assert contact["classes"]["left_arm"]["positive_count_unknown_if_missing"] is True
    assert row["diagnostics"]["substep_native_and_contact_records"][0]["contact_audit_complete"] is False
    assert not any(entry["entry_kind"] == "endpoint_audit_annotation"
                   and entry["record"]["control_index"] == 2 for entry in saved.journal)
    assert saved.journal[-1]["entry_kind"] == "collector_failure_annotation"


def test_new_active_equality_stops_after_paid_audit_and_before_update(run_synthetic):
    saved = run_synthetic(boundary_on=3)
    assert saved.cost["control_call_returns"] == saved.cost["confirmed_physics_substeps"] == 3
    assert saved.trial["complete"] is False and saved.trial["failure"] is None
    assert saved.trial["stop"]["primary_reason"] == "StudyAbort" and saved.updates == []
    assert saved.trace[-1]["contact_audit_complete"] is True
    assert saved.trace[-1]["environment_terminated"] is False
    triggers = saved.trace[-1]["study_abort"]["triggers"]
    assert {tuple(item.items()) for item in triggers} == {
        (("joint_index", 0), ("signal", "absolute_q_minus_qref_rad")),
        (("joint_index", 1), ("signal", "absolute_velocity_rad_s")),
    }
    assert saved.trial["actual_effort"]["active"]["captured_substeps"] == 1
    assert saved.env.step_attempts == 3


def test_new_metadata_drift_rejects_complete_qualification_without_erasing_paid_calls(run_synthetic):
    saved = run_synthetic(metadata_drift=True)
    assert saved.env.step_attempts == saved.cost["confirmed_physics_substeps"] == 4
    assert saved.trial["returned_intervals"] == 4 and len(saved.updates) == 2
    assert saved.trial["metadata_stable"] is False and saved.trial["complete"] is False
    assert saved.trial["status"] == "failed" and saved.trial["stop"] is None
    assert "original_free_root_configuration_changed" in saved.trial["failure"]["message"]
    assert saved.trial["actual_effort"]["active"]["captured_substeps"] == 2
    assert saved.trial["actual_effort"]["active"]["actual_absolute_axis_nm_s"] == pytest.approx([.008, .012])
    assert saved.trial["actual_effort"]["active"]["complete"] is False
    assert saved.trial["actual_effort"]["active"]["actual_effort_population_complete"] is True


def test_new_zero_substep_base_stop_cannot_become_complete_or_trigger_audit(run_synthetic):
    saved = run_synthetic(zero_substep_stop_on=1)
    assert saved.cost["control_call_attempts"] == saved.cost["control_call_returns"] == 1
    assert saved.cost["confirmed_physics_substeps"] == saved.env.physics_steps == 0
    assert saved.cost["captured_native_endpoints"] == saved.cost["audit_contact_snapshot_attempts"] == 0
    assert len(saved.trace) == 1 and saved.updates == []
    assert saved.trace[0]["confirmed_completed_substeps"] == 0
    assert saved.trace[0]["complete_native_endpoint"] is False
    assert saved.trial["stop"]["primary_reason"] == "synthetic_base_protection_stop"
    assert saved.trial["status"] == "stopped" and saved.trial["complete"] is False
    assert saved.trial["failure"] is None and saved.env.step_attempts == 1
    assert all(phase["captured_substeps"] == 0 and phase["complete"] is False
               for phase in saved.trial["actual_effort"].values())


def test_new_core_exception_keeps_paid_delta_and_marks_missing_actual_as_lower_bound(run_synthetic):
    saved = run_synthetic(core_exception_on=3)
    row = saved.trace[-1]
    assert saved.cost["control_call_attempts"] == saved.cost["confirmed_physics_substeps"] == 3
    assert saved.cost["control_call_returns"] == saved.cost["captured_native_endpoints"] == 2
    assert saved.cost["control_call_exceptions"] == 1 and saved.env.step_attempts == 3
    assert row["confirmed_completed_substeps"] == 1 and row["returned"] is False
    assert row["complete_native_endpoint"] is False and row["diagnostics"] is None
    assert "observation_after" not in row and row["collector_exception"]["type"] == "RuntimeError"
    assert saved.trial["complete"] is False and saved.updates == []
    assert saved.trial["actual_effort"]["prefix"]["captured_substeps"] == 2
    active = saved.trial["actual_effort"]["active"]
    assert active["captured_substeps"] == 0 and active["complete"] is False
    assert active["counts_are_lower_bounds_if_incomplete"] is True
    assert active["confirmed_paid_substeps"] == active["unknown_actual_effort_substeps"] == 1
    assert active["actual_effort_population_complete"] is False
    assert saved.cost["audit_contact_snapshot_attempts"] == 2
    annotation = saved.journal[-1]
    assert annotation["entry_kind"] == "collector_failure_annotation"
    assert annotation["record"]["confirmed_completed_substeps"] == 1
    assert annotation["record"]["complete_native_endpoint"] is False
