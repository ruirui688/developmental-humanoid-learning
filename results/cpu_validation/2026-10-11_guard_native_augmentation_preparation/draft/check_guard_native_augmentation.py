"""Only four new L data-qualification/isolation/gate checks; no fits/rollouts."""
from __future__ import annotations

from collections import Counter
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


STAGING = Path(__file__).resolve().parent
REPO = STAGING.parent.parent
spec = importlib.util.spec_from_file_location("staged_L", STAGING/"develop_guard_native_augmentation.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)
K = L.load_core(REPO)


def rows(kind, active, base):
    trial = f"seed0_{kind}"
    result = {}
    for step in range(100+active):
        def obs(endpoint):
            return {"joint_position": [float(i+1)/100 for i in range(8)],
                "joint_velocity": [float(base+.001*endpoint+i*.01) for i in range(8)],
                "imu_gyro": [.1, .2, .3], "imu_acceleration": [.981, 1.962, 2.943]}
        result[step] = {"trial_id": trial, "seed": 0, "kind": kind, "step_index": step,
            "phase": "prefix" if step < 100 else "calibration" if kind == "calibration_sparse" else "control",
            "shared_transition_id": f"{trial}:{step}", "observation_before": obs(step), "observation_after": obs(step+1),
            "requested_torque": [.1, -.1, 0., 0., 0., 0., 0., 0.], "study_abort": None,
            "diagnostics": {"executed_substeps": 10, "terminated": False},
            "target_q": [12345.], "model_update": {"forbidden": True}, "reward": 12345.}
    return result


def fixtures():
    c, g = rows("calibration_sparse", 400, .1), rows("PDselected", 200, .6)
    selected = {"C": {"seed0_calibration_sparse": c}, "G": {"seed0_PDselected": g}}
    return selected, {"seed0_calibration_sparse": 400, "seed0_PDselected": 200}


def expect_failure(function):
    try:
        function()
    except (KeyError, TypeError, ValueError) as exc:
        return f"{type(exc).__name__}:{exc}"
    raise AssertionError("invalid L data qualification was accepted")


def branch_fixed_mix_native_whitelist():
    selected, counts = fixtures()
    raw_PD = list(selected["G"]["seed0_PDselected"].values())
    raw_PD.append({"seed": 0, "kind": "zero", "target_q": [99999.]})
    blob = gzip.compress(b"".join((json.dumps(r)+"\n").encode() for r in raw_PD))
    cost = Counter()
    parsed, actual_counts = L.parse_PD_trials(blob, cost)
    assert actual_counts["seed0_PDselected"] == 200
    assert set(parsed["seed0_PDselected"][100]).isdisjoint(("target_q", "reward", "model_update"))
    selected["G"] = parsed
    training = L.qualified_training_windows(K, selected, counts, 0)
    assert len(training) == 600
    assert [item[0] for item in training] == ["C"]*400+["G"]*200
    assert training[0][1]["shared_transition_id"] == "seed0_calibration_sparse:100"
    assert training[400][1]["shared_transition_id"] == "seed0_PDselected:100"
    assert training[400][2][0]["shared_transition_id"] == "seed0_PDselected:98"
    assert training[400][4] == K.native(selected["G"]["seed0_PDselected"][98]["observation_after"])[1][:2]
    assert training[400][4] != K.native(selected["C"]["seed0_calibration_sparse"][499]["observation_after"])[1][:2]
    return {"ordered_C_rows": 400, "ordered_G_rows": 200, "G_origin_history_is_own_prefix": True,
            "PD_target_reward_update_fields_discarded": True, "cost": dict(cost)}


def branch_cross_trial_history():
    selected, counts = fixtures()
    selected["G"]["seed0_PDselected"][100]["observation_before"] = copy.deepcopy(
        selected["C"]["seed0_calibration_sparse"][499]["observation_after"])
    reason = expect_failure(lambda: L.qualified_training_windows(K, selected, counts, 0))
    assert "discontinuous_past_two_native_endpoints" in reason
    return {"C_last_endpoint_as_G_start_rejected": True, "reason": reason}


def branch_600_qualification():
    selected, counts = fixtures()
    shortened_C = {**counts, "seed0_calibration_sparse": 399}
    missing_C_count = expect_failure(lambda: L.qualified_training_windows(K, selected, shortened_C, 0))
    assert "full_fixed_C_400_source_count_required" in missing_C_count
    shortened = {**counts, "seed0_PDselected": 199}
    missing_count = expect_failure(lambda: L.qualified_training_windows(K, selected, shortened, 0))
    assert "full_fixed_G_200_source_count_required" in missing_count
    del selected["G"]["seed0_PDselected"][150]
    missing_row = expect_failure(lambda: L.qualified_training_windows(K, selected, counts, 0))
    assert "missing_fixed_native_window_or_history" in missing_row
    selected, counts = fixtures()
    selected["G"]["seed0_PDselected"][299]["study_abort"] = {"synthetic_stop": True}
    stopped = expect_failure(lambda: L.qualified_training_windows(K, selected, counts, 0))
    assert "full_unstopped_training_trial_required" in stopped
    return {"missing_C_count": missing_C_count, "missing_G_count": missing_count,
            "missing_row": missing_row, "terminal_stopped_G_rejected": stopped}


def branch_separate_named_gates():
    groups = []
    for seed in L.SEEDS:
        for horizon in L.HORIZONS:
            for name in L.PREDICTORS:
                for channel in (range(22) if name != "D11" else (0, 1, 8, 9)):
                    groups.append({"seed": seed, "horizon": horizon, "predictor": name, "channel_index": channel,
                        "full_fixed_count": True, "source_active_count": 100,
                        "metric": {"rmse": {"K22": 1., "L22": .75, "D11": .7}[name]}})
    augmentation, matched = L.development_gate(groups, "K22"), L.development_gate(groups, "D11")
    assert augmentation["name"] == "L22_vs_K22_data_augmentation" and augmentation["passed"]
    assert matched["name"] == "L22_vs_D11_original_K_rules" and not matched["passed"]
    assert not (augmentation["passed"] and matched["passed"])
    assert "K22_rmse" in augmentation["checks"][0]["seed_records"][0]
    assert "D11_rmse" in matched["checks"][0]["seed_records"][0]
    assert not augmentation["scientific_adoption"] and not matched["old_K_D_gates_reinterpreted"]
    return {"augmentation_gate_passed": True, "matched_D11_gate_passed": False,
            "single_gate_does_not_release_new_holdout_control": True, "old_gates_not_reinterpreted": True}


if __name__ == "__main__":
    path = STAGING/"CHECK_01.json"
    if path.exists():
        raise FileExistsError("preserve first L check; no overwrite/rerun")
    checks = []
    for function in (branch_fixed_mix_native_whitelist, branch_cross_trial_history,
                     branch_600_qualification, branch_separate_named_gates):
        try:
            checks.append({"name": function.__name__, "passed": True, "result": function()})
        except Exception as exc:
            checks.append({"name": function.__name__, "passed": False, "failure": f"{type(exc).__name__}:{exc}"})
    result = {"synthetic_only": True, "checks": checks, "branch_count": 4, "passed": all(r["passed"] for r in checks),
        "real_trace_reads": 0, "real_K_weight_reads": 0, "model_predictions": 0, "fit_calls": 0,
        "ridge_solves": 0, "physics_calls": 0, "RLS_updates": 0, "K_old_checks_repeated": False,
        "source_sha256": {name: hashlib.sha256((STAGING/name).read_bytes()).hexdigest() for name in (
            "develop_guard_native_augmentation.py", "GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_PROTOCOL.md",
            "check_guard_native_augmentation.py")},
        "canonical_K_source_sha256": hashlib.sha256((REPO/L.CORE_PATH).read_bytes()).hexdigest(),
        "runtime": {"python": sys.version, "numpy": L.np.__version__}}
    path.write_bytes(L.json_bytes(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if not result["passed"]:
        raise SystemExit(1)
