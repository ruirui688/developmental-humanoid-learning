"""Few E hand fixtures: no complete matrix, source D reads, RLS or MPC search."""
from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np


import pytest

pytest.importorskip("mujoco")
from developmental_physics import guard_lag_control_development as collector


class FakeEnv:
    created = []

    def __init__(self, config, mode="full_stop"):
        self.config, self.mode = config, mode
        self.step_id = self.physics_steps = 0
        self.terminated, self.reason = False, None
        self.joint_names = tuple(f"j{i}" for i in range(8))
        self.model = SimpleNamespace(joint=lambda name: SimpleNamespace(range=np.array([-1., 1.])))
        self.data = SimpleNamespace(qpos=np.zeros(15), qvel=np.zeros(14))
        self.created.append(self)

    def parameter_fingerprint(self):
        return "synthetic-plant"

    def reset(self, *, seed, pose):
        assert seed == collector.RESET_SEEDS[0] and pose == "supine"
        return self.observation()

    def observation(self):
        q = [.2]*8
        if self.step_id > 100 and self.mode == "full_stop":
            q[0] = .325
        return {"joint_position": q, "joint_velocity": [self.step_id*.0001, -self.step_id*.0001]+[0.]*6,
                "imu_gyro": [0.]*3, "imu_acceleration": [0.]*3,
                "actuator_torque": [0.]*8, "previous_command": [0.]*8}

    def diagnostics(self):
        return self.last_diagnostics

    def step(self, requested):
        active = self.step_id >= 100
        executed = 4 if active and self.mode in ("partial_stop", "unreturned") else 10
        self.physics_steps += executed
        if active and self.mode == "unreturned":
            raise ValueError("hand fixture unreturned partial physics")
        self.step_id += 1
        if active and self.mode == "partial_stop":
            self.terminated, self.reason = True, "hand_partial_stop"
        diagnostic = {"step_id": self.step_id, "physics_steps": self.physics_steps, "time": self.physics_steps*.002,
            "executed_substeps": executed, "applied_torque_history": [list(requested)]*executed,
            "requested_torque": list(requested), "accepted_torque": list(requested), "applied_torque": list(requested),
            "guarded_substeps": 0, "terminated": self.terminated, "reason": self.reason,
            "substep_ground_normal_forces": [0.]*executed, "substep_kinetic_energies": [0.]*executed,
            "substep_minimum_contact_distances": [0.]*executed,
            "ground_normal_force": 0., "ground_normal_impulse_ns": 0., "kinetic_energy": 0.,
            "minimum_contact_distance": 0., "peak_substep_ground_normal_force": 0., "peak_substep_kinetic_energy": 0.,
            "minimum_substep_contact_distance": 0., "contact_count": 0, "ground_contact_count": 0}
        self.last_diagnostics = diagnostic
        return SimpleNamespace(observation=self.observation(), diagnostics=diagnostic, terminated=self.terminated)


class BadWriter:
    def write(self, value):
        raise OSError("hand fixture write failed")

    def flush(self):
        pass


def trial(mode, writer=None):
    result = {"seed": 0, "reset_seed": collector.RESET_SEEDS[0], "evaluations": {},
              "fresh_prefix_bindings": {}, "expected_environment_fingerprint": "synthetic-plant"}
    # Two unchanged frozen cold helpers are explicit synthetic stand-ins;
    # neither is a restored D model or an empirical learned result.
    models = {name: collector.GuardLagPairBodyModel((.2, .2), public_joint_ranges=((-1., 1.), (-1., 1.)), trainable=False)
              for name in collector.MODEL_NAMES}
    episode = collector.episode_plan(0, "zero")
    writer = StringIO() if writer is None else writer
    fatal = None
    try:
        collector.run_trial(result, models, episode, writer, {"kp": (64., 64.), "kd": (0., 4.)},
                            env_factory=lambda config: FakeEnv(config, mode))
    except BaseException as exc:
        fatal = exc
    rows = [json.loads(line) for line in writer.getvalue().splitlines()] if isinstance(writer, StringIO) else []
    return result, episode, rows, fatal


