"""X fixed-upright torso fixture, reusing frozen W0 substep protection/capture.

The arms are suspended above the retained floor. Contacts are diagnostics,
never an input to the actor; their presence is not an engineering pass gate.
This environment has no controller, learner or body-model fit.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import mujoco
import numpy as np

from developmental_physics.environment import JOINT_NAMES
from developmental_physics.supported_environment import SupportedGroundBodyEnv


INSTALLATION_SEED = 7400
FOOT_GEOMS = ("left_foot_geom", "right_foot_geom")


class SuspendedGroundBodyEnv(SupportedGroundBodyEnv):
    """Fresh, one-reset, upright mount; later protocols may choose other seeds.

    The shared constructor builds its supine model first. We then compile the
    independent identity-quaternion XML, rather than changing a compiled body's
    orientation. Both builds and the otherwise-unused shared build are counted.
    The X0 runner, not this reusable environment, fixes the engineering seed.
    """

    def __init__(self, config=None):
        super().__init__(config)
        self._reset_attempted = False
        tree = ET.fromstring(self._source_xml)
        torso = tree.find("./worldbody/body[@name='torso']")
        roots = list(tree.iter("freejoint"))
        if torso is None or len(roots) != 1 or roots[0].get("name") != "root" or roots[0] not in list(torso):
            raise ValueError("X_exact_original_torso_root_freejoint_required")
        torso.remove(roots[0])
        torso.set("pos", "0 0 0")
        torso.set("quat", "1 0 0 0")
        self._derived_xml = ET.tostring(tree, encoding="utf-8")
        self.engineering_operations["model_builds"] += 1
        self.engineering_operations["shared_supine_constructor_builds"] = 1
        self.engineering_operations["suspended_identity_constructor_builds"] = 1
        self.model = mujoco.MjModel.from_xml_string(self._derived_xml.decode("utf-8"))
        self.model.opt.timestep = self.config.physics_dt
        self.model.actuator_ctrlrange[:] = (-self.config.torque_limit, self.config.torque_limit)
        self._floor_id = self.model.geom("floor").id
        self._torso_id = self.model.body("torso").id
        self._asset_contact_parameters = [
            self._geom_contact_configuration(gid) for gid in range(self.model.ngeom)
        ]
        self.data = mujoco.MjData(self.model)
        self._joint_ids = np.array([self.model.joint(name).id for name in JOINT_NAMES])
        self._joint_qpos = self.model.jnt_qposadr[self._joint_ids].copy()
        self._joint_dof = self.model.jnt_dofadr[self._joint_ids].copy()
        if (self.model.nq, self.model.nv, self.model.nu) != (8, 8, 8):
            raise ValueError("X_fixed_upright_requires_eight_qpos_dof_actuators")
        if (len(set(self._joint_qpos)) != 8 or len(set(self._joint_dof)) != 8
                or [int(self.model.actuator_trnid[i, 0]) for i in range(8)] != self._joint_ids.tolist()):
            raise ValueError("X_named_native_mapping_or_motor_order_differs")
        if not np.array_equal(self.model.body_quat[self._torso_id], np.array([1., 0., 0., 0.])):
            raise ValueError("X_identity_quaternion_must_be_compiled_from_XML")

    def reset(self, seed=INSTALLATION_SEED, pose="upright"):
        if type(seed) is not int or seed < 0 or pose != "upright":
            raise ValueError("X_requires_nonnegative_integer_seed_and_upright_pose")
        if self._reset_attempted:
            raise RuntimeError("X_single_installation_no_reset_retry")
        self._reset_attempted = True
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
            "seed": seed, "pose": pose,
            "rule": "identity_upright_original_primitive_clearance_then_fixed_torso_world_pose",
            "initial_native_q8": q.tolist(), "initial_native_v8": [0.]*8,
            "first_forward_lowest_primitive_z_m": lowest,
            "reset_clearance_m": self.config.reset_clearance,
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
        record = super().support_configuration()
        record.update(
            domain="X_suspended_fixed_upright_torso",
            task_class="noncontact_left_arm_reachability_engineering",
            xml_modifications=["remove root freejoint", "identity upright torso quaternion", "one original 5mm-clearance height assignment"],
            compiled_original_comparison_reference="first X0 assembly self-check; original upright constructed without physics",
            controlled_arm_contact_required=False,
            floor_contact_required=False,
            root_orientation="identity quaternion compiled from the derived XML",
            noncontrolled_joint_semantics="six original passive joints; zero requests, not locked",
            physical_contact_scope="retained floor; observed left_arm/feet/other pairs reported separately",
            fixture_reaction_measurement="unknown; fixed support is not zero support",
        )
        return record

    def diagnostics(self):
        record = super().diagnostics()
        # W0 capture holds references to the same contacts list; adding labels
        # here annotates both endpoint and captured substep diagnostics.
        for contact in record["floor_contacts"]:
            names = contact["geom_names"]
            feet = any(name in FOOT_GEOMS for name in names)
            contact["feet"] = feet
            contact["contact_class"] = "left_arm" if contact["left_arm"] else "feet" if feet else "other"
        record["suspended_fixed_upright_prior"] = True
        return record
