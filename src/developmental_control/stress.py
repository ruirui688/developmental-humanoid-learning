"""Fixed-parameter CPU failure-boundary diagnostics, without learning.

Run ``python -m developmental_control.stress --output PATH``. Dynamic delay
selects command[t-delay] from permanent history, and can replay older commands;
this is an explicit diagnostic fixture, not a communication-queue model.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import time
import zipfile

import numpy as np

from .joints import FixedBodyModel, JointParameters, advance
from .maturation import ActionEnvelope, CompetenceGate, GateConfig, GateEvidence
from .planning import CandidatePlanner, PlannerConfig
from .sustained import SustainedCompetenceGate
from .validate import STAGES, ValidationConfig, _git_info, _signature


@dataclass(frozen=True)
class StressScenario:
    name: str
    before: JointParameters = JointParameters()
    after: JointParameters | None = None
    change_step: int | None = None

    def __post_init__(self):
        if not self.name.strip() or not isinstance(self.before, JointParameters):
            raise ValueError("a scenario needs a name and JointParameters")
        if (self.after is None) != (self.change_step is None):
            raise ValueError("after and change_step must be supplied together")
        if self.after is not None and not isinstance(self.after, JointParameters):
            raise ValueError("after must be JointParameters")
        if self.change_step is not None and (type(self.change_step) is not int or self.change_step < 1):
            raise ValueError("change_step must be a positive integer")

    def parameters_at(self, step: int) -> JointParameters:
        return self.after if self.change_step is not None and step >= self.change_step else self.before

    def phase_at(self, step: int) -> str:
        if self.change_step is None:
            return "constant"
        return "pre_change" if step < self.change_step else "post_change"


SCENARIOS = (
    StressScenario("nominal"),
    *(StressScenario(f"constant_delay_{delay}", JointParameters(delay_steps=delay)) for delay in (6, 15, 30)),
    StressScenario("delay_jump_0_to_30_at225", after=JointParameters(delay_steps=30), change_step=225),
    StressScenario("gain_drop_1_to_0.25_at225", after=JointParameters(actuator_gain=(0.25, 0.25)), change_step=225),
    StressScenario("gain_jump_1_to_4_at225", after=JointParameters(actuator_gain=(4.0, 4.0)), change_step=225),
    StressScenario("inertia_jump_x4_at225", after=JointParameters(inertia=(3.2, 4.0)), change_step=225),
)
MODES = ("zero", "pd", "full", "fixed", "competence", "competence_sustained")
GATED_MODES = ("competence", "competence_sustained")
SUSTAINED_FAILURE_WINDOWS = 3


@dataclass(frozen=True)
class StressConfig:
    seeds: tuple[int, ...] = (10, 11, 12)
    rollout_steps: int = 450
    window_steps: int = 25
    fixed_stage_steps: int = 75
    dt: float = 0.02
    target: tuple[float, float] = (0.08, -0.06)
    hard_torque_limits: tuple[float, float] = (1.2, 1.2)
    position_limit: float = 0.35
    speed_limit: float = 1.2
    recovery_speed: float = 0.15

    def __post_init__(self):
        # Share the earlier diagnostic's validation and state-limit definitions.
        ValidationConfig(**asdict(self), evaluation_steps=1)
        ActionEnvelope(self.hard_torque_limits)
        if self.fixed_stage_steps % self.window_steps:
            raise ValueError("fixed stage transitions must align with evidence windows")


class StressPlant:
    """Hidden simulation fixture with state and command history across changes."""

    def __init__(self, scenario: StressScenario, initial_state, dt=0.02):
        self.scenario = scenario
        self.dt = dt
        state = np.asarray(initial_state, dtype=float)
        if state.shape != (4,) or not np.isfinite(state).all():
            raise ValueError("initial_state must contain four finite values")
        self._state = state.copy()
        self.commands: list[np.ndarray] = []
        self.executed_steps = 0
        self.applied_command = np.zeros(2)
        self.effective_torque = np.zeros(2)
        self.applied_command_step: int | None = None
        self.parameters = scenario.before

    @property
    def observation(self):
        return self._state.copy()

    def step(self, command, external_torque=None):
        command = np.asarray(command, dtype=float)
        if command.shape != (2,) or not np.isfinite(command).all():
            raise ValueError("command must contain two finite values")
        step = self.executed_steps
        self.commands.append(command.copy())
        self.parameters = self.scenario.parameters_at(step)
        source = step - self.parameters.delay_steps
        self.applied_command_step = source if source >= 0 else None
        self.applied_command = self.commands[source].copy() if source >= 0 else np.zeros(2)
        self.effective_torque = np.asarray(self.parameters.actuator_gain) * self.applied_command
        self._state = advance(self._state, self.applied_command, self.parameters, self.dt, external_torque)
        self.executed_steps += 1
        return self.observation


def _finite_float(value):
    return float(value) if np.isfinite(value) else None


def _gate_parameters(gate):
    return {"type": type(gate).__name__, "config": asdict(gate.config),
            "stages": [asdict(stage) for stage in gate.stages],
            "failure_windows": getattr(gate, "failure_windows", None)}


def _source_hashes():
    root = Path(__file__).resolve().parents[2]
    return {str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(__file__).parent.glob("*.py"))}


def _window_summary(rows, target, permission, config, gate_config):
    finite = all(row["finite"] for row in rows)
    result = {
        "start_step": rows[0]["command_step"],
        "end_step_exclusive": rows[-1]["step"],
        "completed_steps_at_detection": rows[-1]["step"],
        "decision_effective_command_step": rows[-1]["step"],
        "phase": rows[0]["phase"] if rows[0]["phase"] == rows[-1]["phase"] else "mixed",
        "level": rows[0]["level"], "steps": len(rows),
        "complete": len(rows) == config.window_steps,
        "all_finite": finite, "state_safe": all(row["safe"] for row in rows),
        "gate_observed": False, "failures": [],
    }
    if finite:
        errors = np.array([[row["q0"], row["q1"]] for row in rows]) - target
        active = np.asarray(permission.active_joints)
        tail = rows[-5:]
        tail_error = np.array([[row["q0"], row["q1"]] for row in tail]) - target
        prediction = float(np.sqrt(np.mean([row["prediction_rmse"] ** 2 for row in rows])))
        active_tracking = float(np.sqrt(np.mean(errors[:, active] ** 2)))
        full_tracking = float(np.sqrt(np.mean(errors ** 2)))
        peak_speed = max(max(abs(row["v0"]), abs(row["v1"])) for row in rows)
        residual_max = max(row["prediction_rmse"] for row in rows)
        recovered = bool(np.sqrt(np.mean(tail_error[:, active] ** 2)) <= gate_config.max_tracking_rmse
                         and max(max(abs(row["v0"]), abs(row["v1"])) for row in tail) <= config.recovery_speed)
        safe = bool(result["state_safe"] and not any(row["fallback"] for row in rows))
        evidence = GateEvidence(prediction, active_tracking, peak_speed, residual_max, safe, recovered)
        failures = []
        for failed, name in (
            (not safe, "unsafe_or_planner_fallback"),
            (prediction > gate_config.max_prediction_rmse, "prediction_mismatch"),
            (residual_max > gate_config.max_model_error_bound, "model_uncertainty"),
            (active_tracking > gate_config.max_tracking_rmse, "tracking_failure"),
            (peak_speed > gate_config.max_peak_speed, "speed_failure"),
            (not recovered, "recovery_failure"),
        ):
            if failed:
                failures.append(name)
        result.update(prediction_rmse=prediction, full_target_rmse=full_tracking,
                      active_tracking_rmse=active_tracking, peak_speed=peak_speed,
                      residual_max=residual_max, recovered=recovered, failures=failures)
    else:
        evidence = None
        result.update(prediction_rmse=None, full_target_rmse=None, active_tracking_rmse=None,
                      peak_speed=None, residual_max=None, recovered=False, failures=["nonfinite_state"])
    return result, evidence


def _metrics(rows, dt):
    if not rows:
        return None
    finite = all(row["finite"] for row in rows)
    return {
        "executed_steps": len(rows),
        "full_target_rmse": float(np.sqrt(np.mean([row["full_target_rmse"] ** 2 for row in rows]))) if finite else None,
        "active_tracking_rmse": float(np.sqrt(np.mean([row["active_tracking_rmse"] ** 2 for row in rows]))) if finite else None,
        "prediction_rmse": float(np.sqrt(np.mean([row["prediction_rmse"] ** 2 for row in rows]))) if finite else None,
        "peak_speed": max(max(abs(row["v0"]), abs(row["v1"])) for row in rows) if finite else None,
        "stage_exposure_steps": {str(level): sum(row["level"] == level for row in rows) for level in range(len(STAGES))},
        "active_joint_steps": sum(int(row["active0"]) + int(row["active1"]) for row in rows),
        "permission_limit_joint_seconds": dt * sum(row["limit0"] + row["limit1"] for row in rows),
        "permission_saturated_steps": sum(row["permission_saturated"] for row in rows),
        "hard_command_limit_steps": sum(row["hard_command_limit_reached"] for row in rows),
        "command_limit_violation_steps": sum(row["command_limit_violation"] for row in rows),
        "applied_command_exceeds_current_permission_steps": sum(row["applied_exceeds_current_permission"] for row in rows),
        "applied_command_stage_exposure_steps": {str(level): sum(row["applied_command_level"] == level for row in rows) for level in range(len(STAGES))},
        "initial_zero_history_steps": sum(row["applied_command_level"] is None for row in rows),
        "effective_torque_exceeds_nominal_hard_limit_steps": sum(row["effective_exceeds_nominal_hard_limit"] for row in rows),
        "peak_effective_torque": max(max(abs(row["effective_torque0"]), abs(row["effective_torque1"])) for row in rows),
        "planner_model_transitions": sum(row["planner_model_transitions"] for row in rows),
        "fallback_steps": sum(row["fallback"] for row in rows),
    }


def run_trial(scenario, mode, seed, config, model, planner, envelope):
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")
    rng = np.random.default_rng(seed)
    initial = np.concatenate((rng.uniform(-0.005, 0.005, 2), rng.uniform(-0.003, 0.003, 2)))
    plant = StressPlant(scenario, initial, config.dt)
    gate = (SustainedCompetenceGate(STAGES, GateConfig(), SUSTAINED_FAILURE_WINDOWS)
            if mode == "competence_sustained" else CompetenceGate(STAGES, GateConfig()))
    gate_before = _signature(_gate_parameters(gate))
    previous = np.zeros(2)
    target = np.asarray(config.target)
    scales = np.array([config.position_limit] * 2 + [config.speed_limit] * 2)
    trace, timings, pending, windows, events = [], [], [], [], []
    for step in range(config.rollout_steps):
        if mode in ("zero", "pd", "full"):
            level = len(STAGES) - 1
        elif mode == "fixed":
            level = min(step // config.fixed_stage_steps, len(STAGES) - 1)
        else:
            level = gate.level
        permission = STAGES[level]
        observation = plant.observation
        started = time.perf_counter()
        fallback, candidates = False, None
        if mode == "zero":
            command = np.zeros(2)
        elif mode == "pd":
            nominal = model.parameters
            feedforward = np.asarray(nominal.stiffness) * target + nominal.coupling * (target - target[::-1])
            command = envelope.apply(feedforward + 4.0 * (target - observation[:2]) - 2.0 * observation[2:], permission)
        else:
            plan = planner.plan(observation, target, permission, previous)
            command, fallback, candidates = plan.action, plan.fallback, plan.feasible_candidates
        action_seconds = time.perf_counter() - started
        timings.append(action_seconds)
        disturbance = np.array([0.12, -0.10]) if step % config.window_steps < 2 else np.zeros(2)
        predicted = model.predict(observation, command)
        next_state = plant.step(command, disturbance)
        finite = bool(np.isfinite(next_state).all())
        safe = bool(finite and np.max(np.abs(next_state[:2])) <= config.position_limit
                    and np.max(np.abs(next_state[2:])) <= config.speed_limit)
        limits = np.asarray(permission.torque_limits)
        active = np.asarray(permission.active_joints)
        command_violation = bool(np.any(np.abs(command) > limits + 1e-12)
                                 or np.any(command[~active] != 0)
                                 or np.any(np.abs(command) > np.asarray(config.hard_torque_limits) + 1e-12))
        assert not command_violation, "new command violates its current permission"
        item = {
            "step": step + 1, "command_step": step, "physical_seconds": (step + 1) * config.dt,
            "phase": scenario.phase_at(step), "audit_half": "first225" if step < 225 else "second225",
            "level": level, "permission": permission.name,
            "active0": bool(active[0]), "active1": bool(active[1]),
            "limit0": float(limits[0]), "limit1": float(limits[1]),
            **{f"obs_{name}": _finite_float(value) for name, value in zip(("q0", "q1", "v0", "v1"), observation)},
            **{name: _finite_float(value) for name, value in zip(("q0", "q1", "v0", "v1"), next_state)},
            "command0": float(command[0]), "command1": float(command[1]),
            "applied0": float(plant.applied_command[0]), "applied1": float(plant.applied_command[1]),
            "effective_torque0": float(plant.effective_torque[0]), "effective_torque1": float(plant.effective_torque[1]),
            "applied_command_step": plant.applied_command_step,
            "applied_command_level": (None if plant.applied_command_step is None else
                                      level if plant.applied_command_step == step else trace[plant.applied_command_step]["level"]),
            "true_delay_steps": plant.parameters.delay_steps,
            "true_gain0": plant.parameters.actuator_gain[0], "true_gain1": plant.parameters.actuator_gain[1],
            "true_inertia0": plant.parameters.inertia[0], "true_inertia1": plant.parameters.inertia[1],
            "disturbance0": float(disturbance[0]), "disturbance1": float(disturbance[1]),
            "prediction_rmse": float(np.sqrt(np.mean(((predicted - next_state) / scales) ** 2))) if finite else None,
            "full_target_rmse": float(np.sqrt(np.mean((next_state[:2] - target) ** 2))) if finite else None,
            "active_tracking_rmse": float(np.sqrt(np.mean((next_state[:2][active] - target[active]) ** 2))) if finite else None,
            "finite": finite, "safe": safe, "fallback": fallback, "feasible_candidates": candidates,
            "planner_model_transitions": (planner.config.horizon_steps * planner.config.candidates_per_joint ** int(active.sum())) if mode not in ("zero", "pd") else 0,
            "command_limit_violation": command_violation,
            "permission_saturated": bool(np.any((limits > 0) & (np.abs(command) >= limits - 1e-12))),
            "hard_command_limit_reached": bool(np.any(np.abs(command) >= np.asarray(config.hard_torque_limits) - 1e-12)),
            "applied_exceeds_current_permission": bool(np.any(np.abs(plant.applied_command) > limits + 1e-12)
                                                       or np.any(plant.applied_command[~active] != 0)),
            "effective_exceeds_nominal_hard_limit": bool(np.any(np.abs(plant.effective_torque) > np.asarray(config.hard_torque_limits) + 1e-12)),
            "action_selection_ms": action_seconds * 1000,
        }
        trace.append(item)
        pending.append(item)
        if len(pending) == config.window_steps or not safe or step == config.rollout_steps - 1:
            window, evidence = _window_summary(pending, target, permission, config, gate.config)
            # Independent state safety ends the trial before any gate observation.
            if safe and window["complete"] and mode in GATED_MODES:
                gate.observe(evidence)
                event = {**gate.events[-1],
                         "start_step": window["start_step"], "end_step_exclusive": window["end_step_exclusive"],
                         "decision_effective_command_step": window["decision_effective_command_step"],
                         "phase": window["phase"], "full_target_rmse": window["full_target_rmse"],
                         "failures": window["failures"]}
                events.append(event)
                window.update(gate_observed=True, decision=event["decision"], reason=event["reason"], level_after=gate.level)
            else:
                window.update(decision=None, reason="independent_safety_exit" if not safe else "no_gate", level_after=None)
            windows.append(window)
            pending = []
        if not safe:
            break
        previous = command
    assert _signature(_gate_parameters(gate)) == gate_before, "gate parameters changed"
    metrics = _metrics(trace, config.dt)
    phases = {phase: _metrics([row for row in trace if row["phase"] == phase], config.dt)
              for phase in ("constant", "pre_change", "post_change")}
    failures = [window for window in windows if window["failures"]]
    change = scenario.change_step
    post_failures = [window for window in failures if window["complete"] and change is not None and window["start_step"] >= change]
    first_failure = post_failures[0] if post_failures else None
    post_retreats = [event for event in events if event["decision"] == "retreat"
                    and change is not None and event["start_step"] >= change]
    first_retreat = post_retreats[0] if post_retreats else None
    detection_step = first_failure["completed_steps_at_detection"] if first_failure else None
    retreat_step = first_retreat["decision_effective_command_step"] if first_retreat else None
    pre_change_rows = [row for row in trace if change is not None and row["command_step"] < change]
    changed_rows = [row for row in trace if change is not None and row["command_step"] == change]
    audit_halves = {half: _metrics([row for row in trace if row["audit_half"] == half], config.dt)
                   for half in ("first225", "second225")}
    summary = {
        **metrics,
        "budget_steps": config.rollout_steps, "physical_seconds": plant.executed_steps * config.dt,
        "initial_state": initial.tolist(), "initial_full_target_rmse": float(np.sqrt(np.mean((initial[:2] - target) ** 2))),
        "final_full_target_rmse": trace[-1]["full_target_rmse"],
        "termination_reason": "nonfinite_state" if not trace[-1]["finite"] else ("state_limit" if not trace[-1]["safe"] else "completed"),
        "state_limit_exit": trace[-1]["finite"] and not trace[-1]["safe"],
        "nonfinite_exit": not trace[-1]["finite"],
        "independent_safety_exit_step": trace[-1]["step"] if not trace[-1]["safe"] else None,
        "final_command_level": trace[-1]["level"], "gate_final_level": gate.level if mode in GATED_MODES else None,
        "gate_promotions": sum(event["decision"] == "promote" for event in events),
        "gate_retreats": sum(event["decision"] == "retreat" for event in events),
        "complete_evidence_windows": sum(window["complete"] for window in windows),
        "gate_observed_windows": sum(window["gate_observed"] for window in windows),
        "terminal_partial_window_steps": windows[-1]["steps"] if not windows[-1]["complete"] else 0,
        "failed_windows_at_floor": sum(window["complete"] and bool(window["failures"]) and window["level"] == 0 for window in windows),
        "failure_windows_before_change": sum(bool(window["failures"]) and window["end_step_exclusive"] <= change for window in windows) if change is not None else None,
        "last_pre_change_command_level": pre_change_rows[-1]["level"] if pre_change_rows else None,
        "level_before_change": changed_rows[0]["level"] if changed_rows else None,
        "first_post_change_failure_window": first_failure,
        "first_post_change_failure_observed_step": detection_step,
        "first_post_change_gate_detection_step": detection_step if first_failure and first_failure["gate_observed"] else None,
        "first_post_change_failure_latency_steps": detection_step - change if detection_step is not None else None,
        "first_post_change_retreat_step": retreat_step,
        "first_post_change_retreat_latency_steps": retreat_step - change if retreat_step is not None else None,
        "first_retreat_latency_from_observed_failure_steps": retreat_step - detection_step if retreat_step is not None and detection_step is not None else None,
        "first_post_change_failure_latency_seconds": (detection_step - change) * config.dt if detection_step is not None else None,
        "first_post_change_retreat_latency_seconds": (retreat_step - change) * config.dt if retreat_step is not None else None,
        "action_selection_ms_mean": 1000 * float(np.mean(timings)),
        "action_selection_ms_p95": 1000 * float(np.quantile(timings, 0.95)),
        "action_selection_over_dt_steps": sum(duration > config.dt for duration in timings),
        "gate_parameter_fingerprint_before": gate_before,
        "gate_parameter_fingerprint_after": _signature(_gate_parameters(gate)),
        "phases": phases, "audit_halves": audit_halves, "windows": windows,
    }
    assert summary["executed_steps"] == plant.executed_steps == len(trace)
    return summary, trace, events


def run_stress(config: StressConfig = StressConfig(), scenarios=SCENARIOS, modes=MODES):
    sources_before = _source_hashes()
    if not scenarios or not modes or len(set(modes)) != len(modes):
        raise ValueError("supply scenarios and distinct modes")
    if len({scenario.name for scenario in scenarios}) != len(scenarios):
        raise ValueError("scenario names must be unique")
    for scenario in scenarios:
        if scenario.change_step is not None and (scenario.change_step >= config.rollout_steps
                                                or scenario.change_step % config.window_steps):
            raise ValueError("scenario changes must lie inside the trial on an evidence-window boundary")
    model = FixedBodyModel(dt=config.dt)
    envelope = ActionEnvelope(config.hard_torque_limits)
    planner = CandidatePlanner(model, envelope, PlannerConfig())

    def parameters():
        return {"model": asdict(model), "planner": asdict(planner.config), "gate": asdict(GateConfig()),
                "stages": [asdict(stage) for stage in STAGES], "pd_gains": {"kp": 4.0, "kd": 2.0},
                "sustained_failure_windows": SUSTAINED_FAILURE_WINDOWS, "config": asdict(config),
                "scenarios": [asdict(scenario) for scenario in scenarios], "modes": list(modes)}

    frozen = parameters()
    before = _signature(frozen)
    model_before = model.fingerprint()
    records, all_trace, gates = [], [], []
    started = time.perf_counter()
    for scenario in scenarios:
        for seed in config.seeds:
            for mode in modes:
                summary, trace, events = run_trial(scenario, mode, seed, config, model, planner, envelope)
                context = {"scenario": scenario.name, "seed": seed, "mode": mode}
                records.append({**context, **summary})
                all_trace.extend({**context, **row} for row in trace)
                gates.extend({**context, **event} for event in events)
    after = _signature(parameters())
    assert before == after and model_before == model.fingerprint(), "a fixed parameter changed"
    root = Path(__file__).resolve().parents[2]
    sources = _source_hashes()
    assert sources_before == sources, "source files changed during the diagnostic"
    report = {
        "kind": "cpu_no_training_failure_boundary_diagnostic", "device": "cpu", "gpu": None,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model_parameter_updates": 0, "policy_parameter_updates": 0,
        "fixed_parameters_before": before, "fixed_parameters_after": after,
        "model_fingerprint_before": model_before, "model_fingerprint_after": model.fingerprint(),
        "config": frozen, "git": _git_info(root), "source_sha256": sources,
        "source_files_unchanged": True,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "elapsed_seconds": time.perf_counter() - started,
        "planned_interaction_steps": len(scenarios) * len(config.seeds) * len(modes) * config.rollout_steps,
        "total_executed_steps": len(all_trace),
        "total_planner_model_transitions": sum(row["planner_model_transitions"] for row in all_trace),
        "diagnostic_one_step_model_predictions": len(all_trace), "records": records,
        "limitations": [
            "Stable supported spring/damper fixture; no humanoid balance, gravity instability or contact switching.",
            "Fixed nominal body knowledge, task target, PD gains, planning rules and gate thresholds are disclosed priors.",
            "No parameter fitting, PPO, online adaptation, cold-start acquisition or robot experiment.",
            "Delay selects historical command[t-delay], with zero for negative indices; changing delay may replay older commands.",
            "New commands obey permissions. Old delayed commands may exceed permissions after withdrawal.",
            "Effective actuator torque is gain times delayed command without clipping; nominal command limits are not physical hardware protection.",
            "Gate evidence uses currently active joints; shared full-target error and permission exposure are reported separately.",
            "Observed residual maxima are diagnostics, not calibrated uncertainty bounds.",
            "State-limit and nonfinite exits stop independently before gate observation; a terminal partial window can precede scheduled detection.",
            "Failure-observation latency uses complete windows only; gate-detection latency exists only for gate-observed windows. Terminal partial-window evidence is retained separately.",
            "Latency is completed steps minus zero-index change_step; decisions affect the next command at end_step_exclusive.",
            "Reduced permission, no exit or a gate promotion does not establish task success or learning efficiency.",
            "Timing covers action selection only, excluding simulation, gate aggregation and communication.",
        ],
    }
    return report, all_trace, gates


def write_outputs(output: Path, report, trace, gates):
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "gates.json").write_text(json.dumps(gates, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(trace[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(trace)
    (output / "trace.csv.gz").write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), mtime=0))
    root = Path(__file__).resolve().parents[2]
    with zipfile.ZipFile(output / "source_snapshot.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, expected in report["source_sha256"].items():
            content = (root / relative).read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                raise RuntimeError(f"source changed before snapshot: {relative}")
            entry = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/cpu_validation/stress"))
    args = parser.parse_args()
    report, trace, gates = run_stress()
    write_outputs(args.output, report, trace, gates)
    print(json.dumps({"report": str(args.output / "report.json"), "runs": len(report["records"]),
                      "executed_steps": report["total_executed_steps"], "elapsed_seconds": report["elapsed_seconds"],
                      "model_parameter_updates": 0, "policy_parameter_updates": 0}, indent=2))


if __name__ == "__main__":
    main()
