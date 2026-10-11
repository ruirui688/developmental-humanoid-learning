"""C5 draft channel/event accounting tests with no physical integration."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("mujoco")
if Path(__file__).with_name("perturbed_environment.py").exists():
    spec = importlib.util.spec_from_file_location("c5_env_draft", Path(__file__).with_name("perturbed_environment.py"))
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
else:
    from developmental_physics import perturbed_environment as core


@pytest.fixture
def env(monkeypatch):
    instance = object.__new__(core.PerturbedGroundBodyEnv)
    instance._channel_gains = core._gains(np.ones(8))
    instance._step_in_progress = instance._event_in_progress = False
    instance._reset_done, instance.terminated = True, False
    instance.action_limits = np.ones(8)*.5
    instance.last_command = np.zeros(8)
    instance.physics_steps, instance.step_id = 30, 3
    instance._joint_ids = np.arange(8)
    instance.model = SimpleNamespace(dof_armature=np.ones(14)*.01, jnt_dofadr=np.arange(8)+6)
    instance.data = SimpleNamespace(qpos=np.arange(15, dtype=float), qvel=np.arange(14, dtype=float), time=.06)
    monkeypatch.setattr(instance, "_stop_reason", lambda: None)
    monkeypatch.setattr(core.GroundBodyEnv, "parameter_fingerprint", lambda self: self.model.dof_armature.tobytes().hex())
    monkeypatch.setattr(core.mujoco, "mj_forward", lambda model, data: None)
    return instance


@pytest.mark.parametrize("gain", [1., .5])
def test_channel_scales_after_public_clip_preserves_native_previous_and_actual_history(env, monkeypatch, gain):
    original = np.array([2., -.4]+[0.]*6)
    gains = np.array([gain]*2+[1.]*6)
    env.set_channel_gains(gains)
    received = []
    def paid_backend(self, torque):
        received.append(torque.copy())
        self.last_command[:] = torque
        self.physics_steps += 10
        self.step_id += 1
        return SimpleNamespace(observation={"previous_command": torque.copy(), "actuator_torque": torque.copy()},
            diagnostics={"requested_torque": torque.tolist(), "accepted_torque": torque.tolist(),
                "executed_substeps": 10, "applied_torque_history": [torque.tolist()]*10})
    monkeypatch.setattr(core.GroundBodyEnv, "step", paid_backend)
    result = env.step(original)
    accepted = np.clip(original, -.5, .5)
    np.testing.assert_array_equal(received[0], accepted*gains)
    np.testing.assert_array_equal(result.observation["previous_command"], accepted)
    np.testing.assert_array_equal(result.observation["actuator_torque"], accepted*gains)
    assert result.diagnostics["requested_torque"] == original.tolist()
    assert result.diagnostics["accepted_torque"] == accepted.tolist()
    assert result.diagnostics["applied_torque_history"] == [(accepted*gains).tolist()]*10
    assert (env.physics_steps, env.step_id) == (40, 4)


def test_mid_step_interrupt_keeps_paid_counts_and_original_accepted_history(env, monkeypatch):
    env.set_channel_gains([.5]*8)
    def fail(self, torque):
        self.last_command[:] = torque
        self.physics_steps += 3
        raise KeyboardInterrupt()
    monkeypatch.setattr(core.GroundBodyEnv, "step", fail)
    with pytest.raises(KeyboardInterrupt):
        env.step(np.ones(8)*.4)
    assert env.physics_steps == 33 and env.step_id == 3
    np.testing.assert_array_equal(env.last_command, np.ones(8)*.4)


def test_preexisting_stop_does_not_forge_command_acceptance(env, monkeypatch):
    monkeypatch.setattr(env, "_stop_reason", lambda: "already unsafe")
    env.last_command[:] = .1
    monkeypatch.setattr(core.GroundBodyEnv, "step", lambda self, torque: SimpleNamespace(
        observation={"previous_command": self.last_command.copy()},
        diagnostics={"executed_substeps": 0, "applied_torque_history": []}))
    result = env.step(np.ones(8)*.4)
    np.testing.assert_array_equal(result.observation["previous_command"], np.ones(8)*.1)
    assert env.physics_steps == 30


@pytest.mark.parametrize("gains", [[.5]*7, [0.]*8, [1.1]*8, [float("nan")]*8])
def test_invalid_gain_proposal_cannot_change_published_parameters(env, gains):
    before = env.plant_fingerprint()
    with pytest.raises(ValueError):
        env.set_channel_gains(gains)
    assert env.plant_fingerprint() == before


def test_gain_fingerprint_tracks_wrapper_parameters_and_is_immutable(env):
    before = env.plant_fingerprint()
    base = env.base_model_fingerprint()
    assert env.parameter_fingerprint() == before
    env.set_channel_gains([.5]*8)
    assert env.plant_fingerprint() != before
    assert env.parameter_fingerprint() == env.plant_fingerprint()
    assert env.base_model_fingerprint() == base
    with pytest.raises(ValueError):
        env._channel_gains[0] = 1.


def test_armature_event_maps_native_dofs_without_reset_or_free_steps(env):
    before_q, before_v = env.data.qpos.copy(), env.data.qvel.copy()
    record = env.change_armature((0, 1), (.03, .04))
    assert record["status"] == "applied" and record["dof_indices"] == [6, 7]
    assert record["confirmed_physics_substeps_added"] == 0
    for key in ("qpos", "qvel", "last_command"):
        np.testing.assert_array_equal(record["before"][key], record["after"][key])
    assert record["before"]["time"] == record["after"]["time"] == .06
    assert env.model.dof_armature[6:8].tolist() == [.03, .04]
    np.testing.assert_array_equal(env.data.qpos, before_q)
    np.testing.assert_array_equal(env.data.qvel, before_v)
    assert (env.physics_steps, env.step_id, env.data.time) == (30, 3, .06)


@pytest.mark.parametrize("mutation", ["qvel", "time", "interrupt"])
def test_armature_forward_failure_preserves_parameter_change_without_rollback(env, monkeypatch, mutation):
    def failed_forward(model, data):
        if mutation == "interrupt":
            raise KeyboardInterrupt()
        if mutation == "qvel": data.qvel[0] += 1.
        else: data.time += .002
    monkeypatch.setattr(core.mujoco, "mj_forward", failed_forward)
    with pytest.raises((KeyboardInterrupt, RuntimeError)) as failure:
        env.change_armature((1,), (.04,))
    record = failure.value.parameter_event_record
    assert record["status"] == "failed" and record["parameter_assignment_completed"]
    assert env.model.dof_armature[7] == .04 and record["after_armature"][7] == .04
    assert record["confirmed_physics_substeps_added"] == 0
    assert record["after"]["time"] == env.data.time
    np.testing.assert_array_equal(record["after"]["qvel"], env.data.qvel)
    assert not env._event_in_progress


@pytest.mark.parametrize("indices,values", [([1], [.04]), ((True,), [.04]), ((1, 1), [.04, .04]), ((1,), [-.01])])
def test_invalid_armature_event_is_rejected_before_parameter_mutation(env, indices, values):
    before = env.plant_fingerprint()
    with pytest.raises(ValueError):
        env.change_armature(indices, values)
    assert env.plant_fingerprint() == before


def test_nonidentity_native_joint_ids_and_dofs_are_not_reindexed(env):
    env._joint_ids = np.array([4, 1, 7, 0, 6, 2, 5, 3])
    env.model.jnt_dofadr = np.array([9, 6, 11, 7, 13, 8, 10, 12])
    before = env.model.dof_armature.copy()
    record = env.change_armature((0, 2), (.03, .04))
    assert record["joint_indices"] == [0, 2] and record["dof_indices"] == [13, 12]
    assert env.model.dof_armature[13] == .03 and env.model.dof_armature[12] == .04
    np.testing.assert_array_equal(env.model.dof_armature[:12], before[:12])


def test_forward_primary_exception_survives_after_fingerprint_failure(env, monkeypatch):
    original_fingerprint = env.plant_fingerprint
    primary = RuntimeError("primary forward failure")
    def broken_fingerprint():
        if env.model.dof_armature[7] == .04:
            raise OSError("after diagnostic unavailable")
        return original_fingerprint()
    def forward(model, data):
        data.qvel[0] += .25
        raise primary
    monkeypatch.setattr(env, "plant_fingerprint", broken_fingerprint)
    monkeypatch.setattr(core.mujoco, "mj_forward", forward)
    with pytest.raises(RuntimeError) as raised:
        env.change_armature((1,), (.04,))
    assert raised.value is primary
    record = raised.value.parameter_event_record
    assert record["status"] == "failed" and record["parameter_assignment_completed"]
    assert record["after"]["armature"][7] == .04
    assert record["after"]["qvel"][0] == record["before"]["qvel"][0]+.25
    assert record["error"]["message"] == "primary forward failure"
    assert record["after_diagnostic_errors"]["plant"]["type"] == "OSError"
    assert record["after_plant"] is None and not env._event_in_progress
    assert record["confirmed_physics_substeps_added"] == 0


def test_gain_assignment_then_after_report_failure_keeps_event_fact(env, monkeypatch):
    original = env.plant_fingerprint
    def fingerprint():
        if env._channel_gains[1] == .5:
            raise OSError("gain after report failed")
        return original()
    monkeypatch.setattr(env, "plant_fingerprint", fingerprint)
    with pytest.raises(OSError) as raised:
        env.set_channel_gains([.5]*8)
    record = raised.value.parameter_event_record
    assert record["event_type"] == "channel_gains" and record["status"] == "failed"
    assert record["parameter_assignment_completed"]
    np.testing.assert_array_equal(record["before"]["channel_gains"], np.ones(8))
    np.testing.assert_array_equal(record["after"]["channel_gains"], np.ones(8)*.5)
    assert record["after_diagnostic_errors"]["plant"]["message"] == "gain after report failed"
    assert record["new_physics_substeps"] == 0 and not env._event_in_progress


def test_before_report_failure_does_not_claim_parameter_assignment(env, monkeypatch):
    before = env._channel_gains.copy()
    def fingerprint():
        raise OSError("before record failed")
    monkeypatch.setattr(env, "plant_fingerprint", fingerprint)
    with pytest.raises(OSError) as raised:
        env.set_channel_gains([.5]*8)
    record = raised.value.parameter_event_record
    assert not record["parameter_assignment_completed"] and record["before"] is None
    np.testing.assert_array_equal(env._channel_gains, before)
    assert record["confirmed_physics_substeps_added"] is None
    assert not env._event_in_progress


@pytest.mark.parametrize("event", ["gain", "armature"])
def test_midstep_event_rejected_and_paid_interrupt_preserved(env, monkeypatch, event):
    def backend(self, torque):
        self.last_command[:] = torque
        self.physics_steps += 2
        if event == "gain": self.set_channel_gains([.5]*8)
        else: self.change_armature((1,), (.04,))
    monkeypatch.setattr(core.GroundBodyEnv, "step", backend)
    with pytest.raises(RuntimeError, match="forbidden during step"):
        env.step(np.ones(8)*.4)
    assert env.physics_steps == 32 and env.step_id == 3
    np.testing.assert_array_equal(env.last_command, np.ones(8)*.4)
    np.testing.assert_array_equal(env._channel_gains, np.ones(8))
    assert env.model.dof_armature[7] == .01
    assert not env._step_in_progress and not env._event_in_progress


@pytest.mark.parametrize("nested", ["gain", "armature", "step", "reset"])
def test_event_reentry_rejected_preserves_original_assignment(env, monkeypatch, nested):
    def forward(model, data):
        if nested == "gain": env.set_channel_gains([.5]*8)
        elif nested == "armature": env.change_armature((0,), (.03,))
        elif nested == "step": env.step(np.zeros(8))
        else: env.reset()
    monkeypatch.setattr(core.mujoco, "mj_forward", forward)
    with pytest.raises(RuntimeError) as raised:
        env.change_armature((1,), (.04,))
    record = raised.value.parameter_event_record
    assert record["status"] == "failed" and record["parameter_assignment_completed"]
    assert env.model.dof_armature[7] == .04 and env.model.dof_armature[6] == .01
    np.testing.assert_array_equal(env._channel_gains, np.ones(8))
    assert env.physics_steps == 30 and env.step_id == 3
    assert not env._event_in_progress and not env._step_in_progress


def test_step_reentry_is_rejected_without_losing_command_history(env, monkeypatch):
    def backend(self, torque):
        self.last_command[:] = torque
        return self.step(torque)
    monkeypatch.setattr(core.GroundBodyEnv, "step", backend)
    with pytest.raises(RuntimeError, match="cannot reenter"):
        env.step(np.ones(8)*.4)
    np.testing.assert_array_equal(env.last_command, np.ones(8)*.4)
    assert env.physics_steps == 30 and not env._step_in_progress


def test_reset_preserves_runtime_parameters_and_does_not_silently_restore(env, monkeypatch):
    env.set_channel_gains([.5]*8)
    env.change_armature((1,), (.04,))
    def reset(self, seed=0, pose="supine"):
        self.last_command[:] = 0.
        self.physics_steps = self.step_id = 0
        self.data.time = 0.
        return {"previous_command": self.last_command.copy()}
    monkeypatch.setattr(core.GroundBodyEnv, "reset", reset)
    record = env.reset()
    np.testing.assert_array_equal(env._channel_gains, np.ones(8)*.5)
    assert env.model.dof_armature[7] == .04
    np.testing.assert_array_equal(record["previous_command"], np.zeros(8))
    assert "reset preserves current" in env.parameter_record()["reset_parameter_semantics"]
