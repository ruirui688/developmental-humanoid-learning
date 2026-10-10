"""Fixed CPU contact-profile scope and provenance checks; no model fitting."""

from __future__ import annotations

import json

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from developmental_physics.environment import (
    ExplorationConfig, GroundBodyEnv, MODEL_PATH,
)


NATIVE_OBSERVATIONS = {
    "joint_position", "joint_velocity", "imu_gyro", "imu_acceleration",
    "actuator_torque", "previous_command",
}


def _numeric_arrays(model):
    arrays = {}
    for name in dir(model):
        if name.startswith("_"):
            continue
        value = getattr(model, name)
        if isinstance(value, np.ndarray) and value.dtype.kind in "biufc":
            arrays[name] = value
    return arrays


def _ground_contacts(env):
    floor_id = env.model.geom("floor").id
    return [
        contact for contact in env.data.contact
        if floor_id in (contact.geom1, contact.geom2)
    ]


def test_default_baseline_model_arrays_and_raw_engine_dynamics_match_asset():
    env = GroundBodyEnv()
    raw_model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    raw_arrays = _numeric_arrays(raw_model)
    assert env.config.ground_contact_profile == "baseline"
    assert set(_numeric_arrays(env.model)) == set(raw_arrays)
    for name, raw_array in raw_arrays.items():
        np.testing.assert_array_equal(getattr(env.model, name), raw_array, err_msg=name)
    assert env.model.opt.timestep == raw_model.opt.timestep
    np.testing.assert_array_equal(env.model.opt.gravity, raw_model.opt.gravity)

    env.reset(seed=4, pose="left_side")
    raw_data = mujoco.MjData(raw_model)
    state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mujoco.mj_stateSize(env.model, state_spec))
    mujoco.mj_getState(env.model, env.data, state, state_spec)
    mujoco.mj_setState(raw_model, raw_data, state, state_spec)
    mujoco.mj_forward(raw_model, raw_data)
    # Replay a short fixed, zero-command prefix across initial landing.
    for _ in range(8):
        for _ in range(env.config.control_substeps):
            raw_data.ctrl[:] = 0.0
            mujoco.mj_step(raw_model, raw_data)
            mujoco.mj_forward(raw_model, raw_data)
        result = env.step(np.zeros(8))
        assert not result.terminated
        assert raw_data.time == env.data.time
        np.testing.assert_array_equal(raw_data.qpos, env.data.qpos)
        np.testing.assert_array_equal(raw_data.qvel, env.data.qvel)
        np.testing.assert_array_equal(raw_data.sensordata, env.data.sensordata)


def test_compliant_profile_changes_only_floor_time_constant_and_priority():
    env = GroundBodyEnv(ExplorationConfig(ground_contact_profile="compliant"))
    raw_model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    floor_id = env.model.geom("floor").id
    for name, raw_array in _numeric_arrays(raw_model).items():
        expected = raw_array.copy()
        if name == "geom_solref":
            expected[floor_id, 0] = 0.05
        elif name == "geom_priority":
            expected[floor_id] = 1
        np.testing.assert_array_equal(getattr(env.model, name), expected, err_msg=name)
    np.testing.assert_array_equal(env.model.geom_solref[floor_id], [0.05, 1.0])
    assert env.model.geom_priority[floor_id] == 1
    # The higher-priority floor must not introduce an additional friction or
    # impedance change from otherwise identical body/floor defaults.
    body_ids = [index for index in range(env.model.ngeom) if index != floor_id]
    for body_id in body_ids:
        assert raw_model.geom_condim[body_id] == raw_model.geom_condim[floor_id]
        assert raw_model.geom_solref[body_id, 1] == raw_model.geom_solref[floor_id, 1]
        if hasattr(raw_model, "geom_solmix"):
            assert raw_model.geom_solmix[body_id] == raw_model.geom_solmix[floor_id]
        np.testing.assert_array_equal(
            raw_model.geom_solimp[body_id], raw_model.geom_solimp[floor_id]
        )
        np.testing.assert_array_equal(
            raw_model.geom_friction[body_id], raw_model.geom_friction[floor_id]
        )


@pytest.mark.parametrize("profile,time_constant", [("baseline", 0.01), ("compliant", 0.05)])
def test_actual_landing_contacts_use_declared_solver_parameters(profile, time_constant):
    env = GroundBodyEnv(ExplorationConfig(ground_contact_profile=profile))
    env.reset(seed=0, pose="supine")
    seen_contacts = 0
    floor_id = env.model.geom("floor").id
    expected_friction = env.model.geom_friction[floor_id][[0, 0, 1, 2, 2]]
    for _ in range(8):
        result = env.step(np.zeros(8))
        assert not result.terminated
        for contact in _ground_contacts(env):
            seen_contacts += 1
            np.testing.assert_array_equal(contact.solref, [time_constant, 1.0])
            assert contact.dim == env.model.geom_condim[floor_id]
            np.testing.assert_array_equal(contact.solimp, env.model.geom_solimp[floor_id])
            np.testing.assert_array_equal(contact.friction, expected_friction)
    assert seen_contacts > 0


