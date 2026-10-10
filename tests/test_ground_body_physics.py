"""Physical and safety invariants for the optional CPU ground-body environment.

These tests exercise a fixed model.  They fit no parameters and do not judge
random exploration as acquired motor skill.
"""

from __future__ import annotations

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from developmental_physics.environment import ExplorationConfig, GroundBodyEnv
from developmental_physics.exploration import SmoothRandomExplorer


OBSERVATION_SHAPES = {
    "joint_position": (8,),
    "joint_velocity": (8,),
    "imu_gyro": (3,),
    "imu_acceleration": (3,),
    "actuator_torque": (8,),
    "previous_command": (8,),
}


def _root_position_address(env: GroundBodyEnv) -> int:
    free_joints = np.flatnonzero(env.model.jnt_type == mujoco.mjtJoint.mjJNT_FREE)
    assert free_joints.size == 1
    return int(env.model.jnt_qposadr[free_joints[0]])


def _put_in_air(env: GroundBodyEnv) -> None:
    address = _root_position_address(env)
    env.data.qpos[address + 2] += 2.0
    env.data.qvel[:] = 0.0
    mujoco.mj_forward(env.model, env.data)
    assert env.data.ncon == 0


def _center_of_mass(env: GroundBodyEnv) -> np.ndarray:
    masses = env.model.body_mass
    return np.sum(masses[:, None] * env.data.xipos, axis=0) / np.sum(masses)


def _linear_momentum(env: GroundBodyEnv) -> np.ndarray:
    """Sum mass times COM velocity, independently of environment diagnostics."""
    momentum = np.zeros(3)
    linear_jacobian = np.zeros((3, env.model.nv))
    angular_jacobian = np.zeros_like(linear_jacobian)
    for body_id in range(1, env.model.nbody):
        mujoco.mj_jacBodyCom(
            env.model, env.data, linear_jacobian, angular_jacobian, body_id
        )
        momentum += env.model.body_mass[body_id] * (
            linear_jacobian @ env.data.qvel
        )
    return momentum


def _state(env: GroundBodyEnv) -> tuple:
    return (
        (
            float(env.data.time), env.step_id, env.physics_steps,
            env.terminated, env.reason,
        ),
        env.data.qpos.copy(),
        env.data.qvel.copy(),
        env.data.ctrl.copy(),
        env.last_command.copy(),
    )


def _assert_state_equal(first: tuple, second: tuple) -> None:
    assert first[0] == second[0]
    for first_array, second_array in zip(first[1:], second[1:]):
        np.testing.assert_array_equal(first_array, second_array)


@pytest.mark.parametrize("pose", ["supine", "prone", "left_side", "right_side"])
def test_ground_start_has_native_observations_and_no_deep_penetration(pose):
    env = GroundBodyEnv()
    observation = env.reset(seed=7, pose=pose)

    assert len(env.joint_names) == len(set(env.joint_names)) == 8
    assert set(observation) == set(OBSERVATION_SHAPES)
    for key, shape in OBSERVATION_SHAPES.items():
        assert observation[key].shape == shape
        assert np.all(np.isfinite(observation[key]))
    np.testing.assert_array_equal(observation["previous_command"], np.zeros(8))
    assert env.data.time == 0.0
    assert env.data.qpos[_root_position_address(env) + 2] < 0.6
    for contact_id in range(env.data.ncon):
        assert env.data.contact[contact_id].dist >= -1e-4


def test_four_reset_poses_are_distinct_not_near_upright_aliases():
    env = GroundBodyEnv()
    address = _root_position_address(env)
    rotations = []
    for pose in ("supine", "prone", "left_side", "right_side"):
        env.reset(seed=0, pose=pose)
        rotations.append(env.data.qpos[address + 3 : address + 7].copy())
    for index, rotation in enumerate(rotations):
        for other in rotations[index + 1 :]:
            assert abs(np.dot(rotation, other)) < 0.99


def test_zero_command_in_air_follows_gravity():
    env = GroundBodyEnv()
    env.reset(seed=0, pose="supine")
    _put_in_air(env)
    initial_com = _center_of_mass(env)

    for _ in range(5):
        result = env.step(np.zeros(8))
        assert not result.terminated
        assert result.diagnostics["ground_contact_count"] == 0

    elapsed = env.data.time
    final_com = _center_of_mass(env)
    assert final_com[2] < initial_com[2] - 0.02
    # The articulated body may rotate internally; its total COM remains ballistic.
    np.testing.assert_allclose(
        final_com[:2], initial_com[:2], atol=1e-6, rtol=0
    )
    expected_drop = 0.5 * env.model.opt.gravity[2] * elapsed**2
    assert final_com[2] - initial_com[2] == pytest.approx(expected_drop, abs=0.002)


def test_no_gravity_and_zero_command_cannot_create_motion():
    env = GroundBodyEnv()
    env.reset(seed=0, pose="supine")
    _put_in_air(env)
    env.model.opt.gravity[:] = 0.0
    mujoco.mj_forward(env.model, env.data)
    initial_position = env.data.qpos.copy()

    for _ in range(20):
        result = env.step(np.zeros(8))
        assert not result.terminated
        assert result.diagnostics["contact_count"] == 0

    np.testing.assert_allclose(env.data.qpos, initial_position, atol=1e-10, rtol=0)
    np.testing.assert_allclose(env.data.qvel, 0.0, atol=1e-10, rtol=0)


