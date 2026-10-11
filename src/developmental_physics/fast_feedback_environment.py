"""Z one-substep native-feedback interface over the frozen suspended assembly.

The environment still accepts direct torque requests. Its caller can recompute
the disclosed PD from fresh native q/v every 2 ms; no task controller or learner
is installed here. Construction retains the baseline two-build installation,
then changes only the number of physics substeps in each control call.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json

import mujoco
import numpy as np

from developmental_physics.environment import ExplorationConfig, MODEL_PATH
from developmental_physics.suspended_environment import SuspendedGroundBodyEnv


INTERFACE_NAME = "Z_native_feedback_one_2ms_substep_v1"
PHYSICAL_ARRAY_NAMES = (
    "body_mass", "body_inertia", "body_pos", "body_quat", "jnt_range",
    "dof_damping", "dof_armature", "geom_friction", "geom_size",
    "actuator_gainprm", "actuator_biasprm", "actuator_gear",
    "actuator_ctrlrange", "geom_solref", "geom_solimp", "geom_priority",
    "geom_condim",
)


def _record_fingerprint(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


class FastFeedbackGroundBodyEnv(SuspendedGroundBodyEnv):
    """Same physical installation and protection, one substep per request.

    The frozen supported constructor deliberately rejects changed configs.
    Build through that exact baseline first, then replace the immutable config
    without changing a compiled physical array or the MuJoCo timestep.
    """

    def __init__(self, config: ExplorationConfig | None = None):
        baseline = ExplorationConfig()
        active = replace(baseline, control_substeps=1)
        if config is not None and (
                not isinstance(config, ExplorationConfig) or asdict(config) != asdict(active)):
            raise ValueError("Z_requires_only_control_substeps_1_over_baseline_config")
        super().__init__(baseline)
        self._construction_config = self.config
        self.config = replace(self.config, control_substeps=1)
        if asdict(self.config) != asdict(active):
            raise ValueError("Z_active_configuration_differs_from_fixed_interface")
        if self.control_dt != .002 or float(self.model.opt.timestep) != .002:
            raise ValueError("Z_requires_unchanged_2ms_physics_and_one_substep_control")

    def action_interface_configuration(self):
        """Public cadence/action metadata, separate from physical configuration."""
        return {
            "interface": INTERFACE_NAME,
            "construction_config": asdict(self._construction_config),
            "active_config": asdict(self.config),
            "changed_configuration_fields": ["control_substeps"],
            "construction_control_dt_s": self._construction_config.physics_dt * self._construction_config.control_substeps,
            "active_control_dt_s": self.control_dt,
            "model_physics_dt_s": float(self.model.opt.timestep),
            "requested_control_substeps": self.config.control_substeps,
            "action_units": "eight requested direct motor torques in Nm",
            "request_hold_duration_s": self.control_dt,
            "environment_has_task_PD": False,
            "native_feedback_location": "caller recomputes from each returned native q/v endpoint",
            "execution_source": "unchanged GroundBodyEnv.step range(config.control_substeps)",
            "physical_interface_change": "only control_substeps 10 to 1; compiled model arrays and physics timestep unchanged",
            "protection": "unchanged pre/post physics base stop and per-substep angle guard; study stop belongs to caller",
            "prior_disclosure": "higher native feedback/action cadence; shared PD gains and task capability are caller priors",
            "learning_recipe_inherited": False,
            "old_X_Y_qualification_released": False,
        }

    def interface_fingerprint(self):
        return _record_fingerprint(self.action_interface_configuration())

    def physical_configuration_fingerprint(self):
        """Physical/config/XML identity excluding only control-call subdivision.

        Like the frozen physical hash, this reads the asset once per call and
        hashes actual static model arrays. It performs no build, forward or
        integration, and does not hash evolving native state or diagnostics.
        """
        physical_config = asdict(self.config)
        physical_config.pop("control_substeps")
        digest = hashlib.sha256(MODEL_PATH.read_bytes())
        digest.update(json.dumps(physical_config, sort_keys=True).encode("utf-8"))
        digest.update(mujoco.__version__.encode("utf-8"))
        digest.update(np.asarray(self.action_limits).tobytes())
        for name in PHYSICAL_ARRAY_NAMES:
            digest.update(np.asarray(getattr(self.model, name)).tobytes())
        if hasattr(self.model, "geom_solmix"):
            digest.update(np.asarray(self.model.geom_solmix).tobytes())
        digest.update(np.asarray(self.model.opt.gravity).tobytes())
        digest.update(np.asarray([self.model.opt.timestep]).tobytes())
        digest.update(json.dumps({
            "fixed_xml": self._derived_xml.decode("utf-8"),
            "installed_xml": self._installed_xml.decode("utf-8") if self._installed_xml else None,
            "installation": self._installation,
        }, sort_keys=True, allow_nan=False).encode("utf-8"))
        return digest.hexdigest()

    def parameter_fingerprint(self):
        """Full execution identity binds both physical and control interfaces."""
        return _record_fingerprint({
            "physical_configuration": self.physical_configuration_fingerprint(),
            "control_interface": self.interface_fingerprint(),
        })

    def support_configuration(self):
        record = super().support_configuration()
        record.update(
            domain="Z_fast_feedback_suspended_fixed_upright_torso",
            installation_source="frozen SuspendedGroundBodyEnv upright assembly",
            fast_feedback_interface=self.action_interface_configuration(),
        )
        return record

    def diagnostics(self):
        record = super().diagnostics()
        record.update(native_feedback_control_dt_s=self.control_dt,
                      requested_control_substeps=self.config.control_substeps,
                      fast_feedback_interface_prior=True)
        return record
