"""Native-signal permissions and deterministic timing for fixed body probes."""

from dataclasses import FrozenInstanceError
import json

import numpy as np
import pytest

from developmental_physics.probes import FixedJointProbe, ProbeConfig, direction_record


def ranges():
    return np.tile([-1., 1.], (8, 1))


@pytest.mark.parametrize("current, expected", [
    (-1.1, 1), (-1., 1), (-.9, 1), (0., 1), (.9, -1), (1., -1), (1.1, -1),
])
def test_direction_uses_public_room_and_handles_endpoints(current, expected):
    position = np.zeros(8)
    position[5] = current
    record = direction_record(5, position, ranges())
    assert record["direction"] == expected
    assert record["positive_room_rad"] == 1. - current
    assert record["negative_room_rad"] == current + 1.
    assert record["joint_index"] == 5


def test_direction_uses_asymmetric_public_limits_not_zero_angle():
    public_ranges = ranges()
    public_ranges[1] = [0., 2.]
    position = np.zeros(8)
    position[1] = .8
    assert direction_record(1, position, public_ranges)["direction"] == 1
    position[1] = 1.2
    assert direction_record(1, position, public_ranges)["direction"] == -1


@pytest.mark.parametrize("joint_index", range(8))
@pytest.mark.parametrize("amplitude", [.125, .25, .5])
def test_full_pulse_timing_and_selected_joint_permission(joint_index, amplitude):
    config = ProbeConfig(joint_index=joint_index, mode="pulse", amplitude_nm=amplitude)
    actor = FixedJointProbe(config, ranges())
    observation = {"joint_position": np.zeros(8)}
    observation["joint_position"][joint_index] = .8
    commands = [actor.act(observation, step) for step in range(config.total_steps)]
    assert config.total_steps == 200
    assert actor.selection_record["selection_step"] == 100
    assert actor.selection_record["direction"] == -1
    command_array = np.asarray(commands)
    assert np.count_nonzero(command_array) == 25
    assert np.all(command_array[:100] == 0)
    assert np.all(command_array[125:] == 0)
    assert np.all(command_array[100:125, joint_index] == -amplitude)
    assert np.all(np.delete(command_array, joint_index, axis=1) == 0)
    assert np.max(np.abs(command_array)) <= .5
    for step in range(200):
        expected_phase = "prefix" if step < 100 else ("probe" if step < 125 else "recovery")
        assert actor.schedule(step) == {
            "phase": expected_phase, "action_index": step - 100 if 100 <= step < 125 else None,
        }


def test_selected_zero_records_same_direction_without_torque():
    observation = {"joint_position": np.full(8, -.8)}
    common = {"joint_index": 3, "prefix_steps": 2, "pulse_steps": 3, "recovery_steps": 1}
    zero = FixedJointProbe(ProbeConfig(mode="zero", **common), ranges())
    pulse = FixedJointProbe(ProbeConfig(mode="pulse", **common), ranges())
    for step in range(6):
        assert np.array_equal(zero.act(observation, step), np.zeros(8))
        pulse.act(observation, step)
    assert zero.selection_record == pulse.selection_record


def test_shared_zero_never_reads_observation_or_selects_direction():
    class NoObservation(dict):
        def __getitem__(self, key):
            raise AssertionError(f"unexpected observation access: {key}")

    actor = FixedJointProbe(ProbeConfig(), ranges())
    for step in range(200):
        assert np.array_equal(actor.act(NoObservation(), step), np.zeros(8))
    assert actor.selection_record is None


def test_direction_freezes_and_only_encoder_field_is_accessed():
    class EncoderOnly(dict):
        def __getitem__(self, key):
            assert key == "joint_position"
            return np.full(8, .8)

    actor = FixedJointProbe(ProbeConfig(0, mode="pulse", prefix_steps=0,
                                       pulse_steps=2, recovery_steps=1), ranges())
    before = actor.parameter_fingerprint()
    assert actor.act(EncoderOnly(), 0)[0] == -.5
    # Later commands must neither read new state nor reverse the chosen direction.
    assert actor.act({}, 1)[0] == -.5
    assert np.array_equal(actor.act({}, 2), np.zeros(8))
    assert actor.parameter_fingerprint() == before
    record = actor.selection_record
    record["direction"] = 1
    assert actor.selection_record["direction"] == -1


def test_spec_copies_parameters_and_fingerprint_excludes_dynamic_selection():
    public_ranges = ranges()
    config = ProbeConfig(2, mode="pulse", prefix_steps=1, pulse_steps=1, recovery_steps=0)
    actor = FixedJointProbe(config, public_ranges)
    copy = FixedJointProbe(config, public_ranges)
    initial_hash = actor.parameter_fingerprint()
    assert initial_hash == copy.parameter_fingerprint()
    public_ranges[:] = [-100., 100.]
    spec = actor.spec()
    json.dumps(spec, allow_nan=False)
    spec["config"]["amplitude_nm"] = 100
    spec["joint_ranges_rad"][0][0] = -100
    assert actor.parameter_fingerprint() == initial_hash
    actor.act({"joint_position": np.zeros(8)}, 0)
    actor.act({"joint_position": np.zeros(8)}, 1)
    assert actor.parameter_fingerprint() == initial_hash
    assert actor.spec()["config"]["amplitude_nm"] == .5
    with pytest.raises(FrozenInstanceError):
        config.amplitude_nm = .25
    changed = FixedJointProbe(ProbeConfig(2, mode="pulse", amplitude_nm=.25), ranges())
    assert changed.parameter_fingerprint() != initial_hash


@pytest.mark.parametrize("kwargs", [
    {"mode": "random"}, {"mode": "pulse"}, {"joint_index": -1}, {"joint_index": 8},
    {"joint_index": True}, {"joint_index": 1.0}, {"amplitude_nm": 1.},
    {"amplitude_nm": .1}, {"amplitude_nm": 0}, {"amplitude_nm": True},
    {"amplitude_nm": np.nan}, {"amplitude_nm": np.inf}, {"amplitude_nm": ".5"},
    {"prefix_steps": -1}, {"prefix_steps": True}, {"prefix_steps": 1.0},
    {"pulse_steps": 0}, {"pulse_steps": -1}, {"pulse_steps": True},
    {"recovery_steps": -1}, {"recovery_steps": .1},
])
def test_invalid_config_rejected(kwargs):
    with pytest.raises(ValueError):
        ProbeConfig(**kwargs)


@pytest.mark.parametrize("public_ranges", [
    [], np.zeros((7, 2)), np.zeros((8, 2)), np.tile([1., -1.], (8, 1)),
    np.full((8, 2), np.nan), np.full((8, 2), np.inf), "invalid",
])
def test_invalid_public_ranges_rejected(public_ranges):
    with pytest.raises(ValueError):
        FixedJointProbe(ProbeConfig(), public_ranges)


@pytest.mark.parametrize("position", [np.zeros(7), np.full(8, np.nan), np.full(8, np.inf)])
def test_invalid_encoders_rejected(position):
    with pytest.raises(ValueError):
        direction_record(0, position, ranges())


@pytest.mark.parametrize("step", [-1, 200, True, 1.0])
def test_invalid_schedule_steps_rejected(step):
    with pytest.raises(ValueError):
        FixedJointProbe(ProbeConfig(), ranges()).act({}, step)


def test_missed_direction_selection_rejected_instead_of_using_late_encoders():
    actor = FixedJointProbe(ProbeConfig(0, mode="pulse"), ranges())
    with pytest.raises(RuntimeError, match="prefix endpoint"):
        actor.act({"joint_position": np.zeros(8)}, 101)
