"""CPU history/horizon factorial diagnostic with immutable controller priors.

Run ``python -m developmental_control.history --output PATH``. Initial delays
are explicit experiment inputs, never estimated or updated from plant labels.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from .history_planning import HistoryCandidatePlanner, HistoryPlannerConfig
from .joints import FixedBodyModel, JointParameters
from .maturation import ActionEnvelope
from .planning import PlannerConfig
from .stress import StressPlant, StressScenario, _finite_float, _source_hashes, write_outputs
from .validate import STAGES, ValidationConfig, _git_info, _signature


@dataclass(frozen=True)
class HistoryScenario:
    plant: StressScenario
    declared_initial_delay_steps: int = 0

    def __post_init__(self):
        if not isinstance(self.plant, StressScenario):
            raise ValueError("plant must be a StressScenario")
        if type(self.declared_initial_delay_steps) is not int or self.declared_initial_delay_steps < 0:
            raise ValueError("declared delay must be a nonnegative integer")


SCENARIOS = (
    HistoryScenario(StressScenario("nominal")),
    *(HistoryScenario(StressScenario(f"constant_delay_{d}", JointParameters(delay_steps=d)), d)
      for d in (6, 15, 30)),
    HistoryScenario(StressScenario("delay_jump_0_to_30_at225",
                                  after=JointParameters(delay_steps=30), change_step=225)),
    HistoryScenario(StressScenario("delay_jump_15_to_30_at225", JointParameters(delay_steps=15),
                                  JointParameters(delay_steps=30), 225), 15),
    HistoryScenario(StressScenario("gain_drop_1_to_0.25_at225",
                                  after=JointParameters(actuator_gain=(0.25, 0.25)), change_step=225)),
    HistoryScenario(StressScenario("gain_drop_1_to_0.125_at225",
                                  after=JointParameters(actuator_gain=(0.125, 0.125)), change_step=225)),
)


@dataclass(frozen=True)
class ControllerSpec:
    name: str
    horizon_steps: int
    use_history: bool
    kind: str = "planner"

    def __post_init__(self):
        if not self.name or self.kind not in ("planner", "pd") or type(self.use_history) is not bool:
            raise ValueError("invalid controller specification")
        PlannerConfig(horizon_steps=self.horizon_steps)


CONTROLLERS = (
    ControllerSpec("immediate_h20", 20, False),
    ControllerSpec("immediate_h50", 50, False),
    ControllerSpec("history_h20", 20, True),
    ControllerSpec("history_h50", 50, True),
    ControllerSpec("pd", 20, False, "pd"),
)


@dataclass(frozen=True)
class HistoryConfig:
    seeds: tuple[int, ...] = (10, 11, 12)
    rollout_steps: int = 450
    window_steps: int = 25
    dt: float = 0.02
    target: tuple[float, float] = (0.08, -0.06)
    hard_torque_limits: tuple[float, float] = (1.2, 1.2)
    position_limit: float = 0.35
    speed_limit: float = 1.2

    def __post_init__(self):
        ValidationConfig(**asdict(self), evaluation_steps=1)
        ActionEnvelope(self.hard_torque_limits)


def _metrics(rows):
    if not rows:
        return None
    finite = all(row["finite"] for row in rows)
    result = {"executed_steps": len(rows), "fallback_steps": sum(row["fallback"] for row in rows),
              "command_limit_violation_steps": sum(row["command_limit_violation"] for row in rows),
              "planner_model_transitions": sum(row["planner_model_transitions"] for row in rows),
              "effective_torque_exceeds_nominal_hard_limit_steps": sum(row["effective_exceeds_nominal_hard_limit"] for row in rows)}
    for key in ("full_target_rmse", "prediction_rmse", "immediate_prediction_rmse", "applied_label_prediction_rmse"):
        result[key] = float(np.sqrt(np.mean([row[key] ** 2 for row in rows]))) if finite else None
    result["peak_speed"] = max(max(abs(row["v0"]), abs(row["v1"])) for row in rows) if finite else None
    result["peak_effective_torque"] = max(max(abs(row["effective_torque0"]), abs(row["effective_torque1"])) for row in rows)
    return result


def run_trial(scenario, spec, seed, config, model, envelope):
    # Pass only the separately declared immutable prior into the controller.
    history_config = HistoryPlannerConfig(scenario.declared_initial_delay_steps, spec.use_history)
    planner = HistoryCandidatePlanner(model, envelope, PlannerConfig(horizon_steps=spec.horizon_steps), history_config)
    fixed = lambda: {"model": asdict(model), "planner": asdict(planner.config),
                     "history_config": asdict(planner.history_config), "spec": asdict(spec),
                     "permission": asdict(STAGES[-1]), "pd_gains": {"kp": 4.0, "kd": 2.0}}
    before = _signature(fixed())
    rng = np.random.default_rng(seed)
    initial = np.concatenate((rng.uniform(-0.005, 0.005, 2), rng.uniform(-0.003, 0.003, 2)))
    plant = StressPlant(scenario.plant, initial, config.dt)
    permission = STAGES[-1]
    target = np.asarray(config.target)
    scales = np.array([config.position_limit] * 2 + [config.speed_limit] * 2)
    commands, trace, timings = [], [], []
    previous = np.zeros(2)
    for step in range(config.rollout_steps):
        assert len(commands) == step, "issued command history is incomplete"
        observation = plant.observation
        started = time.perf_counter()
        if spec.kind == "pd":
            nominal = model.parameters
            feedforward = np.asarray(nominal.stiffness) * target + nominal.coupling * (target - target[::-1])
            command = envelope.apply(feedforward + 4.0 * (target - observation[:2]) - 2.0 * observation[2:], permission)
            fallback, candidates = False, None
        else:
            plan = planner.plan(observation, target, permission, previous, commands)
            command, fallback, candidates = plan.action, plan.fallback, plan.feasible_candidates
        action_ms = (time.perf_counter() - started) * 1000
        timings.append(action_ms)
        assumed_applied = planner.assumed_applied_action(command, commands)
        predicted = model.predict(observation, assumed_applied)
        immediate_predicted = model.predict(observation, command)
        disturbance = np.array([0.12, -0.10]) if step % config.window_steps < 2 else np.zeros(2)
        next_state = plant.step(command, disturbance)
        # This diagnostic uses a simulation label only AFTER the transition.
        # Neither the label nor its residual is fed into the action generator.
        label_predicted = model.predict(observation, plant.applied_command)
        finite = bool(np.isfinite(next_state).all())
        safe = bool(finite and np.max(np.abs(next_state[:2])) <= config.position_limit
                    and np.max(np.abs(next_state[2:])) <= config.speed_limit)
        limits = np.asarray(permission.torque_limits)
        violation = bool(np.any(np.abs(command) > limits + 1e-12)
                         or np.any(np.abs(command) > np.asarray(config.hard_torque_limits) + 1e-12))
        assert not violation, "new command violates permission"
        residual = lambda prediction: float(np.sqrt(np.mean(((prediction - next_state) / scales) ** 2))) if finite else None
        assumed_delay = history_config.effective_delay_steps
        source = step - assumed_delay
        item = {
            "command_step": step, "step": step + 1, "physical_seconds": (step + 1) * config.dt,
            "issued_history_length": len(commands),
            "phase": scenario.plant.phase_at(step), "audit_half": "first225" if step < 225 else "second225",
            "declared_initial_delay_steps": scenario.declared_initial_delay_steps,
            "assumed_delay_steps": assumed_delay, "horizon_steps": spec.horizon_steps if spec.kind == "planner" else None,
            "candidate_effect_steps": max(0, spec.horizon_steps - assumed_delay) if spec.kind == "planner" else None,
            "assumed_applied_command_step": source if source >= 0 else None,
            "assumed_applied0": float(assumed_applied[0]), "assumed_applied1": float(assumed_applied[1]),
            **{f"obs_{name}": _finite_float(value) for name, value in zip(("q0", "q1", "v0", "v1"), observation)},
            **{name: _finite_float(value) for name, value in zip(("q0", "q1", "v0", "v1"), next_state)},
            **{f"pred_{name}": _finite_float(value) for name, value in zip(("q0", "q1", "v0", "v1"), predicted)},
            "command0": float(command[0]), "command1": float(command[1]),
            "applied0": float(plant.applied_command[0]), "applied1": float(plant.applied_command[1]),
            "effective_torque0": float(plant.effective_torque[0]), "effective_torque1": float(plant.effective_torque[1]),
            "applied_command_step": plant.applied_command_step,
            "true_delay_steps": plant.parameters.delay_steps,
            "true_gain0": plant.parameters.actuator_gain[0], "true_gain1": plant.parameters.actuator_gain[1],
            "true_inertia0": plant.parameters.inertia[0], "true_inertia1": plant.parameters.inertia[1],
            "disturbance0": float(disturbance[0]), "disturbance1": float(disturbance[1]),
            "prediction_rmse": residual(predicted), "immediate_prediction_rmse": residual(immediate_predicted),
            "applied_label_prediction_rmse": residual(label_predicted),
            "full_target_rmse": float(np.sqrt(np.mean((next_state[:2] - target) ** 2))) if finite else None,
            "finite": finite, "safe": safe, "fallback": fallback, "feasible_candidates": candidates,
            "planner_model_transitions": spec.horizon_steps * planner.config.candidates_per_joint ** 2 if spec.kind == "planner" else 0,
            "command_limit_violation": violation,
            "effective_exceeds_nominal_hard_limit": bool(np.any(np.abs(plant.effective_torque) > np.asarray(config.hard_torque_limits) + 1e-12)),
            "action_selection_ms": action_ms,
        }
        trace.append(item)
        commands.append(command.copy())
        if not safe:
            break
        previous = command.copy()
    after = _signature(fixed())
    assert before == after, "controller parameters changed"
    summary = {
        **_metrics(trace), "budget_steps": config.rollout_steps,
        "initial_state": initial.tolist(), "initial_full_target_rmse": float(np.sqrt(np.mean((initial[:2] - target) ** 2))),
        "final_full_target_rmse": trace[-1]["full_target_rmse"],
        "termination_reason": "nonfinite_state" if not trace[-1]["finite"] else ("state_limit" if not trace[-1]["safe"] else "completed"),
        "exit_step": trace[-1]["step"] if not trace[-1]["safe"] else None,
        "exit_seconds": trace[-1]["physical_seconds"] if not trace[-1]["safe"] else None,
        "controller_parameters": fixed(), "fixed_parameters_before": before, "fixed_parameters_after": after,
        "phases": {phase: _metrics([row for row in trace if row["phase"] == phase]) for phase in ("constant", "pre_change", "post_change")},
        "audit_halves": {half: _metrics([row for row in trace if row["audit_half"] == half]) for half in ("first225", "second225")},
        "action_selection_ms": {"median": float(np.median(timings)), "p95": float(np.percentile(timings, 95)),
                                "max": float(max(timings)), "exceeds_dt_steps": sum(value > config.dt * 1000 for value in timings)},
    }
    return summary, trace


def run_history(config=HistoryConfig(), scenarios=SCENARIOS, controllers=CONTROLLERS):
    if not scenarios or not controllers:
        raise ValueError("need nonempty scenarios and controllers")
    if len({s.plant.name for s in scenarios}) != len(scenarios) or len({c.name for c in controllers}) != len(controllers):
        raise ValueError("scenario and controller names must be unique")
    for scenario in scenarios:
        change = scenario.plant.change_step
        if change is not None and (change >= config.rollout_steps or change % config.window_steps):
            raise ValueError("changes must be inside the trial on a disturbance-window boundary")
    root = Path(__file__).resolve().parents[2]
    git_before = _git_info(root)
    sources_before = _source_hashes()
    protocol_path = root / "docs/CPU_HISTORY_PROTOCOL.md"
    protocol_before = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    model = FixedBodyModel(dt=config.dt)
    envelope = ActionEnvelope(config.hard_torque_limits)
    parameters = lambda: {"config": asdict(config), "scenarios": [asdict(s) for s in scenarios],
                          "controllers": [asdict(c) for c in controllers], "model": asdict(model),
                          "base_planner": asdict(PlannerConfig()), "permission": asdict(STAGES[-1]),
                          "pd_gains": {"kp": 4.0, "kd": 2.0}}
    frozen = parameters()
    fingerprint_before = _signature(frozen)
    model_before = model.fingerprint()
    records, all_trace, trial_traces = [], [], {}
    started = time.perf_counter()
    for scenario in scenarios:
        for seed in config.seeds:
            for spec in controllers:
                summary, trace = run_trial(scenario, spec, seed, config, model, envelope)
                context = {"scenario": scenario.plant.name, "seed": seed, "mode": spec.name}
                records.append({**context, **summary})
                all_trace.extend({**context, **row} for row in trace)
                trial_traces[(scenario.plant.name, seed, spec.name)] = trace
    pairs = []
    comparisons = (("immediate_h20", "history_h20"), ("immediate_h50", "history_h50"),
                   ("immediate_h20", "immediate_h50"), ("history_h20", "history_h50"))
    for scenario in scenarios:
        for seed in config.seeds:
            for left, right in comparisons:
                keys = [(scenario.plant.name, seed, mode) for mode in (left, right)]
                if not all(key in trial_traces for key in keys):
                    continue
                a, b = [trial_traces[key] for key in keys]
                count = min(len(a), len(b))
                pairs.append({"scenario": scenario.plant.name, "seed": seed, "left": left, "right": right,
                              "common_executed_steps": count,
                              "left_common_metrics": _metrics(a[:count]), "right_common_metrics": _metrics(b[:count]),
                              "identical_common_state_and_commands": all(
                                  all(x[key] == y[key] for key in ("q0", "q1", "v0", "v1", "command0", "command1"))
                                  for x, y in zip(a[:count], b[:count]))})
    assert fingerprint_before == _signature(parameters()) and model_before == model.fingerprint(), "fixed parameters changed"
    assert sources_before == _source_hashes(), "source files changed during diagnostic"
    assert protocol_before == hashlib.sha256(protocol_path.read_bytes()).hexdigest(), "protocol changed during diagnostic"
    assert git_before == _git_info(root), "git state changed during diagnostic"
    report = {
        "kind": "cpu_no_training_history_horizon_diagnostic", "device": "cpu", "gpu": None,
        "created_utc": datetime.now(timezone.utc).isoformat(), "git": git_before,
        "model_parameter_updates": 0, "policy_parameter_updates": 0, "delay_parameter_updates": 0,
        "model_fingerprint_before": model_before, "model_fingerprint_after": model.fingerprint(),
        "fixed_parameters_before": fingerprint_before, "fixed_parameters_after": _signature(parameters()),
        "source_sha256": sources_before, "source_files_unchanged": True,
        "protocol_sha256": protocol_before, "config": frozen,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "elapsed_seconds": time.perf_counter() - started,
        "planned_interaction_steps": len(scenarios) * len(config.seeds) * len(controllers) * config.rollout_steps,
        "total_executed_steps": len(all_trace),
        "total_planner_model_transitions": sum(row["planner_model_transitions"] for row in all_trace),
        "diagnostic_one_step_model_predictions": 3 * len(all_trace),
        "records": records, "paired_comparisons": pairs,
        "limitations": [
            "Stable supported spring/damper fixture; no humanoid or real robot conclusion.",
            "Declared initial delay is a supplied constant prior, not learned, and is never updated after a plant change.",
            "History/no-history and horizon20/50 form a model ablation, not equal-knowledge learned strategies.",
            "Controllers never receive plant delay, gain, inertia, disturbances or executed-command labels.",
            "Applied-label residual is an after-transition privileged offline diagnostic, never control input.",
            "All new commands use highest fixed permission; no competence gate or permission learning.",
            "Prediction rollout assumes a constant candidate command and omits the external disturbance.",
            "If horizon <= assumed delay, no candidate affects any predicted transition.",
            "Delay uses command[t-delay] with negative indices zero; jumps can replay old commands.",
            "Effective torque is gain times applied command without clipping; command limits are not physical safety protection.",
            "Early exits are retained; full-trajectory and common-prefix metrics differ and are separately reported.",
            "Timing includes action selection only, not simulation, communication or diagnostics.",
            "No fitting, online identification, PPO, or skill acquisition; zero parameter updates.",
        ],
    }
    return report, all_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError(f"refusing to overwrite existing experiment: {args.output}")
    report, trace = run_history()
    write_outputs(args.output, report, trace, [])
    print(json.dumps({"report": str(args.output / "report.json"), "runs": len(report["records"]),
                      "executed_steps": report["total_executed_steps"], "elapsed_seconds": report["elapsed_seconds"],
                      "model_parameter_updates": 0, "policy_parameter_updates": 0, "delay_parameter_updates": 0}, indent=2))


if __name__ == "__main__":
    main()