def main():
    checks = []
    result, full, rows, fatal = trial("full_stop")
    assert fatal is None and full["status"] == "terminated" and full["control_calls_attempted"] == 101
    last = rows[-1]
    assert last["history"]["history_transition_ids"] == ["seed0_zero:98", "seed0_zero:99"]
    assert last["history"]["current_v_rad_s"] == [.01, -.01]
    assert last["history"]["previous_v_rad_s"] == [99*.0001, -99*.0001]
    ev = result["evaluations"]["zero"]
    assert ev["metric_control_step_count"] == 1 and ev["diagnostic_prediction_accounting"]["pair_prediction_attempts"] == 2
    assert ev["model_updates"] == 0 and ev["planning_accounting"]["pair_prediction_attempts"] == 0
    checks.append("complete terminal scored, native prefix history exact, both diagnostics once, zero updates")

    result, partial, rows, fatal = trial("partial_stop")
    ev = result["evaluations"]["zero"]
    assert fatal is None and partial["status"] == "terminated" and partial["physics_steps"] == 1004
    assert ev["metric_control_step_count"] == 0 and len(ev["partial_interval_target_errors_rad"]) == 1
    assert ev["actual_effort_complete"] and ev["phase_actual_effort_substeps"]["control"] == 4
    checks.append("partial terminal paid and retained outside full metrics")

    result, unreturned, rows, fatal = trial("unreturned")
    ev = result["evaluations"]["zero"]
    assert fatal is None and unreturned["status"] == "exception" and unreturned["physics_steps"] == 1004
    assert unreturned["unreturned_physics_steps"] == 4 and ev["missing_control_effort_substeps"] == 4
    assert not ev["actual_effort_complete"] and rows[-1]["collector_exception"]["type"] == "ValueError"
    checks.append("ordinary unreturned physics exception stays local and missing actual effort remains explicit")

    _, failed_write, _, fatal = trial("full_stop", BadWriter())
    assert isinstance(fatal, OSError) and failed_write["returned_unwritten_steps"] == 1
    assert failed_write["control_calls_attempted"] == 1 and failed_write["physics_steps"] == 10
    checks.append("write failure remains fatal with paid returned-unwritten interval")

    prior_formal_flag = collector.FORMAL_CONTROL_ENABLED
    try:
        collector.FORMAL_CONTROL_ENABLED = False
        try:
            collector.run_guard_lag_control_development(Path(__file__).with_name("never_created"))
        except RuntimeError:
            pass
        else:
            raise AssertionError("draft public formal flag failed closed")
    finally:
        collector.FORMAL_CONTROL_ENABLED = prior_formal_flag
    assert not Path(__file__).with_name("never_created").exists()
    checks.append("formal flag rejects before source/Git/environment/output")

    try:
        collector.native_history([], FakeEnv.created[0].observation(), "seed0_zero", 100)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown history accepted")
    checks.append("unknown native history cannot be zero-filled")

    print(json.dumps({"checks": len(checks), "failed": 0, "cases": checks,
        "fixture_scope": "four hand environment trials; no fixed twelve-trial matrix or MPC search",
        "fake_env_calls_attempted": sum(x["control_calls_attempted"] for x in (full, partial, unreturned, failed_write)),
        "fake_env_returned_control_steps": sum(x["control_steps"] for x in (full, partial, unreturned, failed_write)),
        "fake_substeps": sum(x.physics_steps for x in FakeEnv.created),
        "model_pair_predictions": 6, "model_scalar_predictions": 12,
        "MPC_select_calls": 0, "RLS_updates": 0, "D_data_reads": 0, "real_physics_calls": 0, "Git_calls": 0}, ensure_ascii=False, indent=2))


def test_hand_fixtures():
    main()


if __name__ == "__main__":
    main()
