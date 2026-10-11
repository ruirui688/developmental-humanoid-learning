"""Ground-start rigid-body dynamics with bounded torques, without task rewards.

The synthetic morphology and ideal sensors are shared initial conditions. The
wrapper's stop latch is a simulation diagnostic, not a hardware safety system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np


MODEL_PATH = Path(__file__).with_name("assets") / "ground_body.xml"
POSES = ("supine", "prone", "left_side", "right_side")
JOINT_NAMES = (
    "left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
    "left_hip", "left_knee", "right_hip", "right_knee",
)


@dataclass(frozen=True)
class ExplorationConfig:
    physics_dt: float = 0.002
    control_substeps: int = 10
    torque_limit: float = 0.5
    joint_speed_limit: float = 20.0
    joint_limit_margin: float = 0.08
    kinetic_energy_limit: float = 50.0
    reset_clearance: float = 0.005
    ground_contact_profile: str = "baseline"

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name == "ground_contact_profile":
                if not isinstance(value, str) or value not in ("baseline", "compliant"):
                    raise ValueError("ground_contact_profile must be baseline or compliant")
            elif name == "control_substeps":
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError("control_substeps must be a positive integer")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.torque_limit > 0.5:
            raise ValueError("torque_limit cannot exceed the asset's 0.5 N m limit")


@dataclass
class StepResult:
    observation: dict[str, np.ndarray]
    diagnostics: dict[str, object]
    terminated: bool
    reason: str | None


class GroundBodyEnv:
    """No teacher, reference gait, phase clock, target velocity or reward API."""

    def __init__(self, config: ExplorationConfig | None = None):
        self.config = config or ExplorationConfig()
        self.model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
        self.model.opt.timestep = self.config.physics_dt
        self.model.actuator_ctrlrange[:] = (-self.config.torque_limit, self.config.torque_limit)
        self._floor_id = self.model.geom("floor").id
        self._asset_contact_parameters = [
            self._geom_contact_configuration(gid) for gid in range(self.model.ngeom)
        ]
        if self.config.ground_contact_profile == "compliant":
            # Higher floor priority selects these parameters for ground contacts;
            # body-body contact parameters and collision filtering stay untouched.
            self.model.geom_solref[self._floor_id, 0] = 0.05
            self.model.geom_priority[self._floor_id] = 1
        self.data = mujoco.MjData(self.model)
        self.joint_names = JOINT_NAMES
        self._joint_ids = np.array([self.model.joint(name).id for name in JOINT_NAMES])
        self._joint_qpos = self.model.jnt_qposadr[self._joint_ids].copy()
        self._joint_dof = self.model.jnt_dofadr[self._joint_ids].copy()
        self.action_limits = np.full(len(JOINT_NAMES), self.config.torque_limit)
        self.last_command = np.zeros(len(JOINT_NAMES))
        self.step_id = 0
        self.physics_steps = 0
        self.terminated = False
        self.reason: str | None = None
        self._reset_done = False

    @property
    def control_dt(self) -> float:
        return self.config.physics_dt * self.config.control_substeps

    def parameter_fingerprint(self) -> str:
        """Hash configuration and actual physical arrays, never dynamic state."""
        digest = hashlib.sha256(MODEL_PATH.read_bytes())
        digest.update(json.dumps(asdict(self.config), sort_keys=True).encode())
        digest.update(mujoco.__version__.encode())
        digest.update(self.action_limits.tobytes())
        for name in (
            "body_mass", "body_inertia", "body_pos", "body_quat", "jnt_range",
            "dof_damping", "dof_armature", "geom_friction", "geom_size",
            "actuator_gainprm", "actuator_biasprm", "actuator_gear",
            "actuator_ctrlrange", "geom_solref", "geom_solimp", "geom_priority",
            "geom_condim",
        ):
            digest.update(np.asarray(getattr(self.model, name)).tobytes())
        if hasattr(self.model, "geom_solmix"):
            digest.update(np.asarray(self.model.geom_solmix).tobytes())
        digest.update(np.asarray(self.model.opt.gravity).tobytes())
        digest.update(np.asarray([self.model.opt.timestep]).tobytes())
        return digest.hexdigest()

    def _geom_contact_configuration(self, geom_id: int) -> dict[str, object]:
        result = {
            "geom_id": geom_id,
            "name": self.model.geom(geom_id).name,
            "priority": int(self.model.geom_priority[geom_id]),
            "condim": int(self.model.geom_condim[geom_id]),
            "solref": self.model.geom_solref[geom_id].tolist(),
            "solimp": self.model.geom_solimp[geom_id].tolist(),
            "friction": self.model.geom_friction[geom_id].tolist(),
        }
        if hasattr(self.model, "geom_solmix"):
            result["solmix"] = float(self.model.geom_solmix[geom_id])
        return result

    def contact_configuration(self) -> dict[str, object]:
        """Copy actual contact parameters and asset differences for metadata only."""
        geometries = [
            self._geom_contact_configuration(gid) for gid in range(self.model.ngeom)
        ]
        changes = []
        for original, current in zip(self._asset_contact_parameters, geometries):
            for field in ("priority", "condim", "solmix", "solref", "solimp", "friction"):
                if field in current and original[field] != current[field]:
                    original_value = original[field]
                    changes.append({
                        "geom_id": current["geom_id"],
                        "name": current["name"],
                        "field": field,
                        "asset": original_value.copy() if isinstance(original_value, list) else original_value,
                        "actual": current[field].copy() if isinstance(current[field], list) else current[field],
                    })
        return {
            "profile": self.config.ground_contact_profile,
            "floor": geometries[self._floor_id],
            "body_geoms": [
                geom for geom in geometries if geom["geom_id"] != self._floor_id
            ],
            "changes_from_asset": changes,
            "change_scope": {
                "geometry": "floor",
                "fields": [] if self.config.ground_contact_profile == "baseline" else ["solref[0]", "priority"],
                "ground_parameter_selection": (
                    "asset mixing" if self.config.ground_contact_profile == "baseline"
                    else "higher floor priority selects floor contact parameters"
                ),
            },
        }

    def reset(self, seed: int = 0, pose: str = "supine") -> dict[str, np.ndarray]:
        if pose not in POSES:
            raise ValueError(f"pose must be one of {POSES}")
        rng = np.random.default_rng(seed)
        mujoco.mj_resetData(self.model, self.data)
        # Symmetric near-neutral flexion is morphology/reset information, not a gait.
        self.data.qpos[self._joint_qpos] = np.array([0, .12, 0, .12, 0, .12, 0, .12]) + rng.uniform(-.015, .015, 8)
        axis, angle = {
            "supine": ((0., 1., 0.), -np.pi / 2),
            "prone": ((0., 1., 0.), np.pi / 2),
            "left_side": ((1., 0., 0.), -np.pi / 2),
            "right_side": ((1., 0., 0.), np.pi / 2),
        }[pose]
        quat = np.empty(4)
        mujoco.mju_axisAngle2Quat(quat, np.array(axis), angle)
        self.data.qpos[3:7] = quat
        mujoco.mj_forward(self.model, self.data)
        # Place the lowest primitive above the plane; no uncounted settling steps.
        lowest = np.inf
        for gid in range(self.model.ngeom):
            if gid == self._floor_id:
                continue
            radius = self.model.geom_size[gid, 0]
            if self.model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_CAPSULE:
                radius += self.model.geom_size[gid, 1] * abs(self.data.geom_xmat[gid].reshape(3, 3)[2, 2])
            lowest = min(lowest, self.data.geom_xpos[gid, 2] - radius)
        self.data.qpos[2] += self.config.reset_clearance - lowest
        self.last_command[:] = 0
        self.step_id = self.physics_steps = 0
        self.terminated = False
        self.reason = None
        self._reset_done = True
        mujoco.mj_forward(self.model, self.data)
        return self.observation()

    def observation(self) -> dict[str, np.ndarray]:
        """Idealized encoder, IMU and torque feedback; no privileged contact input."""
        return {
            "joint_position": self.data.qpos[self._joint_qpos].copy(),
            "joint_velocity": self.data.qvel[self._joint_dof].copy(),
            "imu_gyro": self.data.sensor("imu_gyro").data.copy(),
            "imu_acceleration": self.data.sensor("imu_acceleration").data.copy(),
            "actuator_torque": self.data.actuator_force.copy(),
            "previous_command": self.last_command.copy(),
        }

    def diagnostics(self) -> dict[str, object]:
        """Simulator truth for audits only; never passed to the exploration actor."""
        ground_contacts = 0
        ground_normal_force = 0.0
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            if self._floor_id in (contact.geom1, contact.geom2):
                ground_contacts += 1
                force = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.data, index, force)
                ground_normal_force += max(0., float(force[0]))
        return {
            "step_id": self.step_id,
            "physics_steps": self.physics_steps,
            "time": float(self.data.time),
            "contact_count": int(self.data.ncon),
            "ground_contact_count": ground_contacts,
            "ground_normal_force": ground_normal_force,
            "root_position": self.data.qpos[:3].tolist(),
            "root_quaternion": self.data.qpos[3:7].tolist(),
            "center_of_mass": self.data.subtree_com[1].tolist(),
            "kinetic_energy": float(self.data.energy[1]),
            "minimum_contact_distance": min((float(c.dist) for c in self.data.contact), default=0.),
        }

    def geometry_snapshot(self) -> list[dict[str, object]]:
        """Physical geometry for offline plotting, not fixed-height skeleton art."""
        result = []
        for gid in range(self.model.ngeom):
            if gid == self._floor_id:
                continue
            center = self.data.geom_xpos[gid]
            half_length = self.model.geom_size[gid, 1]
            axis = self.data.geom_xmat[gid].reshape(3, 3)[:, 2]
            result.append({
                "name": self.model.geom(gid).name,
                "center": center.tolist(),
                "endpoints": [(center - half_length * axis).tolist(), (center + half_length * axis).tolist()],
                "radius": float(self.model.geom_size[gid, 0]),
            })
        return result

    def _stop_reason(self) -> str | None:
        if not all(np.isfinite(x).all() for x in (self.data.qpos, self.data.qvel, self.data.sensordata, self.data.energy)):
            return "nonfinite_state"
        if any(int(w.number) for w in self.data.warning):
            return "solver_warning"
        if np.max(np.abs(self.data.qvel[self._joint_dof])) > self.config.joint_speed_limit:
            return "joint_speed_limit"
        angles = self.data.qpos[self._joint_qpos]
        limits = self.model.jnt_range[self._joint_ids]
        margin = self.config.joint_limit_margin
        if np.any(angles < limits[:, 0] - margin) or np.any(angles > limits[:, 1] + margin):
            return "joint_position_limit"
        if self.data.energy[1] > self.config.kinetic_energy_limit:
            return "kinetic_energy_limit"
        return None

    def step(self, torque: np.ndarray) -> StepResult:
        requested = np.asarray(torque, dtype=float)
        if requested.shape != (len(JOINT_NAMES),) or not np.isfinite(requested).all():
            raise ValueError("torque must be a finite vector of length 8")
        if not self._reset_done:
            raise RuntimeError("reset must be called before step")
        if self.terminated:
            raise RuntimeError("episode stopped; reset is required")
        # Check both before and after integration; stop is latched without reset.
        reason = self._stop_reason()
        accepted = np.clip(requested, -self.action_limits, self.action_limits)
        executed_substeps = 0
        applied_history = []
        guarded_substeps = 0
        substep_ground_forces = []
        substep_energies = []
        substep_contact_distances = []
        if reason is None:
            self.last_command[:] = accepted
            for _ in range(self.config.control_substeps):
                angles = self.data.qpos[self._joint_qpos]
                limits = self.model.jnt_range[self._joint_ids]
                blocked = ((angles <= limits[:, 0] + .03) & (accepted < 0)) | ((angles >= limits[:, 1] - .03) & (accepted > 0))
                self.data.ctrl[:] = np.where(blocked, 0., accepted)
                applied_history.append(self.data.ctrl.tolist())
                guarded_substeps += int(np.any(blocked))
                mujoco.mj_step(self.model, self.data)
                executed_substeps += 1
                self.physics_steps += 1
                # Recompute sensors/contacts at the logged endpoint, not pre-step.
                mujoco.mj_forward(self.model, self.data)
                # Privileged telemetry observes dynamics; it never chooses actions.
                sample = self.diagnostics()
                substep_ground_forces.append(sample["ground_normal_force"])
                substep_energies.append(sample["kinetic_energy"])
                substep_contact_distances.append(sample["minimum_contact_distance"])
                reason = self._stop_reason()
                if reason is not None:
                    break
        self.step_id += 1
        self.reason = reason
        self.terminated = reason is not None
        applied = self.data.ctrl.copy()
        if self.terminated:
            self.data.ctrl[:] = 0
        diagnostics = self.diagnostics()
        diagnostics.update({
            "requested_torque": requested.tolist(),
            "accepted_torque": accepted.tolist(),
            "applied_torque": applied.tolist(),
            "applied_torque_history": applied_history,
            "guarded_substeps": guarded_substeps,
            "substep_ground_normal_forces": substep_ground_forces,
            "substep_kinetic_energies": substep_energies,
            "substep_minimum_contact_distances": substep_contact_distances,
            "peak_substep_ground_normal_force": max(substep_ground_forces, default=0.),
            "ground_normal_impulse_ns": float(sum(substep_ground_forces) * self.config.physics_dt),
            "peak_substep_kinetic_energy": max(substep_energies, default=0.),
            "minimum_substep_contact_distance": min(substep_contact_distances, default=0.),
            "executed_substeps": executed_substeps,
            "terminated": self.terminated,
            "reason": reason,
        })
        return StepResult(self.observation(), diagnostics, self.terminated, reason)
