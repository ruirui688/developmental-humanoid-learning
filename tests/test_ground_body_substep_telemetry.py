"""Independent, no-training checks for actual-integrator substep telemetry."""

from __future__ import annotations

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from developmental_physics.environment import ExplorationConfig, GroundBodyEnv


NATIVE_OBSERVATIONS = {
    "joint_position", "joint_velocity", "imu_gyro", "imu_acceleration",
    "actuator_torque", "previous_command",
}


def _engine_sample(model, data):
    """Read engine truth directly, without the wrapper's diagnostics method."""
    floor_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
    normal_force = 0.0
    for contact_id in range(data.ncon):
        contact = data.contact[contact_id]
        if floor_id in (contact.geom1, contact.geom2):
            force = np.empty(6)
            mujoco.mj_contactForce(model, data, contact_id, force)
            normal_force += max(0.0, float(force[0]))
    return {
        "time": float(data.time),
        "force": normal_force,
        "kinetic_energy": float(data.energy[1]),
        "distance": min(
            (float(data.contact[index].dist) for index in range(data.ncon)),
            default=0.0,
        ),
    }


def _install_forward_spy(monkeypatch, env):
    samples = []
    original_forward = mujoco.mj_forward

    def forward_spy(model, data):
        original_forward(model, data)
        if data is env.data:
            samples.append(_engine_sample(model, data))

    monkeypatch.setattr(mujoco, "mj_forward", forward_spy)
    return samples


def _assert_telemetry(diagnostics, samples, physics_dt):
    keys = (
        ("substep_ground_normal_forces", "force"),
        ("substep_kinetic_energies", "kinetic_energy"),
        ("substep_minimum_contact_distances", "distance"),
    )
    assert len(samples) == diagnostics["executed_substeps"]
    for diagnostic_key, sample_key in keys:
        assert isinstance(diagnostics[diagnostic_key], list)
        assert len(diagnostics[diagnostic_key]) == len(samples)
        np.testing.assert_allclose(
            diagnostics[diagnostic_key],
            [sample[sample_key] for sample in samples],
            atol=0.0, rtol=0.0,
        )
    forces = [sample["force"] for sample in samples]
    kinetic_energies = [sample["kinetic_energy"] for sample in samples]
    distances = [sample["distance"] for sample in samples]
    assert diagnostics["peak_substep_ground_normal_force"] == max(forces, default=0.0)
    assert diagnostics["ground_normal_impulse_ns"] == pytest.approx(
        sum(forces) * physics_dt, abs=1e-12, rel=1e-12
    )
    assert diagnostics["peak_substep_kinetic_energy"] == max(
        kinetic_energies, default=0.0
    )
    assert diagnostics["minimum_substep_contact_distance"] == min(
        distances, default=0.0
    )


def test_each_actual_substep_is_sampled_once_after_forward(monkeypatch):
    env = GroundBodyEnv()
    env.reset(seed=12, pose="supine")
    samples = _install_forward_spy(monkeypatch, env)
    total_sample_count = 0
    saw_ground_force = False

    for step_id in range(1, 9):
        previous_time = float(env.data.time)
        samples.clear()
        result = env.step(np.zeros(8))
        assert not result.terminated
        assert result.diagnostics["executed_substeps"] == env.config.control_substeps
        _assert_telemetry(result.diagnostics, samples, env.config.physics_dt)
        np.testing.assert_allclose(
            np.diff([previous_time] + [sample["time"] for sample in samples]),
            env.config.physics_dt, rtol=0.0, atol=1e-16,
        )
        assert samples[-1]["time"] == env.data.time
        assert result.diagnostics["ground_normal_force"] == samples[-1]["force"]
        assert result.diagnostics["kinetic_energy"] == samples[-1]["kinetic_energy"]
        assert result.diagnostics["step_id"] == step_id
        total_sample_count += len(samples)
        assert result.diagnostics["physics_steps"] == total_sample_count
        saw_ground_force |= any(sample["force"] > 0.0 for sample in samples)

    assert total_sample_count == 8 * env.config.control_substeps
    assert saw_ground_force


def test_contact_transient_peak_and_impulse_are_not_endpoint_only(monkeypatch):
    env = GroundBodyEnv(ExplorationConfig(control_substeps=50))
    env.reset(seed=0, pose="supine")
    samples = _install_forward_spy(monkeypatch, env)

    result = env.step(np.zeros(8))

    assert not result.terminated
    _assert_telemetry(result.diagnostics, samples, env.config.physics_dt)
    forces = np.array([sample["force"] for sample in samples])
    assert np.any(forces == 0.0)
    assert np.max(forces) > 0.0
    assert np.max(forces) > forces[-1] * 1.05
    assert result.diagnostics["peak_substep_ground_normal_force"] > (
        result.diagnostics["ground_normal_force"]
    )
    assert result.diagnostics["ground_normal_impulse_ns"] > 0.0


