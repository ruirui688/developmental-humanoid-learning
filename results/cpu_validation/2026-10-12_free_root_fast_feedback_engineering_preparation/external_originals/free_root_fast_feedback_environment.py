"""Draft production path: developmental_physics/free_root_fast_feedback_environment.py.

The free-root asset, reset, observation, integrator and protection remain inherited.
Contact pair telemetry is audit-only, never included in observation or action input.
"""
from dataclasses import asdict
import hashlib

import mujoco
import numpy as np

from developmental_physics.environment import ExplorationConfig, GroundBodyEnv, MODEL_PATH


LEFT_ARM_GEOMS = frozenset(("left_upper_arm_geom", "left_forearm_geom"))
FOOT_GEOMS = frozenset(("left_foot_geom", "right_foot_geom"))


class FreeRootFastFeedbackGroundBodyEnv(GroundBodyEnv):
    """Only construction config substeps differs from the original ground body."""

    def __init__(self, *, audit_cost):
        self.audit_cost = audit_cost
        super().__init__(ExplorationConfig(control_substeps=1))

    def action_interface_configuration(self):
        return {
            "original_baseline_control_dt_s": .02,
            "construction_control_dt_s": self.control_dt,
            "active_control_dt_s": self.control_dt,
            "model_physics_dt_s": self.config.physics_dt,
            "requested_control_substeps": self.config.control_substeps,
            "request_hold_duration_s": self.control_dt,
            "pd_kp": [64., 64.], "pd_kd": [4., 4.],
            "controlled_joint_indices": [0, 1],
            "other_six_requested_torques": "always_zero",
            "actor_inputs": ["native_current_shoulder_elbow_qv", "current_public_target"],
            "contact_pair_telemetry": "audit_only_after_return_not_actor_observation",
            "study_check": "active_only_after_each_complete_returned_2ms_endpoint",
        }

    def physical_configuration_fingerprint(self):
        """Audit physical arrays, separately from config-containing execution hash."""
        self.audit_cost["physical_identity_attempts"] += 1
        data = MODEL_PATH.read_bytes()
        self.audit_cost["physical_asset_read_returns"] += 1
        self.audit_cost["physical_asset_bytes_read"] += len(data)
        digest = hashlib.sha256(data)
        digest.update(mujoco.__version__.encode())
        digest.update(self.action_limits.tobytes())
        for name in (
            "body_mass", "body_inertia", "body_pos", "body_quat", "jnt_range",
            "dof_damping", "dof_armature", "geom_friction", "geom_size",
            "actuator_gainprm", "actuator_biasprm", "actuator_gear",
            "actuator_ctrlrange", "geom_solref", "geom_solimp", "geom_priority", "geom_condim",
        ):
            digest.update(np.asarray(getattr(self.model, name)).tobytes())
        if hasattr(self.model, "geom_solmix"):
            digest.update(np.asarray(self.model.geom_solmix).tobytes())
        digest.update(np.asarray(self.model.opt.gravity).tobytes())
        digest.update(np.asarray([self.model.opt.timestep]).tobytes())
        self.audit_cost["physical_identity_returns"] += 1
        return digest.hexdigest()

    def frozen_metadata(self):
        return {
            "configuration": asdict(self.config),
            "physical_fingerprint": self.physical_configuration_fingerprint(),
            "execution_fingerprint": self.parameter_fingerprint(),
            "action_interface": self.action_interface_configuration(),
            "support": {"root": "original_asset_freejoint", "mount": None,
                        "initial_pose": "supine", "external_support": False},
            "contact_classification": {"left_arm": sorted(LEFT_ARM_GEOMS),
                                       "feet": sorted(FOOT_GEOMS), "other": "all_other_floor_pairs"},
        }

    def audit_floor_pairs(self):
        """Call only at a complete returned 2ms endpoint; no mj_step/forward here."""
        self.audit_cost["audit_contact_snapshot_attempts"] += 1
        try:
            result = self._audit_floor_pairs()
        except BaseException:
            self.audit_cost["audit_contact_snapshot_exceptions"] += 1
            raise
        self.audit_cost["audit_contact_snapshot_returns"] += 1
        return result

    def _audit_floor_pairs(self):
        pairs = []
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            self.audit_cost["audit_contact_pair_inspections"] += 1
            if self._floor_id not in (contact.geom1, contact.geom2):
                continue
            other = int(contact.geom2 if contact.geom1 == self._floor_id else contact.geom1)
            self.audit_cost["audit_geom_name_query_attempts"] += 1
            try:
                name = self.model.geom(other).name
            except BaseException:
                self.audit_cost["audit_geom_name_query_exceptions"] += 1
                raise
            self.audit_cost["audit_geom_name_query_returns"] += 1
            category = "left_arm" if name in LEFT_ARM_GEOMS else "feet" if name in FOOT_GEOMS else "other"
            force = np.zeros(6)
            self.audit_cost["audit_contact_force_query_attempts"] += 1
            try:
                mujoco.mj_contactForce(self.model, self.data, index, force)
            except BaseException:
                self.audit_cost["audit_contact_force_query_exceptions"] += 1
                raise
            self.audit_cost["audit_contact_force_query_returns"] += 1
            distance = float(contact.dist)
            if not np.isfinite(force).all() or not np.isfinite(distance):
                raise ValueError("nonfinite_audit_floor_contact")
            pairs.append({"contact_index": index, "geom1": int(contact.geom1), "geom2": int(contact.geom2),
                          "other_geom_name": name, "category": category,
                          "signed_normal_force_n": float(force[0]),
                          "positive_normal_force_n": max(0., float(force[0])),
                          "contact_frame_force6": force.tolist(), "distance_m": distance})
        result = {"time_s": float(self.data.time), "all_contact_count": int(self.data.ncon),
                  "floor_pairs": pairs, "sampling": "returned_complete_2ms_endpoint",
                  "actor_use": False}
        if not np.isfinite(result["time_s"]):
            raise ValueError("nonfinite_audit_contact_time")
        return result
