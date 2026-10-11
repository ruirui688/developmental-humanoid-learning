"""Source-only Z derivation from closed Y drafts and its frozen controller."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
repo = root.parent.parent
read_cost = {"source_file_reads": 0, "source_read_and_hash_bytes": 0}
pins = {}

def read(name):
    data = (repo/name).read_bytes()
    read_cost["source_file_reads"] += 1
    read_cost["source_read_and_hash_bytes"] += len(data)
    pins[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    return data.decode("utf-8")

def change(source, before, after, expected=1):
    if source.count(before) != expected:
        raise ValueError("unexpected_source_replacement_population:" + before)
    return source.replace(before, after)

controller = read("src/developmental_physics/damped_residual_pd_pair_mpc.py")
controller = controller.replace("Y ", "Z ").replace("Y_", "Z_")
controller = controller.replace("DampedResidualPDPairMPC", "FastFeedbackResidualPDPairMPC")
controller = change(controller, "from dataclasses import dataclass", "from dataclasses import dataclass, replace")
controller = change(controller, "import numpy as np", "import numpy as np\n\nfrom .local_model import MPCConfig")
controller = change(controller, "super().__init__(model, joint_ranges, config)",
    'baseline = MPCConfig()\n        micro = replace(baseline, horizon=150, position_weight=.1 * baseline.position_weight,\n                        velocity_weight=.1 * baseline.velocity_weight, effort_weight=.1 * baseline.effort_weight)\n        if config is not None and config != micro:\n            raise ValueError("Z_fixed_micro_horizon_and_time_normalized_cost_required")\n        if model.dt != .002:\n            raise ValueError("Z_controller_requires_2ms_body_model")\n        super().__init__(model, joint_ranges, micro)')
controller = controller.replace('"81 first residuals, H15 predicted PD tail, complete-request costs."',
    '"81 held-ten-microstep residuals, H150 micro PD tail and complete costs."')
controller = controller.replace('"action_rollout": "clip(PD(current)+delta) first; PD(each candidate predicted state) tail; apply first only",',
    '"action_rollout": "PD(predicted q/v)+held delta for first ten 2ms steps; remaining 140 PD steps delta zero",\n                "execution": "hold chosen residual for ten native-feedback microsteps; fallback literal torque zero for ten",\n                "micro_dt_seconds": .002, "planning_period_seconds": .02,\n                "residual_hold_microsteps": 10, "running_cost_time_scale": .1,\n                "discount": "none; original cost has no discount",')
controller = change(controller, "request = first if stage == 0 else pd_request(pq, pv)",
    'if stage == 0:\n                    request = first\n                else:\n                    base = pd_request(pq, pv)\n                    delta = residual if stage < 10 else (0., 0.)\n                    request = tuple(float(np.clip(base[i]+delta[i], -.5, .5)) for i in range(2))')
target = root/"src/developmental_physics/fast_feedback_pair_mpc.py"
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists():
    raise ValueError("fresh_Z_controller_path_required")
target.write_text(controller, encoding="utf-8")

development = read("external/y_learning_candidate/src/developmental_physics/damped_suspended_pair_development.py")
development = development.replace("Y1", "Z1").replace("Y2", "Z2").replace("y1", "z1").replace("y2", "z2").replace('f"Y_', 'f"Z_')
development = development.replace("7501", "7701").replace("7502", "7702").replace("7503", "7703")
development = change(development, "from .guard_coupled_pair_model import GuardCoupledPairBodyModel", "from .fast_feedback_pair_model import FastFeedbackGuardCoupledPairBodyModel")
development = development.replace("GuardCoupledPairBodyModel", "FastFeedbackGuardCoupledPairBodyModel")
development = development.replace("FastFeedbackFastFeedbackGuardCoupledPairBodyModel", "FastFeedbackGuardCoupledPairBodyModel")
development = development.replace("from .damped_residual_pd_pair_mpc import DampedResidualPDPairMPC", "from .fast_feedback_pair_mpc import FastFeedbackResidualPDPairMPC")
development = development.replace("DampedResidualPDPairMPC", "FastFeedbackResidualPDPairMPC")
development = change(development, "PREFIX = 100\nCALIBRATION = 400\nPREDICTION = 100\nCONTROL = 200\nHORIZONS = (1, 2, 5, 15)",
    "PREFIX = 1000\nCALIBRATION = 4000\nPREDICTION = 1000\nCONTROL = 2000\nHORIZONS = (1, 10, 20, 50, 150)\nSCORING_STRIDE = 10\nMACRO_HOLD = 10")
development = change(development, "block, slot = divmod(index, 20)", "block, slot = divmod(index // MACRO_HOLD, 20)")
development = development.replace('snapshot.get("dt_seconds") != .02', 'snapshot.get("dt_seconds") != .002')
development = development.replace('row["diagnostics"]["executed_substeps"] != 10', 'row["diagnostics"]["executed_substeps"] != 1')
development = development.replace("if len(samples) != 10:", "if len(samples) != 1:")
development = development.replace('10*row["control_index"]+i+1', 'row["control_index"]+i+1')
development = development.replace('10*len(selected)', 'len(selected)')
development = development.replace('result.diagnostics["executed_substeps"] == 10', 'result.diagnostics["executed_substeps"] == 1')
development = change(development, "origins = planned-horizon+1", "origin_indices = tuple(range(0, planned-horizon+1, SCORING_STRIDE))\n        origins = len(origin_indices)")
development = change(development, "for origin in range(origins):", "for origin in origin_indices:")
development = change(development, 'strict = (horizon, signal) in ((1, "v"), (15, "q"))', 'strict = (horizon, signal) in ((10, "v"), (150, "q"))')
development = change(development, 'gated = (horizon, signal) != (1, "q")', 'gated = horizon != 1 and (horizon, signal) != (10, "q")')
development = development.replace("# H1q is reported but is not an extra scientific veto.", "# Native H1 and physical-20ms H10q report only; no extra veto.")
development = development.replace("not_400_atomic_updates", "not_4000_atomic_updates").replace("400_update_learned", "4000_update_learned")
development = change(development, "controller = None", "controller = None\n            held_residual, held_fallback = None, True")
development = change(development, "def actor(observation, index, current):\n                q, v = native(observation)\n                target = current[\"targets_q2\"][0 if index < 100 else 1]", 
    'def actor(observation, index, current):\n                nonlocal held_residual, held_fallback\n                q, v = native(observation)\n                target = current["targets_q2"][0 if index < 1000 else 1]')
old_start = 'if name in models:\n                    cost["MPC_decision_attempts"] += 1'
new_start = 'if name in models:\n                    if index % MACRO_HOLD == 0:\n                        cost["MPC_decision_attempts"] += 1'
start = development.index(old_start)
end = development.index('                elif name == "pd":', start)
block = development[start:end]
# Indent only existing decision handling under the macro cadence branch.
lines = block.splitlines()
block = lines[0]+"\n                    if index % MACRO_HOLD == 0:\n"+"\n".join("    "+line for line in lines[1:] if line.strip() != "command = decision.torque")+"\n"
block += '                        held_residual, held_fallback = decision.selected_residual_nm, decision.fallback\n                    info.update(held_residual2=held_residual, held_fallback=held_fallback,\n                                residual_hold_micro_index=index % MACRO_HOLD, macro_decision_index=index // MACRO_HOLD)\n                    if held_fallback:\n                        command = (0., 0.)\n                    else:\n                        base = counted_pd(q, v, target, cost, "control_"+name)\n                        command = tuple(float(np.clip(base[i]+held_residual[i], -.5, .5)) for i in range(2))\n                        info["public_pd_request2"] = base\n'
development = development[:start]+block+development[end:]
target = root/"src/developmental_physics/fast_feedback_pair_development.py"
if target.exists():
    raise ValueError("fresh_Z_development_path_required")
target.write_text(development, encoding="utf-8")
(root/"source_derivation.json").write_text(json.dumps({"input_files": pins, "read_cost": read_cost,
    "production_imports": 0, "fixture_executions": 0, "model_calls": 0, "fit_calls": 0,
    "physical_calls": 0, "raw_reads": 0, "production_publication": False}, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"input_files": pins, "read_cost": read_cost, "outputs": ["fast_feedback_pair_mpc.py", "fast_feedback_pair_development.py"]}))