def test_partial_step_stop_counts_only_the_executed_substeps(monkeypatch):
    config = ExplorationConfig(kinetic_energy_limit=1e-5, reset_clearance=0.05)
    env = GroundBodyEnv(config)
    env.reset(seed=0, pose="supine")
    samples = _install_forward_spy(monkeypatch, env)

    result = env.step(np.zeros(8))

    assert result.terminated
    assert result.reason == "kinetic_energy_limit"
    assert result.diagnostics["executed_substeps"] == 1
    assert result.diagnostics["physics_steps"] == 1
    assert env.data.time == config.physics_dt
    _assert_telemetry(result.diagnostics, samples, config.physics_dt)
    assert result.diagnostics["peak_substep_kinetic_energy"] > config.kinetic_energy_limit
    np.testing.assert_array_equal(env.data.ctrl, np.zeros(8))
    previous_time = float(env.data.time)
    previous_samples = list(samples)
    with pytest.raises(RuntimeError, match="reset"):
        env.step(np.zeros(8))
    assert env.data.time == previous_time
    assert samples == previous_samples


def test_preintegration_stop_has_empty_telemetry_and_zero_impulse(monkeypatch):
    env = GroundBodyEnv()
    env.reset(seed=0, pose="supine")
    env.data.qvel[env._joint_dof[0]] = 100.0
    mujoco.mj_forward(env.model, env.data)
    samples = _install_forward_spy(monkeypatch, env)

    result = env.step(np.zeros(8))

    assert result.terminated
    assert result.reason == "joint_speed_limit"
    assert result.diagnostics["executed_substeps"] == 0
    assert result.diagnostics["physics_steps"] == 0
    assert env.data.time == 0.0
    _assert_telemetry(result.diagnostics, samples, env.config.physics_dt)
    assert result.diagnostics["ground_normal_impulse_ns"] == 0.0
    assert result.diagnostics["peak_substep_ground_normal_force"] == 0.0
    assert result.diagnostics["peak_substep_kinetic_energy"] == 0.0
    assert result.diagnostics["minimum_substep_contact_distance"] == 0.0


def test_telemetry_does_not_change_raw_engine_replay_or_joint_guard():
    env = GroundBodyEnv()
    env.reset(seed=8, pose="prone")
    # Exercise the existing joint guard as well as unrestricted commands.
    env.data.qpos[env._joint_qpos[1]] = 0.02
    mujoco.mj_forward(env.model, env.data)
    raw_data = mujoco.MjData(env.model)
    state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
    initial_state = np.empty(mujoco.mj_stateSize(env.model, state_spec))
    mujoco.mj_getState(env.model, env.data, initial_state, state_spec)
    mujoco.mj_setState(env.model, raw_data, initial_state, state_spec)
    mujoco.mj_forward(env.model, raw_data)
    rng = np.random.default_rng(26)
    commands = rng.uniform(-0.15, 0.15, size=(12, 8))
    commands[0, 1] = -0.5
    saw_guard = False

    for command in commands:
        accepted = np.clip(command, -env.action_limits, env.action_limits)
        raw_applied = []
        for _ in range(env.config.control_substeps):
            angles = raw_data.qpos[env._joint_qpos]
            limits = env.model.jnt_range[env._joint_ids]
            blocked = (
                ((angles <= limits[:, 0] + 0.03) & (accepted < 0.0))
                | ((angles >= limits[:, 1] - 0.03) & (accepted > 0.0))
            )
            raw_data.ctrl[:] = np.where(blocked, 0.0, accepted)
            raw_applied.append(raw_data.ctrl.copy())
            saw_guard |= bool(np.any(blocked))
            mujoco.mj_step(env.model, raw_data)
            mujoco.mj_forward(env.model, raw_data)

        result = env.step(command)
        assert not result.terminated
        assert env.data.time == raw_data.time
        np.testing.assert_array_equal(env.data.qpos, raw_data.qpos)
        np.testing.assert_array_equal(env.data.qvel, raw_data.qvel)
        np.testing.assert_array_equal(env.data.sensordata, raw_data.sensordata)
        np.testing.assert_array_equal(
            result.diagnostics["applied_torque_history"], raw_applied
        )

    assert saw_guard


def test_substep_telemetry_stays_out_of_observation_and_changes_no_parameters():
    env = GroundBodyEnv()
    observation = env.reset(seed=3, pose="right_side")
    initial_fingerprint = env.parameter_fingerprint()
    assert set(observation) == NATIVE_OBSERVATIONS
    saved_first_forces = None

    for step_id in range(5):
        result = env.step(np.zeros(8))
        assert not result.terminated
        assert set(result.observation) == NATIVE_OBSERVATIONS
        assert env.parameter_fingerprint() == initial_fingerprint
        if step_id == 0:
            first_forces = result.diagnostics["substep_ground_normal_forces"]
            saved_first_forces = first_forces.copy()

    # Previously returned trace lists must not be reused for the next step.
    assert first_forces == saved_first_forces
