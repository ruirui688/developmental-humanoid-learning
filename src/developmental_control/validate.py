"""Bounded CPU mechanism checks, with zero fitting or policy/model updates.

Run: python -m developmental_control.validate --output results/cpu_validation
The report distinguishes command limits, state-limit exits and control quality.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np

from .joints import FixedBodyModel, JointParameters, JointPlant
from .maturation import ActionEnvelope, CompetenceGate, GateConfig, GateEvidence, StagePermission
from .planning import CandidatePlanner, PlannerConfig


STAGES = (
    StagePermission("one_joint", (True, False), (0.4, 0.0)),
    StagePermission("two_joints", (True, True), (0.7, 0.7)),
    StagePermission("expanded", (True, True), (1.0, 1.0)),
)
SCENARIOS = {
    "nominal_match_diagnostic": JointParameters(),
    "inertia_mismatch": JointParameters(inertia=(1.6, 2.0)),
    "unmodeled_delay": JointParameters(delay_steps=6),
}
MODES = ("zero", "pd", "full", "fixed", "competence")


@dataclass(frozen=True)
class ValidationConfig:
    seeds: tuple[int, ...] = (0, 1, 2)
    rollout_steps: int = 225
    evaluation_steps: int = 100
    window_steps: int = 25
    fixed_stage_steps: int = 75
    dt: float = 0.02
    target: tuple[float, float] = (0.08, -0.06)
    hard_torque_limits: tuple[float, float] = (1.2, 1.2)
    position_limit: float = 0.35
    speed_limit: float = 1.2
    recovery_speed: float = 0.15

    def __post_init__(self):
        if not isinstance(self.seeds, tuple) or not self.seeds or any(type(s) is not int or s < 0 for s in self.seeds):
            raise ValueError("seeds must be a nonempty tuple of nonnegative integers")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("duplicate seeds are not independent replicates")
        for name in ("rollout_steps", "evaluation_steps", "window_steps", "fixed_stage_steps"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.rollout_steps % self.window_steps:
            raise ValueError("rollout_steps must contain complete evidence windows")
        if len(self.target) != 2 or not np.isfinite(self.target).all():
            raise ValueError("target must contain two finite values")
        for name in ("dt", "position_limit", "speed_limit", "recovery_speed"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


def _signature(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _git_info(root: Path):
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip()
        return {"commit": commit, "dirty": bool(status), "status": status}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "status": "unavailable"}


def _run_phase(parameters, mode, seed, config, model, planner, envelope, common_evaluation=False):
    rng = np.random.default_rng(seed + (10_000 if common_evaluation else 0))
    initial = np.concatenate((rng.uniform(-0.005, 0.005, 2), rng.uniform(-0.003, 0.003, 2)))
    plant = JointPlant(parameters, initial, config.dt)
    gate = CompetenceGate(STAGES, GateConfig())
    previous = np.zeros(2)
    target = np.asarray(config.target)
    state_scales = np.array([config.position_limit] * 2 + [config.speed_limit] * 2)
    steps = config.evaluation_steps if common_evaluation else config.rollout_steps
    trace, timings, window = [], [], []
    for step in range(steps):
        if common_evaluation or mode in ("zero", "pd", "full"):
            level = len(STAGES) - 1
        elif mode == "fixed":
            level = min(step // config.fixed_stage_steps, len(STAGES) - 1)
        else:
            level = gate.level
        permission = STAGES[level]
        obs = plant.observation
        started = time.perf_counter()
        fallback = False
        if mode == "zero":
            action = np.zeros(2)
        elif mode == "pd":
            # Explicit task prior: fixed nominal feedforward and hand-set gains.
            nominal = model.parameters
            feedforward = np.asarray(nominal.stiffness) * target + nominal.coupling * (target - target[::-1])
            action = envelope.apply(feedforward + 4.0 * (target - obs[:2]) - 2.0 * obs[2:], permission)
        else:
            plan = planner.plan(obs, target, permission, previous)
            action, fallback = plan.action, plan.fallback
        timings.append(time.perf_counter() - started)
        # Actual small disturbances test settling in every evidence window.
        disturbance = np.array([0.12, -0.10]) if step % config.window_steps < 2 else np.zeros(2)
        predicted = model.predict(obs, action)
        next_obs = plant.step(action, external_torque=disturbance)
        position = next_obs[:2]
        finite = bool(np.isfinite(next_obs).all())
        safe = bool(finite and np.max(np.abs(position)) <= config.position_limit
                    and np.max(np.abs(next_obs[2:])) <= config.speed_limit)
        permitted = np.asarray(permission.torque_limits)
        assert np.all(np.abs(action) <= np.asarray(config.hard_torque_limits) + 1e-12)
        assert np.all(np.abs(action) <= permitted + 1e-12)
        assert np.all(action[~np.asarray(permission.active_joints)] == 0)
        item = {
            "step": step + 1, "level": level,
            "q0": float(position[0]) if finite else None, "q1": float(position[1]) if finite else None,
            "v0": float(next_obs[2]) if finite else None, "v1": float(next_obs[3]) if finite else None,
            "action0": float(action[0]), "action1": float(action[1]),
            "disturbance0": float(disturbance[0]), "disturbance1": float(disturbance[1]),
            "prediction_rmse": float(np.sqrt(np.mean(((predicted - next_obs) / state_scales) ** 2))) if finite else None,
            "tracking_rmse": float(np.sqrt(np.mean((position - target) ** 2))) if finite else None,
            "finite": finite, "safe": safe, "fallback": fallback,
            "permission_saturated": bool(np.any((permitted > 0) & (np.abs(action) >= permitted - 1e-12))),
            "hard_limit_reached": bool(np.any(np.abs(action) >= np.asarray(config.hard_torque_limits) - 1e-12)),
        }
        trace.append(item)
        window.append(item)
        if finite and len(window) == config.window_steps and mode == "competence" and not common_evaluation:
            active = np.asarray(permission.active_joints)
            errors = np.array([[r["q0"], r["q1"]] for r in window]) - target
            tail = window[-5:]
            tail_error = np.array([[r["q0"], r["q1"]] for r in tail]) - target
            evidence = GateEvidence(
                prediction_rmse=float(np.sqrt(np.mean([r["prediction_rmse"] ** 2 for r in window]))),
                tracking_rmse=float(np.sqrt(np.mean(errors[:, active] ** 2))),
                peak_speed=max(max(abs(r["v0"]), abs(r["v1"])) for r in window),
                # Observed residual maximum only; not a calibrated uncertainty bound.
                model_error_bound=max(r["prediction_rmse"] for r in window),
                safe=all(r["safe"] and not r["fallback"] for r in window),
                recovered=bool(np.sqrt(np.mean(tail_error[:, active] ** 2)) <= gate.config.max_tracking_rmse
                               and max(max(abs(r["v0"]), abs(r["v1"])) for r in tail) <= config.recovery_speed),
            )
            gate.observe(evidence)
            window = []
        if not safe:
            # End the trial rather than clipping state and hiding an exit.
            break
        previous = action
    all_finite = all(r["finite"] for r in trace)
    squared_errors = [r["tracking_rmse"] ** 2 for r in trace if r["finite"]]
    residuals = [r["prediction_rmse"] ** 2 for r in trace if r["finite"]]
    summary = {
        "executed_steps": plant.executed_steps,
        "physical_seconds": plant.executed_steps * config.dt,
        "tracking_rmse": float(np.sqrt(np.mean(squared_errors))) if all_finite else None,
        "final_tracking_rmse": trace[-1]["tracking_rmse"],
        "prediction_rmse": float(np.sqrt(np.mean(residuals))) if all_finite else None,
        "peak_speed": max(max(abs(r["v0"]), abs(r["v1"])) for r in trace) if all_finite else None,
        "state_limit_exit": any(r["finite"] and not r["safe"] for r in trace),
        "nonfinite_exit": not all_finite,
        "termination_reason": "nonfinite_state" if not all_finite else ("state_limit" if not trace[-1]["safe"] else "completed"),
        "fallback_steps": sum(r["fallback"] for r in trace),
        "permission_saturated_steps": sum(r["permission_saturated"] for r in trace),
        "hard_limit_steps": sum(r["hard_limit_reached"] for r in trace),
        "action_selection_ms_mean": 1000 * float(np.mean(timings)),
        "action_selection_ms_p95": 1000 * float(np.quantile(timings, 0.95)),
        "action_selection_over_dt_steps": sum(t > config.dt for t in timings),
        "stage_exposure_steps": {str(k): sum(r["level"] == k for r in trace) for k in range(len(STAGES))},
        "final_applied_level": trace[-1]["level"],
        "gate_final_level": gate.level if mode == "competence" and not common_evaluation else None,
        "evidence_window_pending_steps": len(window) if mode == "competence" and not common_evaluation else None,
        "gate_promotions": sum(e["decision"] == "promote" for e in gate.events),
        "gate_retreats": sum(e["decision"] == "retreat" for e in gate.events),
    }
    return summary, trace, gate.events


def run_validation(config: ValidationConfig = ValidationConfig()):
    model = FixedBodyModel(dt=config.dt)
    envelope = ActionEnvelope(config.hard_torque_limits)
    planner = CandidatePlanner(model, envelope)
    frozen = {"model": asdict(model), "planner": asdict(planner.config),
              "gate": asdict(GateConfig()), "stages": [asdict(s) for s in STAGES],
              "pd_gains": {"kp": 4.0, "kd": 2.0}, "config": asdict(config)}
    before = _signature(frozen)
    model_before = model.fingerprint()
    records, all_trace, events = [], [], []
    started = time.perf_counter()
    for scenario, parameters in SCENARIOS.items():
        for seed in config.seeds:
            for mode in MODES:
                mechanism, trace, gate_events = _run_phase(parameters, mode, seed, config, model, planner, envelope)
                evaluation, eval_trace, _ = _run_phase(parameters, mode, seed, config, model, planner, envelope, True)
                record = {"scenario": scenario, "seed": seed, "mode": mode,
                          "mechanism": mechanism, "common_evaluation": evaluation}
                records.append(record)
                for phase, frames in (("mechanism", trace), ("common_evaluation", eval_trace)):
                    all_trace.extend({"scenario": scenario, "seed": seed, "mode": mode,
                                      "phase": phase, **frame} for frame in frames)
                events.extend({"scenario": scenario, "seed": seed, "mode": mode, **event} for event in gate_events)
    assert model.fingerprint() == model_before
    after_state = {**frozen, "model": asdict(model), "planner": asdict(planner.config)}
    after = _signature(after_state)
    assert before == after, "a fixed parameter changed during validation"
    # After permission reset, identical fixed planners must produce identical control.
    for scenario in SCENARIOS:
        for seed in config.seeds:
            matching = [r for r in records if r["scenario"] == scenario and r["seed"] == seed
                        and r["mode"] in ("full", "fixed", "competence")]
            errors = [r["common_evaluation"]["tracking_rmse"] for r in matching]
            if any(error is None for error in errors):
                assert all(error is None for error in errors)
            else:
                assert max(errors) - min(errors) < 1e-12
    root = Path(__file__).resolve().parents[2]
    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(Path(__file__).parent.glob("*.py"))}
    report = {
        "kind": "cpu_no_training_mechanism_validation",
        "device": "cpu", "model_parameter_updates": 0, "policy_parameter_updates": 0,
        "model_fingerprint_before": model_before, "model_fingerprint_after": model.fingerprint(),
        "fixed_parameters_before": before, "fixed_parameters_after": after,
        "config": frozen, "plant_scenarios": {k: asdict(v) for k, v in SCENARIOS.items()},
        "elapsed_seconds": time.perf_counter() - started,
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "source_sha256": sources, "git": _git_info(root),
        "total_executed_steps": sum(r["mechanism"]["executed_steps"] + r["common_evaluation"]["executed_steps"] for r in records),
        "common_evaluation_same_planner_identical": True,
        "limitations": [
            "Stable supported spring/damper joints; no humanoid, gravity balance or contact switching.",
            "Nominal matched scenario is a disclosed exact-model diagnostic, not learned body knowledge.",
            "Model, controller gains, thresholds and candidate rules are fixed; gate state changes only.",
            "Gate uses observed residuals, not a calibrated or proven uncertainty bound.",
            "Prediction residuals are normalized by position/speed limits; tracking error is in radians.",
            "Timing covers action selection only, excluding evidence aggregation, gate decisions and communication.",
            "Zero torque fallback is fixture-specific; command clipping does not ensure state safety.",
            "Active-joint gate evidence differs by stage; full-target metrics and common full-permission evaluation are reported separately.",
            "No online-learning benefit, sample efficiency, cold-start skill acquisition, G1 or real-robot conclusion is tested.",
        ],
        "records": records,
    }
    return report, all_trace, events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/cpu_validation"))
    parser.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2])
    args = parser.parse_args()
    report, trace, events = run_validation(ValidationConfig(seeds=tuple(args.seeds)))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (args.output / "gate_events.json").write_text(json.dumps(events, indent=2, allow_nan=False), encoding="utf-8")
    with (args.output / "trace.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trace[0]))
        writer.writeheader()
        writer.writerows(trace)
    snapshot = args.output / "source_snapshot" / "developmental_control"
    snapshot.mkdir(parents=True, exist_ok=True)
    for source in Path(__file__).parent.glob("*.py"):
        (snapshot / source.name).write_bytes(source.read_bytes())
    print(json.dumps({"report": str(args.output / "report.json"), "runs": len(report["records"]),
                      "elapsed_seconds": report["elapsed_seconds"], "executed_steps": report["total_executed_steps"],
                      "model_parameter_updates": 0, "policy_parameter_updates": 0}, indent=2))


if __name__ == "__main__":
    main()
