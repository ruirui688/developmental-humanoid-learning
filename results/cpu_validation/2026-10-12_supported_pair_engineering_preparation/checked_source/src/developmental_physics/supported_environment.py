"""W0 fixed-torso support domain; original asset/contact settings and protections remain shared.

The fixed mount is an additional public prior. This wrapper cannot validate the
old free-root domain and supplies no controller, teacher or privileged actor input.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from xml.etree import ElementTree as ET

import mujoco
import numpy as np

from developmental_physics.environment import (
    ExplorationConfig, GroundBodyEnv, JOINT_NAMES, MODEL_PATH,
)

INSTALLATION_SEED = 7300
LEFT_ARM_GEOMS = ("left_upper_arm_geom", "left_forearm_geom")


class SupportedGroundBodyEnv(GroundBodyEnv):
    """One fixed supine installation, with name-based eight-joint coordinates."""

    def __init__(self, config: ExplorationConfig | None = None):
        self.config = config or ExplorationConfig()
        if asdict(self.config) != asdict(ExplorationConfig()):
            raise ValueError("W0_requires_unchanged_baseline_exploration_config")
        self._source_xml = MODEL_PATH.read_bytes()
        tree = ET.fromstring(self._source_xml)
        torso = tree.find("./worldbody/body[@name='torso']")
        roots = list(tree.iter("freejoint"))
        if torso is None or len(roots) != 1 or roots[0].get("name") != "root" or roots[0] not in list(torso):
            raise ValueError("exact_original_torso_root_freejoint_required")
        torso.remove(roots[0])
        quat = np.empty(4)
        mujoco.mju_axisAngle2Quat(quat, np.array([0., 1., 0.]), -np.pi/2)
        torso.set("pos", "0 0 0")
        torso.set("quat", " ".join(repr(float(x)) for x in quat))
        self._derived_xml = ET.tostring(tree, encoding="utf-8")
        self.model = mujoco.MjModel.from_xml_string(self._derived_xml.decode("utf-8"))
        self.model.opt.timestep = self.config.physics_dt
        self.model.actuator_ctrlrange[:] = (-self.config.torque_limit, self.config.torque_limit)
        self._floor_id = self.model.geom("floor").id
        self._torso_id = self.model.body("torso").id
        self._asset_contact_parameters = [
            self._geom_contact_configuration(gid) for gid in range(self.model.ngeom)
        ]
        self.data = mujoco.MjData(self.model)
        self.joint_names = JOINT_NAMES
        self._joint_ids = np.array([self.model.joint(name).id for name in JOINT_NAMES])
        self._joint_qpos = self.model.jnt_qposadr[self._joint_ids].copy()
        self._joint_dof = self.model.jnt_dofadr[self._joint_ids].copy()
        if (self.model.nq, self.model.nv, self.model.nu) != (8, 8, 8):
            raise ValueError("fixed_support_requires_exact_eight_qpos_dof_actuators")
        if (len(set(self._joint_qpos)) != 8 or len(set(self._joint_dof)) != 8
                or [int(self.model.actuator_trnid[i, 0]) for i in range(8)] != self._joint_ids.tolist()):
            raise ValueError("name_based_native_mapping_or_original_motor_order_differs")
        self.action_limits = np.full(8, self.config.torque_limit)
        self.last_command = np.zeros(8)
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None
        self._reset_done = False
        self._installation = None
        self._installed_xml = None
        self._capture_active = False
        self._captured_substeps = []
        self._last_captured_physics_step = 0
        self.last_step_partial = None
        self.engineering_operations = {"model_builds": 1, "reset_calls": 0,
                                       "reset_forward_attempts": 0, "reset_forward_returns": 0}

    def _forward(self):
        self.engineering_operations["reset_forward_attempts"] += 1
        mujoco.mj_forward(self.model, self.data)
        self.engineering_operations["reset_forward_returns"] += 1

    def _lowest_primitive(self):
        lowest = np.inf
        for gid in range(self.model.ngeom):
            if gid == self._floor_id:
                continue
            radius = self.model.geom_size[gid, 0]
            if self.model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_CAPSULE:
                radius += self.model.geom_size[gid, 1] * abs(self.data.geom_xmat[gid].reshape(3, 3)[2, 2])
            lowest = min(lowest, self.data.geom_xpos[gid, 2]-radius)
        if not np.isfinite(lowest):
            raise ValueError("nonfinite_original_primitive_clearance")
        return float(lowest)

    def reset(self, seed=INSTALLATION_SEED, pose="supine"):
        if type(seed) is not int or seed != INSTALLATION_SEED or pose != "supine":
            raise ValueError("W0_only_seed7300_original_supine_installation")
        if self._reset_done:
            raise RuntimeError("W0_single_installation_no_reset_retry")
        self.engineering_operations["reset_calls"] += 1
        mujoco.mj_resetData(self.model, self.data)
        rng = np.random.default_rng(seed)
        q = np.array([0., .12, 0., .12, 0., .12, 0., .12])+rng.uniform(-.015, .015, 8)
        self.data.qpos[self._joint_qpos] = q
        self.data.qvel[:] = 0.
        self.model.body_pos[self._torso_id] = (0., 0., 0.)
        self._forward()
        lowest = self._lowest_primitive()
        self.model.body_pos[self._torso_id, 2] = self.config.reset_clearance-lowest
        self._forward()
        self.last_command[:] = 0.
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None
        self._reset_done = True
        self._installation = {
            "seed": seed, "pose": pose, "rule": "original_supine_primitive_clearance_then_fixed_torso_world_pose",
            "initial_native_q8": q.tolist(), "initial_native_v8": [0.]*8,
            "first_forward_lowest_primitive_z_m": lowest, "reset_clearance_m": self.config.reset_clearance,
            "fixed_torso_world_position": self.data.xpos[self._torso_id].tolist(),
            "fixed_torso_world_quaternion": self.data.xquat[self._torso_id].tolist(),
            "body_pos_model": self.model.body_pos[self._torso_id].tolist(),
            "body_quat_model": self.model.body_quat[self._torso_id].tolist(),
            "mount_adjustments_during_trial": 0, "settling_physics_substeps": 0,
        }
        installed_tree = ET.fromstring(self._derived_xml)
        installed_torso = installed_tree.find("./worldbody/body[@name='torso']")
        installed_torso.set("pos", " ".join(repr(float(x)) for x in self.model.body_pos[self._torso_id]))
        self._installed_xml = ET.tostring(installed_tree, encoding="utf-8")
        return self.observation()

    def support_configuration(self):
        return {
            "domain": "W0_supported_fixed_torso", "support_prior": "torso rigidly fixed to world",
            "source_asset_sha256": hashlib.sha256(self._source_xml).hexdigest(),
            "derived_xml_before_height_assignment_sha256": hashlib.sha256(self._derived_xml).hexdigest(),
            "installed_xml_sha256": hashlib.sha256(self._installed_xml).hexdigest() if self._installed_xml else None,
            "xml_modifications": ["remove root freejoint", "fixed original supine torso pos/quat"],
            "installation": self._installation, "nq": self.model.nq, "nv": self.model.nv, "nu": self.model.nu,
            "njnt": self.model.njnt, "removed_root_qpos": 7, "removed_root_dofs": 6,
            "named_body_weld_ids": [{"body_name": self.model.body(i).name, "body_id": i,
                                     "weld_id": int(self.model.body_weldid[i])} for i in range(self.model.nbody)],
            "compiled_original_comparison_reference": "first W0 --self-check preparation archive; no original model in formal run",
            "joint_names": list(self.joint_names), "joint_ids": self._joint_ids.tolist(),
            "joint_qpos_addresses": self._joint_qpos.tolist(), "joint_dof_addresses": self._joint_dof.tolist(),
            "actuator_joint_ids": self.model.actuator_trnid[:, 0].tolist(),
            "config": asdict(self.config), "contact_configuration": self.contact_configuration(),
            "changed_frame_and_effective_inertia": "fixed torso removes free-base motion and inertial/contact feedback",
            "effective_collision_set": "world-welded torso/head may change static collision filtering; new support domain, not matched causal comparison",
            "old_free_root_C4_validation": False,
        }

    def parameter_fingerprint(self):
        base = super().parameter_fingerprint()
        stable = {"base_physical_arrays": base, "fixed_xml": self._derived_xml.decode("utf-8"),
                  "installed_xml": self._installed_xml.decode("utf-8") if self._installed_xml else None,
                  "installation": self._installation}
        return hashlib.sha256(json.dumps(stable, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()

    def diagnostics(self):
        result = super().diagnostics()
        result["root_position"] = self.data.xpos[self._torso_id].tolist()
        result["root_quaternion"] = self.data.xquat[self._torso_id].tolist()
        result["center_of_mass"] = self.data.subtree_com[self._torso_id].tolist()
        floor_contacts = []
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            if self._floor_id not in (contact.geom1, contact.geom2):
                continue
            force = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, index, force)
            names = [self.model.geom(int(contact.geom1)).name, self.model.geom(int(contact.geom2)).name]
            normal = float(force[0])
            floor_contacts.append({"geom_ids": [int(contact.geom1), int(contact.geom2)],
                                   "geom_names": names, "normal_force_n": normal,
                                   "distance_m": float(contact.dist),
                                   "left_arm": any(name in LEFT_ARM_GEOMS for name in names)})
        result["floor_contacts"] = floor_contacts
        if self._capture_active and self.physics_steps > self._last_captured_physics_step:
            self._last_captured_physics_step = self.physics_steps
            native = {key: value.tolist() for key, value in self.observation().items()}
            self._captured_substeps.append({
                "physics_step": self.physics_steps, "time": float(self.data.time),
                "observation": native, "applied_command8": self.data.ctrl.tolist(),
                "actual_actuator_torque8": self.data.actuator_force.tolist(),
                "floor_contacts": floor_contacts, "diagnostics": result.copy(),
            })
        return result

    def step(self, torque):
        if self._capture_active:
            raise RuntimeError("supported_step_cannot_reenter")
        before = self.physics_steps
        self._captured_substeps = []
        self._last_captured_physics_step = before
        self.last_step_partial = None
        self._capture_active = True
        try:
            result = super().step(torque)
            result.diagnostics["substep_native_and_contact_records"] = self._captured_substeps
            result.diagnostics["fixed_torso_world_prior"] = True
            return result
        except BaseException as exc:
            self.last_step_partial = {
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "confirmed_completed_physics_substeps": self.physics_steps-before,
                "unreturned_integrator_attempts": "unknown_if_integration_exception",
                "substep_native_and_contact_records": self._captured_substeps,
            }
            raise
        finally:
            self._capture_active = False