def test_effective_self_contact_parameters_do_not_change_between_profiles():
    all_contacts = []
    for profile in ("baseline", "compliant"):
        env = GroundBodyEnv(ExplorationConfig(ground_contact_profile=profile))
        env.reset(seed=0, pose="supine")
        env.data.qpos[2] += 2.0
        # A fixed folded leg creates a body-body contact in the air. No
        # integration or optimization is required to inspect its parameters.
        env.data.qpos[env._joint_qpos[4]] = -1.4
        env.data.qpos[env._joint_qpos[5]] = 2.25
        mujoco.mj_forward(env.model, env.data)
        assert not _ground_contacts(env)
        contacts = []
        for contact in env.data.contact:
            contacts.append({
                "pair": (env.model.geom(contact.geom1).name, env.model.geom(contact.geom2).name),
                "solref": contact.solref.copy(),
                "solimp": contact.solimp.copy(),
                "friction": contact.friction.copy(),
                "condim": int(contact.dim),
                "distance": float(contact.dist),
            })
        assert contacts
        all_contacts.append(contacts)

    assert len(all_contacts[0]) == len(all_contacts[1])
    for baseline, compliant in zip(*all_contacts):
        assert baseline["pair"] == compliant["pair"]
        assert baseline["distance"] == compliant["distance"]
        assert baseline["condim"] == compliant["condim"]
        for field in ("solref", "solimp", "friction"):
            np.testing.assert_array_equal(baseline[field], compliant[field])
        np.testing.assert_array_equal(compliant["solref"], [0.01, 1.0])


@pytest.mark.parametrize("profile", ["", "soft", "Baseline", None, True, 1, []])
def test_unknown_or_nonstring_profiles_are_rejected(profile):
    with pytest.raises(ValueError, match="ground_contact_profile"):
        ExplorationConfig(ground_contact_profile=profile)


@pytest.mark.parametrize("field", ["geom_priority", "geom_solmix", "geom_condim"])
def test_parameter_fingerprint_detects_contact_mixing_parameter_mutations(field):
    env = GroundBodyEnv()
    if not hasattr(env.model, field):
        pytest.skip(f"engine version does not expose {field}")
    before = env.parameter_fingerprint()
    getattr(env.model, field)[env.model.geom("floor").id] += 1
    assert env.parameter_fingerprint() != before


@pytest.mark.parametrize("profile", ["baseline", "compliant"])
def test_contact_metadata_is_actual_serializable_and_a_pure_detached_copy(profile):
    env = GroundBodyEnv(ExplorationConfig(ground_contact_profile=profile))
    env.reset(seed=2, pose="right_side")
    before = env.parameter_fingerprint()
    initial_position = env.data.qpos.copy()
    metadata = env.contact_configuration()
    json.dumps(metadata, allow_nan=False)
    assert metadata["profile"] == profile
    assert metadata["floor"]["name"] == "floor"
    assert metadata["floor"]["priority"] == (0 if profile == "baseline" else 1)
    assert metadata["floor"]["condim"] == 3
    assert metadata["floor"]["solref"] == ([0.01, 1.0] if profile == "baseline" else [0.05, 1.0])
    assert len(metadata["body_geoms"]) == env.model.ngeom - 1
    actual_changes = {(change["name"], change["field"]) for change in metadata["changes_from_asset"]}
    assert actual_changes == (
        set() if profile == "baseline" else {("floor", "solref"), ("floor", "priority")}
    )
    assert metadata["change_scope"]["geometry"] == "floor"

    metadata["floor"]["solref"][0] = 99.0
    metadata["body_geoms"][0]["friction"][0] = 99.0
    for change in metadata["changes_from_asset"]:
        if change["field"] == "solref":
            change["asset"][0] = -1.0
            change["actual"][0] = -1.0
    refreshed = env.contact_configuration()
    assert refreshed["floor"]["solref"][0] == (0.01 if profile == "baseline" else 0.05)
    assert refreshed["body_geoms"][0]["friction"][0] == 0.8
    for change in refreshed["changes_from_asset"]:
        if change["field"] == "solref":
            assert change["asset"] == [0.01, 1.0]
            assert change["actual"] == [0.05, 1.0]
    assert env.parameter_fingerprint() == before
    assert env.data.time == 0.0
    assert env.physics_steps == env.step_id == 0
    np.testing.assert_array_equal(env.data.qpos, initial_position)


@pytest.mark.parametrize("profile", ["baseline", "compliant"])
def test_profile_does_not_leak_into_observation_or_update_parameters(profile):
    env = GroundBodyEnv(ExplorationConfig(ground_contact_profile=profile))
    observation = env.reset(seed=11, pose="prone")
    assert set(observation) == NATIVE_OBSERVATIONS
    original_fingerprint = env.parameter_fingerprint()
    original_contact_configuration = env.contact_configuration()
    for _ in range(8):
        result = env.step(np.zeros(8))
        assert not result.terminated
        assert set(result.observation) == NATIVE_OBSERVATIONS
        assert env.parameter_fingerprint() == original_fingerprint
        assert env.contact_configuration() == original_contact_configuration