def test_ground_contact_is_resolved_and_exerts_normal_force():
    env = GroundBodyEnv()
    env.reset(seed=0, pose="supine")
    ground_contacts = []
    ground_forces = []
    for _ in range(30):
        result = env.step(np.zeros(8))
        assert not result.terminated
        ground_contacts.append(result.diagnostics["ground_contact_count"])
        ground_forces.append(result.diagnostics["ground_normal_force"])

    assert max(ground_contacts) > 0
    assert max(ground_forces) > 0.0
    assert np.all(np.isfinite(ground_forces))
    assert min(ground_forces) >= 0.0


def test_single_joint_pulse_moves_joint_without_external_horizontal_momentum():
    momentum_errors = []
    # Hold physical time and command fixed while halving the integrator step.
    # Articulated-coordinate integration has a small finite-step COM defect;
    # requiring convergence distinguishes it from an artificial propulsion term.
    for physics_dt, control_substeps in ((0.002, 10), (0.001, 20)):
        env = GroundBodyEnv(ExplorationConfig(
            physics_dt=physics_dt, control_substeps=control_substeps
        ))
        env.reset(seed=0, pose="supine")
        _put_in_air(env)
        env.model.opt.gravity[:] = 0.0
        mujoco.mj_forward(env.model, env.data)
        initial_joints = env.data.qpos[env._joint_qpos].copy()
        initial_com = _center_of_mass(env)
        initial_momentum = _linear_momentum(env)
        command = np.zeros(8)
        command[0] = min(0.25, float(env.action_limits[0]))

        for _ in range(10):
            result = env.step(command)
            assert not result.terminated
            assert result.diagnostics["contact_count"] == 0

        assert abs(env.data.qpos[env._joint_qpos[0]] - initial_joints[0]) > 1e-4
        momentum_error = float(np.max(np.abs(
            _linear_momentum(env)[:2] - initial_momentum[:2]
        )))
        assert momentum_error < 5e-4
        momentum_errors.append(momentum_error)
        np.testing.assert_allclose(
            _center_of_mass(env)[:2], initial_com[:2], atol=2e-5, rtol=0
        )

    assert momentum_errors[1] <= max(0.6 * momentum_errors[0], 1e-10)


@pytest.mark.parametrize(
    "command",
    [np.zeros(7), np.zeros((8, 1)), np.full(8, np.nan), np.full(8, np.inf)],
)
def test_invalid_command_does_not_advance_physics_or_command_state(command):
    env = GroundBodyEnv()
    env.reset(seed=0, pose="prone")
    previous = _state(env)
    with pytest.raises(ValueError):
        env.step(command)
    _assert_state_equal(previous, _state(env))


def test_torque_command_is_clipped_to_declared_action_limits():
    env = GroundBodyEnv()
    env.reset(seed=0, pose="supine")
    _put_in_air(env)
    env.step(np.linspace(-100.0, 100.0, 8))
    assert np.all(np.abs(env.last_command) <= env.action_limits)
    np.testing.assert_array_equal(env.data.ctrl, env.last_command)


def test_speed_safety_stop_is_latched_until_explicit_reset():
    env = GroundBodyEnv()
    env.reset(seed=0, pose="supine")
    env.data.qvel[env._joint_dof[0]] = 100.0
    mujoco.mj_forward(env.model, env.data)

    stopped = env.step(np.zeros(8))
    assert stopped.terminated
    assert stopped.reason == "joint_speed_limit"
    stopped_state = _state(env)
    with pytest.raises(RuntimeError, match="reset"):
        env.step(np.ones(8))
    _assert_state_equal(stopped_state, _state(env))
    np.testing.assert_array_equal(env.data.ctrl, np.zeros(8))

    env.reset(seed=0, pose="supine")
    assert not env.step(np.zeros(8)).terminated


def test_seeded_reset_and_smooth_random_exploration_are_reproducible_and_bounded():
    first, second = GroundBodyEnv(), GroundBodyEnv()
    first_observation = first.reset(seed=41, pose="left_side")
    second_observation = second.reset(seed=41, pose="left_side")
    first_explorer = SmoothRandomExplorer(first.action_limits, seed=73)
    second_explorer = SmoothRandomExplorer(second.action_limits, seed=73)
    commands = []

    for _ in range(20):
        first_command = first_explorer.act(first_observation)
        second_command = second_explorer.act(second_observation)
        assert first_command.shape == (8,)
        assert np.all(np.isfinite(first_command))
        assert np.all(np.abs(first_command) <= first.action_limits)
        np.testing.assert_array_equal(first_command, second_command)
        commands.append(first_command.copy())
        first_result = first.step(first_command)
        second_result = second.step(second_command)
        assert first_result.terminated == second_result.terminated
        np.testing.assert_array_equal(first.data.qpos, second.data.qpos)
        np.testing.assert_array_equal(first.data.qvel, second.data.qvel)
        first_observation = first_result.observation
        second_observation = second_result.observation

    assert np.max(np.abs(commands)) > 0.0


def test_fixed_model_and_controller_parameters_do_not_update_during_exploration():
    env = GroundBodyEnv(ExplorationConfig())
    observation = env.reset(seed=3, pose="prone")
    explorer = SmoothRandomExplorer(env.action_limits, seed=3)
    initial_fingerprint = env.parameter_fingerprint()
    explorer_fingerprint = explorer.parameter_fingerprint()
    assert isinstance(initial_fingerprint, str)
    assert initial_fingerprint

    for _ in range(25):
        result = env.step(explorer.act(observation))
        assert env.parameter_fingerprint() == initial_fingerprint
        assert explorer.parameter_fingerprint() == explorer_fingerprint
        observation = result.observation
