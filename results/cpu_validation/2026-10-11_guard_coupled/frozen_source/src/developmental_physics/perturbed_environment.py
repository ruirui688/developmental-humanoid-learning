"""C5 command-channel and armature events; timing belongs to each frozen protocol.

The actor receives native observations. Hidden gain is applied in the command
channel, while the original asset's motor gain and gear remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import time

import mujoco
import numpy as np

from developmental_physics.environment import GroundBodyEnv


def _gains(value):
    array = np.asarray(value, dtype=float)
    if array.shape != (8,) or not np.isfinite(array).all() or np.any(array <= 0.) or np.any(array > 1.):
        raise ValueError("Eight finite hidden channel gains in (0,1] required")
    array = array.copy()
    array.setflags(write=False)
    return array


class PerturbedGroundBodyEnv(GroundBodyEnv):
    """Command scaling preserves accepted-command history and paid steps.

    This wrapper supports only boundary changes; it never schedules an event
    inside step, waits, resets the body or adds uncharged physics steps.
    Fresh construction initializes gains to one and loads asset armature.
    Reset preserves current plant parameters; it never silently undoes events.
    """
    def __init__(self, config=None):
        super().__init__(config)
        self._channel_gains = _gains(np.ones(8))
        self._step_in_progress = False
        self._event_in_progress = False

    def base_model_fingerprint(self):
        return super().parameter_fingerprint()

    def parameter_record(self):
        return {"base_model_fingerprint": self.base_model_fingerprint(),
                "hidden_channel_gains": self._channel_gains.tolist(),
                "reset_parameter_semantics": "reset preserves current gains and runtime armature; fresh environment starts from asset and unit gains",
                "execution_order": "accepted request -> hidden scaling -> current angle guard -> unchanged unit motor"}

    def plant_fingerprint(self):
        return hashlib.sha256(json.dumps(self.parameter_record(), sort_keys=True).encode()).hexdigest()

    def parameter_fingerprint(self):
        """Existing collectors must see both asset/runtime parameters and channel gain."""
        return self.plant_fingerprint()

    def _require_boundary(self):
        if self._step_in_progress:
            raise RuntimeError("parameter event/reset is forbidden during step")
        if self._event_in_progress:
            raise RuntimeError("parameter event/reset cannot reenter an active event")

    def reset(self, seed=0, pose="supine"):
        self._require_boundary()
        return super().reset(seed=seed, pose=pose)

    def _event_snapshot(self, *, best_effort=False):
        getters = {
            "qpos": lambda: self.data.qpos.copy(), "qvel": lambda: self.data.qvel.copy(),
            "time": lambda: float(self.data.time), "physics_steps": lambda: self.physics_steps,
            "step_id": lambda: self.step_id, "last_command": lambda: self.last_command.copy(),
            "armature": lambda: self.model.dof_armature.copy(),
            "channel_gains": lambda: self._channel_gains.copy(),
            "base_model_fingerprint": self.base_model_fingerprint, "plant": self.plant_fingerprint,
        }
        result, errors = {}, {}
        for key, getter in getters.items():
            try:
                result[key] = getter()
            except BaseException as exc:
                if not best_effort:
                    raise
                errors[key] = {"type": type(exc).__name__, "message": str(exc)}
        if errors:
            result["capture_errors"] = errors
        return result

    def _parameter_event(self, record, assign, *, forward=False):
        """One attempted mutation; preserve primary failure and best-effort after facts."""
        self._require_boundary()
        self._event_in_progress = True
        record.update(status="attempted", parameter_assignment_completed=False,
                      before=None, after=None, no_rollback_or_retry=True)
        wall, cpu = time.perf_counter(), time.process_time()
        try:
            record["before"] = self._event_snapshot()
            assign()
            record["parameter_assignment_completed"] = True
            if forward:
                mujoco.mj_forward(self.model, self.data)
            after = self._event_snapshot()
            before = record["before"]
            for key in ("qpos", "qvel", "last_command"):
                if not np.array_equal(before[key], after[key]):
                    raise RuntimeError(f"parameter event changed live {key}")
            if any(before[key] != after[key] for key in ("time", "physics_steps", "step_id")):
                raise RuntimeError("parameter event changed time or paid counters")
            record["after"] = after
            record["status"] = "applied"
        except BaseException as exc:
            record["status"] = "failed"
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            exc.parameter_event_record = record
            raise
        finally:
            # Capture each field independently. A failed fingerprint must not
            # replace the original forward/report exception after assignment.
            try:
                after = self._event_snapshot(best_effort=True)
                record["after"] = after
                record["after_armature"] = after.get("armature")
                record["after_plant"] = after.get("plant")
                record["after_diagnostic_errors"] = after.get("capture_errors", {})
                before = record["before"] or {}
                paid = (after.get("physics_steps")-before["physics_steps"]
                        if "physics_steps" in after and "physics_steps" in before else None)
                record["confirmed_physics_substeps_added"] = paid
                record["new_physics_substeps"] = paid
                record["wall_seconds"] = time.perf_counter()-wall
                record["cpu_seconds"] = time.process_time()-cpu
            finally:
                self._event_in_progress = False
        return record

    def set_channel_gains(self, gains):
        self._require_boundary()
        proposal = _gains(gains)
        return self._parameter_event({"event_type": "channel_gains", "proposal": proposal.tolist()},
                                     lambda: setattr(self, "_channel_gains", proposal))

    def step(self, torque):
        if self._step_in_progress or self._event_in_progress:
            raise RuntimeError("step cannot reenter step or run during a parameter event")
        requested = np.asarray(torque, dtype=float)
        if requested.shape != (8,) or not np.isfinite(requested).all():
            raise ValueError("torque must be a finite vector of length 8")
        if not self._reset_done:
            raise RuntimeError("reset must be called before step")
        if self.terminated:
            raise RuntimeError("episode stopped; reset is required")
        accepted = np.clip(requested, -self.action_limits, self.action_limits)
        scaled = accepted*self._channel_gains
        # Mirror the base environment's public command acceptance condition.
        # Restore semantics even if integration or diagnostics throws midway.
        self._step_in_progress = True
        try:
            will_accept = self._stop_reason() is None
            try:
                result = super().step(scaled)
            finally:
                if will_accept:
                    self.last_command[:] = accepted
            result.observation["previous_command"] = self.last_command.copy()
            result.diagnostics["requested_torque"] = requested.tolist()
            result.diagnostics["accepted_torque"] = accepted.tolist()
            result.diagnostics["hidden_command_transform"] = {
                "accepted_request": accepted.tolist(), "channel_gains": self._channel_gains.tolist(),
                "scaled_before_guard": scaled.tolist(),
                "paid_substeps": result.diagnostics["executed_substeps"],
                "motor_gain_or_gear_changed": False,
                "applied_history_semantics": "actual unit-motor command after hidden scaling and angle guard"}
            return result
        finally:
            self._step_in_progress = False

    def change_armature(self, joint_indices, values):
        """Unvalidated engineering event; any failure is fatal to its caller.

        Armature enters the runtime generalized mass calculation. This draft
        intentionally exposes the applied array even if mj_forward fails;
        it performs no rollback or retry. No physical step is integrated.
        """
        self._require_boundary()
        if type(joint_indices) is not tuple or not joint_indices or len(set(joint_indices)) != len(joint_indices):
            raise ValueError("Nonempty immutable unique joint indices required")
        if any(type(i) is not int or not 0 <= i < 8 for i in joint_indices):
            raise ValueError("Native joint indices 0..7 required")
        proposal = np.asarray(values, dtype=float)
        if proposal.shape != (len(joint_indices),) or not np.isfinite(proposal).all() or np.any(proposal < 0.):
            raise ValueError("Finite nonnegative armature per declared joint required")
        dofs = [int(self.model.jnt_dofadr[self._joint_ids[i]]) for i in joint_indices]
        record = {"event_type": "armature", "joint_indices": list(joint_indices),
                  "dof_indices": dofs, "proposal": proposal.tolist()}
        def assign():
            self.model.dof_armature[dofs] = proposal
        return self._parameter_event(record, assign, forward=True)
