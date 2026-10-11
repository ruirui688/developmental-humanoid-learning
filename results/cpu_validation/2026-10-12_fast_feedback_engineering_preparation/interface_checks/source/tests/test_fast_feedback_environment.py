"""New interface fixtures only; no real environment build, forward or step."""
from dataclasses import asdict, replace
from types import SimpleNamespace

import numpy as np
import pytest

from developmental_physics import fast_feedback_environment as interface_module
from developmental_physics.environment import ExplorationConfig
from developmental_physics.fast_feedback_environment import FastFeedbackGroundBodyEnv
from developmental_physics.suspended_environment import SuspendedGroundBodyEnv


@pytest.fixture
def fake_parent(monkeypatch, tmp_path):
    """Replace physical construction; the temporary asset is synthetic XML."""
    constructor_calls = []
    asset = tmp_path / "new_interface_fixture.xml"
    asset.write_bytes(b"<new-interface-fixture/>")
    monkeypatch.setattr(interface_module, "MODEL_PATH", asset)

    def initialize(self, config):
        constructor_calls.append(config)
        self.config = config
        self.model = SimpleNamespace(
            opt=SimpleNamespace(timestep=.002, gravity=np.array([0., 0., -9.81])))
        for index, name in enumerate(interface_module.PHYSICAL_ARRAY_NAMES):
            setattr(self.model, name, np.array([index + .125]))
        self.action_limits = np.full(8, .5)
        self._derived_xml = b"<dummy-fixed-assembly/>"
        self._installed_xml = None
        self._installation = None

    monkeypatch.setattr(SuspendedGroundBodyEnv, "__init__", initialize)
    return SimpleNamespace(constructor_calls=constructor_calls, asset=asset)


@pytest.mark.parametrize("explicit_active_config", (False, True))
def test_new_interface_constructs_baseline_then_changes_only_cadence(
        fake_parent, explicit_active_config):
    baseline = ExplorationConfig()
    active = replace(baseline, control_substeps=1)
    env = FastFeedbackGroundBodyEnv(active if explicit_active_config else None)

    assert fake_parent.constructor_calls == [baseline]
    assert env._construction_config == baseline
    assert env.config == active
    assert [name for name in asdict(baseline)
            if getattr(baseline, name) != getattr(env.config, name)] == ["control_substeps"]
    assert env.control_dt == .002
    assert env.model.opt.timestep == .002
    for index, name in enumerate(interface_module.PHYSICAL_ARRAY_NAMES):
        np.testing.assert_array_equal(getattr(env.model, name), [index + .125])

    metadata = env.action_interface_configuration()
    assert metadata["construction_config"] == asdict(baseline)
    assert metadata["active_config"] == asdict(active)
    assert metadata["changed_configuration_fields"] == ["control_substeps"]
    assert metadata["construction_control_dt_s"] == .02
    assert metadata["active_control_dt_s"] == metadata["model_physics_dt_s"] == .002
    assert metadata["requested_control_substeps"] == 1
    assert metadata["environment_has_task_PD"] is False
    assert metadata["learning_recipe_inherited"] is False
    assert metadata["old_X_Y_qualification_released"] is False
    assert "step" not in FastFeedbackGroundBodyEnv.__dict__


@pytest.mark.parametrize("configuration_case", (
    "baseline", "two_substeps", "changed_physics_dt", "wrong_type",
))
def test_new_interface_rejects_any_unapproved_configuration_before_construction(
        fake_parent, configuration_case):
    baseline = ExplorationConfig()
    active = replace(baseline, control_substeps=1)
    configuration = {
        "baseline": baseline,
        "two_substeps": replace(baseline, control_substeps=2),
        "changed_physics_dt": replace(active, physics_dt=.004),
        "wrong_type": object(),
    }[configuration_case]
    with pytest.raises(ValueError, match="requires_only_control_substeps_1"):
        FastFeedbackGroundBodyEnv(configuration)
    assert fake_parent.constructor_calls == []


def test_new_physical_fingerprint_excludes_cadence_and_full_identity_includes_it(fake_parent):
    env = FastFeedbackGroundBodyEnv()
    physical = env.physical_configuration_fingerprint()
    interface = env.interface_fingerprint()
    combined = env.parameter_fingerprint()

    # Deliberate fixture-only mutation isolates the hash boundary; no step runs.
    env.config = replace(env.config, control_substeps=10)
    assert env.physical_configuration_fingerprint() == physical
    assert env.interface_fingerprint() != interface
    assert env.parameter_fingerprint() != combined

    env.config = replace(env.config, control_substeps=1)
    assert env.physical_configuration_fingerprint() == physical
    assert env.interface_fingerprint() == interface
    assert env.parameter_fingerprint() == combined


@pytest.mark.parametrize("physical_change", ("model_array", "asset_xml", "installation_xml"))
def test_new_physical_fingerprint_binds_actual_arrays_and_xml(fake_parent, physical_change):
    env = FastFeedbackGroundBodyEnv()
    physical = env.physical_configuration_fingerprint()
    interface = env.interface_fingerprint()
    combined = env.parameter_fingerprint()

    if physical_change == "model_array":
        env.model.body_mass[0] += .5
    elif physical_change == "asset_xml":
        fake_parent.asset.write_bytes(b"<new-interface-fixture changed='yes'/>")
    else:
        env._installed_xml = b"<new-installed-fixture/>"
        env._installation = {"fixture": "synthetic"}

    assert env.physical_configuration_fingerprint() != physical
    assert env.interface_fingerprint() == interface
    assert env.parameter_fingerprint() != combined


def test_new_support_metadata_retains_frozen_parent_installation(fake_parent, monkeypatch):
    monkeypatch.setattr(SuspendedGroundBodyEnv, "support_configuration", lambda self: {
        "domain": "synthetic-parent-domain", "frozen_installation_marker": "retained",
    })
    env = FastFeedbackGroundBodyEnv()
    metadata = env.support_configuration()
    assert metadata["domain"] == "Z_fast_feedback_suspended_fixed_upright_torso"
    assert metadata["frozen_installation_marker"] == "retained"
    assert metadata["fast_feedback_interface"] == env.action_interface_configuration()
