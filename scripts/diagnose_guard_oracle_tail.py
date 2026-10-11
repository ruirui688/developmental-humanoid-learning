"""V: one frozen future-native-tail sensitivity diagnostic; offline only."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np

SOURCE_PATH = "scripts/diagnose_guard_oracle_tail.py"
PROTOCOL_PATH = "docs/GUARD_ORACLE_TAIL_DIAGNOSTIC_PROTOCOL.md"
R_SOURCE_PATH = "scripts/develop_guard_kinematic_native_transition.py"
U_ROOT = "results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition"
U_COMMIT = "7358ff9f583d9a20460e94c914cd8ea172c9780a"
SEEDS, HORIZONS = (0, 1, 2), (1, 2, 5, 15)
CONTROLLED = (0, 1, 8, 9)
ORACLE = (2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21)
PREDICTORS = ("Q22_saved_self", "U22_saved_self", "Q22_oracle18", "U22_oracle18")
FLAGS = {"scientific_adoption": False, "c4_scientific_validation": False,
         "c5_scientific_dependency_released": False}
HELPER_PINS = {
    "scripts/develop_guard_scaled_native_transition.py": "df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518",
    "docs/GUARD_SCALED_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "0027650441b59159b407e21b687057e816c61c127ca6f5f4f06b6ac44b8b87b7",
    "scripts/develop_guard_native_transition.py": "f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb",
    "docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "7be868a3215dc0e29dd6e96f4f19635259fda15e3a54545194513e11a892ce56",
    "src/developmental_physics/__init__.py": "d2ee9d572836752f5f8404bfdf1fca8add0d62b9858f4c6dcd9cf7ddc6c53ea2",
    "src/developmental_physics/guard_lag_pair_model.py": "f3bcedf05b2c956357929e51dcab026ec13311428fa3c6c3383db114da3f7e57",
    "src/developmental_physics/guard_pair_model.py": "2b8ae6f17aa12f1230daf38d8858f24bde3a3c21342e46a5b8fa6e91dc3da3b3",
    "src/developmental_physics/local_pair_model.py": "81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df",
    "src/developmental_physics/local_model.py": "f51a43c36675980cddd0cbf1fcba576469dd015e0850833ae58ffc32479de2b1",
    "scripts/develop_guard_quadratic_native_transition.py": "6a8109ed9ba68b61674f9744ac0ea4ffce421ff8b4400abfe7cc081b5c16a147",
    "docs/GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "77cb47c42efad889f4d15cf64207b528ab2c7e29908d55d3f16441b0b7a6c5d3",
    "scripts/develop_guard_kinematic_native_transition.py": "07a0135e6cd30e169f780f30eef09472fe857570fa0556f552dcdcbe258c693d",
    "docs/GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md": "8f3c86ccfc4626dbf6219e904daa73b208d2cac044a855e050875aecd62e5c45",
    "scripts/develop_guard_bounded_lbfgs_position_transition.py": "7c2c2ea6cbe421edca73bd0e53adc1ad2f373390c694e8c7950d5b1b32f1ef95",
    "docs/GUARD_BOUNDED_LBFGS_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md": "222f9f65e09c9b71f9bfdae12c39f95bce8472e3652e85bb107b9ed8156669ed"
}
INPUT_PINS = {
    "manifest.json": {"bytes": 27622, "sha256": "6cf687b77fdebbb2cc1104c9459997a5bd9ca928e471f87ca355782d0c1c7109"},
    "raw/manifest.json": {"bytes": 15434, "sha256": "f53834dca057fb6088744916068db350855fe21ecc7eacd34273365f19a57acf"},
    "raw/run.json": {"bytes": 40201, "sha256": "0208050b62e08748c62b13faf58fbd973a0bccb79d67fa2f4578ff55b5751839"},
    "raw/parameters.json": {"bytes": 21860808, "sha256": "fd7509e141d8bb8facc42090c0ade8d6cb2d347ea47ace852554de353c4eaf82"},
    "raw/predictions.jsonl": {"bytes": 30672670, "sha256": "060e7d32879b583dbb9b2c98369d0faf900cf4c582661196355ab8fa32d32a8b"},
    "raw/metrics.json": {"bytes": 468715, "sha256": "0b6d0c537d054862940d3503aded2a35882d3891b29d0c80469f4b2a9c8404eb"},
}
PUBLIC_RANGES = ((-1.7453292519943295, 1.7453292519943295), (0., 2.356194490192345))
FIXED_BUDGET = {"requested_records": 4572, "saved_self_records": 2286,
                "oracle_records": 2286, "controlled_metric_groups": 192,
                "oracle_full22_transitions": 12408, "nonterminal18_overwrites": 10122,
                "future18_scalar_uses": 182196, "H1_pair_records": 600}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def failure_json_safe(value):
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return {"nonfinite_float": "NaN" if np.isnan(value) else "+Infinity" if value > 0 else "-Infinity"}
    if isinstance(value, dict):
        return {key: failure_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [failure_json_safe(item) for item in value]
    return value


def finite(value, shape):
    result = np.asarray(value, dtype=np.float64)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"expected_finite_shape:{shape}")
    return result


def sources(repo, commit, cost, files, synthetic):
    if Path(__file__).resolve() != (repo/SOURCE_PATH).resolve():
        raise ValueError("canonical_V_path_required")
    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("source_git_query_failed")
        cost["git_query_returns"] += 1
        return result.stdout
    if not synthetic:
        if not commit or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("exact_V_commit_required")
        if git("rev-parse", "HEAD").decode().strip() != commit or git("status", "--porcelain").strip():
            raise ValueError("clean_exact_V_HEAD_required")
    for name in (SOURCE_PATH, PROTOCOL_PATH, *HELPER_PINS):
        cost["source_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_raw_bytes"] += len(data)
        cost["source_hash_bytes"] += len(data)
        files[name] = identity(data)
        if name in HELPER_PINS and files[name]["sha256"] != HELPER_PINS[name]:
            raise ValueError("frozen_helper_hash_differs:"+name)
        if not synthetic and git("show", f"{commit}:{name}") != data:
            raise ValueError("committed_bytes_differ:"+name)


def load_helpers(repo, cost):
    sys.path.insert(0, str(repo/"src"))
    cost["helper_module_load_attempts"] += 1
    spec = importlib.util.spec_from_file_location("frozen_R_pure_loader_for_V", repo/R_SOURCE_PATH)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    cost["helper_module_load_returns"] += 1
    support, core, q_support = helper.load_helpers(repo, cost)
    return helper, support, core, q_support


def read_inputs(repo, inputs, cost, files, support):
    docs, prediction_blob = {}, None
    for name, expected in INPUT_PINS.items():
        path = f"{U_ROOT}/{name}"
        cost["input_file_read_attempts"] += 1
        data = (repo/path).read_bytes()
        cost["input_file_read_returns"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        inputs[path] = identity(data)
        if inputs[path] != expected:
            raise ValueError("frozen_U_input_differs:"+path)
        if name.endswith(".jsonl"):
            prediction_blob = data
        else:
            cost["input_json_parse_attempts"] += 1
            docs[name] = json.loads(data, parse_constant=lambda token: (_ for _ in ()).throw(ValueError("nonfinite_JSON:"+token)))
            cost["input_json_parse_returns"] += 1
    root, raw, run = (docs[name] for name in ("manifest.json", "raw/manifest.json", "raw/run.json"))
    for name in INPUT_PINS:
        if name == "manifest.json":
            continue
        if not support.same_identity(root["files"][name], inputs[f"{U_ROOT}/{name}"]):
            raise ValueError("U_root_payload_binding_differs:"+name)
        if name != "raw/manifest.json" and not support.same_identity(raw["files"][name.removeprefix("raw/")], inputs[f"{U_ROOT}/{name}"]):
            raise ValueError("U_raw_payload_binding_differs:"+name)
    if (raw.get("status") != "completed" or run.get("status") != "completed"
            or run.get("self_check") is not False or run["source"].get("commit") != U_COMMIT
            or run["source"].get("clean_committed_bytes_verified") is not True
            or any(run.get(key) is not False for key in FLAGS)):
        raise ValueError("frozen_U_completed_clean_identity_differs")
    for name in HELPER_PINS:
        if not support.same_identity(run["source"]["files"][name], files[name]):
            raise ValueError("U_helper_source_binding_differs:"+name)
    return docs, prediction_blob, run


def public_guards(run):
    from developmental_physics.guard_pair_model import KnownAngleGuard
    guards = {}
    rows = run["baseline_restorations"]["D11"]
    for seed in SEEDS:
        matches = [row for row in rows if row.get("seed") == seed]
        if len(matches) != 1:
            raise ValueError("one_saved_public_guard_per_seed_required")
        guard = KnownAngleGuard(PUBLIC_RANGES)
        if matches[0].get("public_guard") != guard.spec():
            raise ValueError("U_public_guard_spec_differs")
        guards[seed] = guard
    return guards


def restore_weights(helper, core, q_support, payload, guards, cost, parameters):
    models = {}
    for seed in SEEDS:
        matches = [row for row in payload if row.get("seed") == seed and row.get("predictor") == "U22"]
        record = {"seed": seed, "source_parameter_record": f"{U_ROOT}/raw/parameters.json:seed{seed}:U22",
                  "available": False, "public_guard": guards[seed].spec(), "refit": False,
                  "actual_updates": 0, "source_commit": U_COMMIT}
        parameters.append(record)
        cost["saved_parameter_restoration_attempts"] += 1
        if len(matches) != 1:
            record["reason"] = "missing_or_ambiguous_source_parameter_record"
            models[seed] = {}
            continue
        row = matches[0]
        if (row.get("state_order") != list(core.STATE_NAMES)
                or row.get("feature_order") != [*core.FEATURE_NAMES, *q_support.QUADRATIC_NAMES]
                or row.get("optimized_heads") != [0, 1]
                or row.get("frozen_head_indices") != list(range(2, 22))):
            raise ValueError("saved_U_mapping_metadata_differs")
        qref = finite(row["qref8"], (8,)).tolist()
        Q = finite(row["frozen_Q_weights50x22"], (50, 22)).copy()
        Qfingerprint = helper.Q_parameter_fingerprint(core, q_support, qref, Q)
        if Qfingerprint != row.get("Q22_parameter_fingerprint"):
            raise ValueError("saved_Q_fingerprint_differs")
        restored = {"Q22": Q}
        record.update(qref8=qref, Q22_fingerprint_before=Qfingerprint,
                      Q22_weights_source_field="frozen_Q_weights50x22")
        cost["Q22_saved_weight_scalars_validated"] += 1100
        if row.get("available") is True:
            U = finite(row["selected_weights50x22"], (50, 22)).copy()
            Ufingerprint = helper.Q_parameter_fingerprint(core, q_support, qref, U)
            if Ufingerprint != row.get("parameter_fingerprint") or not np.array_equal(U[:, 2:], Q[:, 2:]):
                raise ValueError("saved_U_fingerprint_or_frozen_twenty_heads_differ")
            restored["U22"] = U
            record.update(available=True, U22_fingerprint_before=Ufingerprint,
                          U22_weights_source_field="selected_weights50x22")
            cost["U22_saved_weight_scalars_validated"] += 1100
        else:
            record["reason"] = "source_U_unavailable"
        models[seed] = {"qref8": qref, "weights": restored, "guard": guards[seed]}
        cost["saved_parameter_restoration_returns"] += 1
    return models


def parse_saved(blob, cost):
    indexed = {}
    for line in blob.splitlines():
        cost["saved_prediction_line_parse_attempts"] += 1
        row = json.loads(line, parse_constant=lambda token: (_ for _ in ()).throw(ValueError("nonfinite_JSON:"+token)))
        cost["saved_prediction_line_parse_returns"] += 1
        cost["saved_prediction_uncompressed_bytes"] += len(line)+1
        if row.get("predictor") not in ("Q22", "U22"):
            continue
        seed, horizon, origin = row.get("seed"), row.get("horizon"), row.get("origin")
        if (type(seed) is not int or seed not in SEEDS or type(horizon) is not int or horizon not in HORIZONS
                or type(origin) is not int or not 0 <= origin < 101-horizon
                or row.get("trial_id") != f"seed{seed}_prediction"):
            raise ValueError("saved_selected_prediction_identity_differs")
        indexed.setdefault((seed, row["predictor"], horizon, origin), []).append(row)
        cost["saved_selected_prediction_records"] += 1
    return indexed


def source_row(indexed, seed, source, horizon, origin):
    rows = indexed.get((seed, source, horizon, origin), [])
    if len(rows) != 1:
        return None, "missing_or_ambiguous_source_record"
    return rows[0], None


def legal_window(row, seed, horizon, origin):
    trial = f"seed{seed}_prediction"
    if (row.get("trial_id") != trial
            or row.get("history_transition_ids") != [f"{trial}:{98+origin}", f"{trial}:{99+origin}"]
            or row.get("requested_transition_ids") != [f"{trial}:{100+origin+j}" for j in range(horizon)]):
        raise ValueError("source_saved_continuous_window_IDs_differ")
    finite(row["initial_x22"], (22,))
    finite(row["previous_v2"], (2,))
    finite(row["requested_sequence8"], (horizon, 8))


def native_label(indexed, seed, origin, expected_id):
    row, reason = source_row(indexed, seed, "U22", 1, origin)
    if row is None:
        raise ValueError("oracle_label_"+reason)
    legal_window(row, seed, 1, origin)
    if (row.get("available") is not True or row.get("scored") is not True
            or row.get("source_stopped_at_endpoint") is not False
            or row.get("requested_transition_ids") != [expected_id]):
        raise ValueError("oracle_label_unavailable_or_endpoint_ID_differs")
    actual = row["actual_endpoint_x22"]
    if len(actual) != 22:
        raise ValueError("oracle_label_shape_differs")
    tail = finite([actual[i] for i in ORACLE], (18,))
    return tail, {"source_predictor": "U22", "source_horizon": 1,
                  "seed": seed, "trial_id": f"seed{seed}_prediction", "origin": origin,
                  "endpoint_transition_id": expected_id, "source_field": "actual_endpoint_x22",
                  "oracle_indices": list(ORACLE), "oracle_native18": tail.tolist()}


def oracle_rollout(initial, previous_v, requests, requested_ids, origin, step, label, cost, owner):
    """New V layer: validate full22, advance predicted history, then clamp nonterminal18."""
    path, history, replacements = [], [], []
    x, previous = finite(initial, (22,)).copy(), finite(previous_v, (2,)).copy()
    result = {"available": False, "predicted_preoverwrite_path_x22": path,
              "history_inputs": history, "oracle_replacements": replacements}
    for j, request in enumerate(requests):
        partial = {"step_index": j, "request_transition_id": requested_ids[j],
                   "previous_v2_before": previous.tolist(), "current_x22_before": x.tolist()}
        history.append(partial)
        cost[f"{owner}_full22_forward_attempts"] += 1
        try:
            outcome = step(x, previous, request)
            partial["frozen_full22_step"] = outcome
            if outcome.get("available") is not True:
                raise ValueError("original_full22_forward_unavailable:"+outcome.get("reason", "unknown"))
            candidate = finite(outcome["terminal_x22"], (22,)).copy()
            predicted_previous = finite(outcome["terminal_previous_v2"], (2,)).copy()
            # All22 finite precedes label lookup and any overwrite, including ignored18 heads.
            cost[f"{owner}_full22_forward_returns"] += 1
            cost[f"{owner}_discarded_tail_head_outputs"] += 18
            if not np.array_equal(predicted_previous, x[8:10]):
                raise ValueError("original_predicted_old_current_v_history_differs")
            previous = predicted_previous
            path.append(candidate.tolist())
            partial["previous_v2_after"] = previous.tolist()
            if j < len(requests)-1:
                cost[f"{owner}_oracle_label_attempts"] += 1
                tail, evidence = label(origin+j, requested_ids[j])
                tail = finite(tail, (18,))
                cost[f"{owner}_oracle_label_returns"] += 1
                hybrid = candidate.copy()
                hybrid[list(ORACLE)] = tail
                # Controlled q/v and predicted previous_v remain from the original forward.
                if not np.array_equal(hybrid[list(CONTROLLED)], candidate[list(CONTROLLED)]):
                    raise ValueError("controlled_channels_changed_by_oracle")
                evidence = {**evidence, "step_index": j, "hybrid_x22_after": hybrid.tolist()}
                replacements.append(evidence)
                cost[f"{owner}_nonterminal18_overwrites"] += 1
                cost[f"{owner}_future18_scalar_uses"] += 18
                x = hybrid
            else:
                x = candidate
        except Exception as exc:
            cost[f"{owner}_oracle_rollout_step_failures"] += 1
            result.update(reason=f"{type(exc).__name__}:{exc}", failed_step=partial,
                          failed_step_index=j, partial_previous_v2=previous.tolist())
            return result
    result.update(available=True, terminal_x22=x.tolist(), terminal_previous_v2=previous.tolist(),
                  controlled_terminal4=x[list(CONTROLLED)].tolist(),
                  terminal18_overwritten=False, terminal18_scored=False)
    return result


def common_record(seed, source, horizon, origin, oracle):
    return {"seed": seed, "trial_id": f"seed{seed}_prediction", "origin": origin, "horizon": horizon,
            "predictor": source+("_oracle18" if oracle else "_saved_self"),
            "source_predictor": source, "source_horizon": horizon, "source_origin": origin,
            "source_input": f"{U_ROOT}/raw/predictions.jsonl",
            "controlled_indices": list(CONTROLLED), "terminal18_scored": False,
            "available": False, "scored": False, "privileged_diagnostic": oracle}


def transcribe_self(common, row, reason, cost):
    if row is None:
        return {**common, "reason": reason}
    if row.get("available") is not True or row.get("scored") is not True:
        return {**common, "reason": "source_self_unavailable:"+str(row.get("reason", "unscored")),
                "source_available": row.get("available"), "source_scored": row.get("scored"),
                "source_stop": row.get("source_stopped_at_endpoint")}
    try:
        legal_window(row, common["seed"], common["horizon"], common["origin"])
        terminal = finite(row["terminal_x22"], (22,))
        actual = row["actual_endpoint_x22"]
        errors = row["terminal_errors_x22"]
        controlled_actual = finite([actual[i] for i in CONTROLLED], (4,))
        controlled_errors = finite([errors[str(i)] for i in CONTROLLED], (4,))
        cost["saved_self_records_transcribed"] += 1
        cost["saved_self_controlled_errors_transcribed"] += 4
        return {**common, "available": True, "scored": True, "transcribed_without_forward_or_error_recalculation": True,
                "controlled_terminal4": terminal[list(CONTROLLED)].tolist(),
                "actual_controlled4": controlled_actual.tolist(),
                "terminal_errors_x22": {str(i): float(controlled_errors[j]) for j, i in enumerate(CONTROLLED)},
                "source_stop": row.get("source_stopped_at_endpoint")}
    except (KeyError, TypeError, ValueError) as exc:
        return {**common, "reason": "source_self_fields_unavailable:"+str(exc)}


def evaluate(core, q_support, indexed, models, cost, predictions):
    h1 = {"requested_pair_records": FIXED_BUDGET["H1_pair_records"], "compared_pair_records": 0,
          "exact_pair_records": 0, "unavailable_pair_records": 0}
    for seed in SEEDS:
        for horizon in HORIZONS:
            for origin in range(101-horizon):
                for source in ("Q22", "U22"):
                    cost["V_requested_saved_self_records"] += 1
                    cost["V_requested_oracle_records"] += 1
                    row, reason = source_row(indexed, seed, source, horizon, origin)
                    own = transcribe_self(common_record(seed, source, horizon, origin, False), row, reason, cost)
                    predictions.append(own)
                    record = common_record(seed, source, horizon, origin, True)
                    predictions.append(record)
                    model = models.get(seed, {})
                    if row is None or own["available"] is not True:
                        record["reason"] = "oracle_window_unavailable:"+str(reason or own.get("reason"))
                    elif source not in model.get("weights", {}):
                        record["reason"] = "oracle_model_unavailable"
                    else:
                        record.update(initial_x22=row["initial_x22"], previous_v2=row["previous_v2"],
                                      history_transition_ids=row["history_transition_ids"],
                                      requested_transition_ids=row["requested_transition_ids"],
                                      requested_sequence8=row["requested_sequence8"],
                                      source_stop=row.get("source_stopped_at_endpoint"))
                        def step(x, previous, request):
                            paid = Counter()
                            try:
                                return q_support.rollout50(core, x, previous, [request], model["qref8"],
                                                           model["guard"], model["weights"][source], paid)
                            finally:
                                cost.update({key.replace("Q22", source+"_oracle18"): value for key, value in paid.items()})
                        def label(label_origin, expected_id):
                            return native_label(indexed, seed, label_origin, expected_id)
                        record.update(oracle_rollout(row["initial_x22"], row["previous_v2"], row["requested_sequence8"],
                                      row["requested_transition_ids"], origin, step, label, cost, source+"_oracle18"))
                        if record["available"]:
                            actual = finite(own["actual_controlled4"], (4,))
                            terminal = finite(record["controlled_terminal4"], (4,))
                            with np.errstate(over="ignore", invalid="ignore"):
                                errors = actual-terminal
                            if not np.isfinite(errors).all():
                                record.update(available=False, reason="nonfinite_controlled_terminal_error")
                            else:
                                cost["oracle_controlled_score_scalar_error_calculations"] += 4
                                record.update(scored=True, actual_controlled4=actual.tolist(),
                                              terminal_errors_x22={str(i): float(errors[j]) for j, i in enumerate(CONTROLLED)})
                    if horizon == 1:
                        if own["available"] and record["available"]:
                            h1["compared_pair_records"] += 1
                            if (own["controlled_terminal4"] != record["controlled_terminal4"]
                                    or own["terminal_errors_x22"] != record["terminal_errors_x22"]):
                                record.update(available=False, scored=False, reason="H1_exact_saved_self_identity_failed")
                                raise ValueError("H1_controlled_per_record_exact_identity_failed")
                            h1["exact_pair_records"] += 1
                        else:
                            h1["unavailable_pair_records"] += 1
    h1["all_requested_exact"] = h1["exact_pair_records"] == h1["requested_pair_records"]
    return h1


def summarize(core, predictions, saved_metrics, cost):
    groups = []
    old = saved_metrics["groups"]
    for seed in SEEDS:
        for horizon in HORIZONS:
            expected = 101-horizon
            for source in ("Q22", "U22"):
                for channel in CONTROLLED:
                    matches = [g for g in old if (g.get("seed"), g.get("horizon"), g.get("predictor"), g.get("channel_index")) == (seed, horizon, source, channel)]
                    own_rows = [r for r in predictions if (r["seed"], r["horizon"], r["predictor"]) == (seed, horizon, source+"_saved_self")]
                    good = [r for r in own_rows if r["available"] and r["scored"]]
                    if len(matches) == 1:
                        group = {**matches[0], "predictor": source+"_saved_self", "transcribed_from_U_metrics": True,
                                 "source_predictor": source, "source_input": f"{U_ROOT}/raw/metrics.json"}
                        if (group.get("fixed_origin_count") != expected or group.get("record_count") != len(own_rows)
                                or group.get("usable_count") != len(good) or group.get("unavailable_count") != len(own_rows)-len(good)):
                            group.update(full_fixed_count=False, reason="transcribed_metric_source_count_differs")
                        cost["saved_self_controlled_metric_groups_transcribed"] += 1
                    else:
                        group = {"seed": seed, "horizon": horizon, "predictor": source+"_saved_self", "channel_index": channel,
                                 "channel": core.STATE_NAMES[channel], "fixed_origin_count": expected,
                                 "record_count": len(own_rows), "usable_count": 0, "unavailable_count": expected,
                                 "full_fixed_count": False, "metric": {"count": 0, "rmse": None},
                                 "reason": "missing_or_ambiguous_saved_self_metric", "transcribed_from_U_metrics": False}
                    groups.append(group)
                own = [r for r in predictions if (r["seed"], r["horizon"], r["predictor"]) == (seed, horizon, source+"_oracle18")]
                good = [r for r in own if r["available"] and r["scored"]]
                for channel in CONTROLLED:
                    cost["oracle_controlled_metric_aggregate_attempts"] += 1
                    metric = core.metric([r["terminal_errors_x22"][str(channel)] for r in good])
                    cost["oracle_controlled_metric_aggregate_returns"] += 1
                    cost["oracle_controlled_metric_error_values_used"] += len(good)
                    groups.append({"seed": seed, "horizon": horizon, "predictor": source+"_oracle18",
                                   "source_predictor": source, "channel_index": channel, "channel": core.STATE_NAMES[channel],
                                   "fixed_origin_count": expected, "record_count": len(own), "usable_count": len(good),
                                   "unavailable_count": len(own)-len(good), "source_active_count": 100,
                                   "full_fixed_count": len(own) == len(good) == expected,
                                   "metric": metric, "partial_subset_method_ranking": False,
                                   "privileged_diagnostic": True})
    return groups


def diagnostic_rule(groups, h1):
    index = {(g["seed"], g["horizon"], g["predictor"], g["channel_index"]): g for g in groups}
    result = {"scope": "fixed_future_native18_sensitivity_only", "by_source": {}, "choose_better_source": False,
              "H1_exact_identity_required": True, "H1_exact_identity": h1["all_requested_exact"],
              "all_192_fixed_groups_full": len(groups) == 192 and all(g.get("full_fixed_count") is True for g in groups), **FLAGS}
    for source in ("Q22", "U22"):
        checks = []
        for horizon, channels in ((2, CONTROLLED), (5, CONTROLLED), (15, CONTROLLED)):
            for channel in channels:
                rows = []
                for seed in SEEDS:
                    own = index[(seed, horizon, source+"_saved_self", channel)]
                    oracle = index[(seed, horizon, source+"_oracle18", channel)]
                    a, b = own["metric"].get("rmse"), oracle["metric"].get("rmse")
                    full = own.get("full_fixed_count") is True and oracle.get("full_fixed_count") is True
                    numeric = full and a is not None and b is not None and np.isfinite(a) and np.isfinite(b)
                    improve = numeric and a > 0 and b < a
                    not_worse = numeric and b <= a
                    relative = float((a-b)/a) if numeric and a > 0 else None
                    rows.append({"seed": seed, "saved_self_rmse": a, "oracle18_rmse": b,
                                 "full_fixed_counts": full, "relative_improvement": relative,
                                 "strictly_improved": bool(improve), "not_worse": bool(not_worse)})
                q15 = horizon == 15 and channel in (0, 1)
                relatives = [r["relative_improvement"] for r in rows]
                mean = float(np.mean(relatives)) if all(v is not None for v in relatives) else None
                passed = (all(r["strictly_improved"] for r in rows) and mean is not None and mean >= .20) if q15 else all(r["not_worse"] for r in rows)
                checks.append({"horizon": horizon, "channel_index": channel, "rule": "each_seed_strict_and_mean_ge_20pct" if q15 else "each_seed_not_worse",
                               "seed_records": rows, "mean_relative_improvement": mean, "passed": bool(passed)})
        evaluated = (h1["all_requested_exact"] and result["all_192_fixed_groups_full"]
                     and all(r["full_fixed_counts"] for c in checks for r in c["seed_records"]))
        result["by_source"][source] = {"evaluated": bool(evaluated), "sensitivity_rule_passed": bool(evaluated and all(c["passed"] for c in checks)),
                                      "checks": checks, "meaning": "privileged_hybrid_replay_sensitivity_not_causal_identification", **FLAGS}
    result["oracle_route_closed_after_V"] = True
    result["next_work"] = "bounded_new_physics_design_with_a_justified_mechanism_and_frozen_complete_control_gate"
    return result


def self_check(cost, cases):
    """Only six new layer fixtures; no frozen mapping, fit or source scientific replay."""
    def attempt(name):
        event = {"case": name, "status": "attempted"}
        cases.append(event)
        return event
    initial = np.arange(22, dtype=float)
    requests, ids = [[0.]*8]*3, ["fixture:0", "fixture:1", "fixture:2"]
    observed, used = [], []
    def step(x, previous, request):
        observed.append((x.copy(), previous.copy()))
        candidate = x+1.
        return {"available": True, "terminal_x22": candidate.tolist(), "terminal_previous_v2": x[8:10].tolist()}
    def label(origin, expected):
        used.append((origin, expected))
        return np.full(18, 100.+origin), {"endpoint_transition_id": expected}
    event = attempt("nonterminal18_only_controlled4_and_terminal18_preserved")
    paid = Counter()
    result = oracle_rollout(initial, [-3., -4.], requests, ids, 0, step, label, paid, "synthetic")
    assert result["available"] and len(used) == 2 and len(result["oracle_replacements"]) == 2
    assert result["controlled_terminal4"] == (initial[list(CONTROLLED)]+3.).tolist()
    assert np.array_equal(np.asarray(result["terminal_x22"])[list(ORACLE)], np.full(18, 102.))
    assert paid["synthetic_future18_scalar_uses"] == 36 and paid["synthetic_full22_forward_returns"] == 3
    event["status"] = "passed"; cost.update(paid)
    event = attempt("legal_initial_previous_then_predicted_old_current_controlled_velocity")
    assert observed[0][1].tolist() == [-3., -4.]
    assert observed[1][1].tolist() == initial[8:10].tolist()
    assert observed[2][1].tolist() == (initial[8:10]+1.).tolist()
    assert result["terminal_previous_v2"] == (initial[8:10]+2.).tolist()
    event["status"] = "passed"
    event = attempt("H1_never_queries_oracle_and_is_exact_original_controlled_output")
    paid = Counter()
    def forbidden(*args):
        raise AssertionError("terminal_label_must_not_be_queried")
    result = oracle_rollout(initial, [-3., -4.], requests[:1], ids[:1], 0, step, forbidden, paid, "synthetic")
    assert result["available"] and result["terminal_x22"] == (initial+1.).tolist() and not result["oracle_replacements"]
    assert paid["synthetic_oracle_label_attempts"] == 0
    event["status"] = "passed"; cost.update(paid)
    event = attempt("all22_nonfinite_tail_rejected_before_oracle_can_mask_it")
    paid = Counter()
    def nonfinite_step(x, previous, request):
        candidate = (x+1.).tolist(); candidate[2] = float("nan")
        return {"available": True, "terminal_x22": candidate, "terminal_previous_v2": x[8:10].tolist()}
    result = oracle_rollout(initial, [-3., -4.], requests[:2], ids[:2], 0, nonfinite_step, forbidden, paid, "synthetic")
    assert not result["available"] and paid["synthetic_oracle_label_attempts"] == 0
    assert failure_json_safe(result)["failed_step"]["frozen_full22_step"]["terminal_x22"][2] == {"nonfinite_float": "NaN"}
    event["status"] = "passed"; cost.update(paid)
    event = attempt("missing_native_label_keeps_paid_forward_and_unavailable_denominator")
    paid = Counter()
    def missing(*args):
        raise ValueError("oracle_label_missing_or_ambiguous_source_record")
    result = oracle_rollout(initial, [-3., -4.], requests[:2], ids[:2], 0, step, missing, paid, "synthetic")
    assert not result["available"] and len(result["predicted_preoverwrite_path_x22"]) == 1
    assert paid["synthetic_full22_forward_returns"] == 1 and paid["synthetic_future18_scalar_uses"] == 0
    assert result["partial_previous_v2"] == initial[8:10].tolist()
    event["status"] = "passed"; cost.update(paid)
    event = attempt("cross_trial_or_mismatched_native_label_has_no_source_fallback")
    paid = Counter()
    row = {"seed": 0, "predictor": "U22", "trial_id": "seed0_prediction", "origin": 0, "horizon": 1,
           "history_transition_ids": ["seed0_prediction:98", "seed0_prediction:99"],
           "requested_transition_ids": ["seed0_prediction:100"], "requested_sequence8": requests[:1],
           "initial_x22": initial.tolist(), "previous_v2": [-3., -4.], "actual_endpoint_x22": (initial+50.).tolist(),
           "available": True, "scored": True, "source_stopped_at_endpoint": False}
    indexed = {(0, "U22", 1, 0): [row]}
    def mismatched(origin, expected):
        return native_label(indexed, 0, origin, "seed1_prediction:100")
    result = oracle_rollout(initial, [-3., -4.], requests[:2], ids[:2], 0, step, mismatched, paid, "synthetic")
    assert not result["available"] and paid["synthetic_future18_scalar_uses"] == 0
    assert "endpoint_ID_differs" in result["reason"]
    event["status"] = "passed"; cost.update(paid)


def write_outputs(output, parameters, predictions, metrics, run):
    payloads = {"parameters.json": json_bytes(failure_json_safe(parameters)),
                "metrics.json": json_bytes(failure_json_safe(metrics)), "run.json": json_bytes(failure_json_safe(run)),
                "predictions.jsonl.gz": gzip.compress(b"".join((json.dumps(failure_json_safe(row), ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
                                                          for row in predictions), mtime=0)}
    if run.get("failure"):
        payloads["failure.json"] = json_bytes(failure_json_safe(run))
    files = {}
    for name, data in payloads.items():
        (output/name).write_bytes(data)
        files[name] = identity(data)
    (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": run["status"],
                                                   "diagnostic_only": True, **FLAGS, "files": files}))


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    original = (repo/U_ROOT).resolve()
    if output.is_relative_to(original) or original.is_relative_to(output):
        raise ValueError("input_output_must_not_overlap")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    zero_keys = ("physics_calls", "physics_substeps", "RLS_updates", "MPC_calls", "fit_attempts",
                 "objective_calculation_attempts", "gradient_calculation_attempts", "K22_restorations", "D11_restorations",
                 "saved_self_forward_calls", "saved_self_error_recalculations", "saved_self_metric_recalculations",
                 "oracle_full22_forward_attempts", "oracle_full22_forward_returns", "oracle_full22_forward_failures",
                 "oracle_nonterminal18_overwrites", "oracle_future18_scalar_uses")
    cost = Counter({key: 0 for key in zero_keys})
    files, inputs, parameters, predictions, cases, groups = {}, {}, [], [], [], []
    models, source_run, h1, rule = {}, None, None, None
    status, failure, source_verified = "failed", None, False
    try:
        sources(repo, args.source_commit, cost, files, args.self_check)
        source_verified = not args.self_check
        if args.self_check:
            self_check(cost, cases)
            status = "self_check_passed"
        else:
            helper, support, core, q_support = load_helpers(repo, cost)
            docs, blob, source_run = read_inputs(repo, inputs, cost, files, support)
            guards = public_guards(source_run)
            models = restore_weights(helper, core, q_support, docs["raw/parameters.json"], guards, cost, parameters)
            indexed = parse_saved(blob, cost)
            h1 = evaluate(core, q_support, indexed, models, cost, predictions)
            for record in parameters:
                seed = record["seed"]
                for source, weights in models[seed].get("weights", {}).items():
                    after = helper.Q_parameter_fingerprint(core, q_support, models[seed]["qref8"], weights)
                    record[source+"_fingerprint_after"] = after
                    if after != record[source+"_fingerprint_before"]:
                        raise ValueError("frozen_source_weights_mutated:"+source)
            groups = summarize(core, predictions, docs["raw/metrics.json"], cost)
            rule = diagnostic_rule(groups, h1)
            status = "completed"
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    for target, suffix in (("oracle_full22_forward_attempts", "full22_forward_attempts"),
                           ("oracle_full22_forward_returns", "full22_forward_returns"),
                           ("oracle_rollout_step_failures", "oracle_rollout_step_failures"),
                           ("oracle_nonterminal18_overwrites", "nonterminal18_overwrites"),
                           ("oracle_future18_scalar_uses", "future18_scalar_uses")):
        cost[target] = sum(cost[source+"_oracle18_"+suffix] for source in ("Q22", "U22"))
    cost["oracle_full22_forward_failures"] = cost["oracle_full22_forward_attempts"]-cost["oracle_full22_forward_returns"]
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    run = {"status": status, "self_check": args.self_check,
           "source": {"commit": args.source_commit, "files": files, "clean_committed_bytes_verified": source_verified},
           "inputs": inputs, "input_binding_source_commit": U_COMMIT, "fixed_budget": FIXED_BUDGET,
           "runtime": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
           "public_guard_source": f"{U_ROOT}/raw/run.json:baseline_restorations.D11[].public_guard",
           "source_public_guard_only_no_D_model_restoration": True,
           "H1_identity": h1, "self_check_cases": cases, "cost": dict(cost), "failure": failure,
           "diagnostic_only": True, "privileged_future18": True, "hybrid_state_physical_consistency_guaranteed": False,
           "initial_history_source": "same_saved_legal_continuous_window_previous_v2",
           "later_history_source": "predicted_old_current_controlled_v_only",
           "terminal18_overwritten": False, "terminal18_scored": False,
           "saved_self_recalculated": False, "C_fallback_reads": 0, "oracle_route_closed_after_V": True,
           "source_cumulative_cost_reference": f"{U_ROOT}/raw/run.json:cost",
           "source_cumulative_cost_transcribed": source_run.get("cost") if source_run else "unknown_before_source_metadata_return",
           "timing_excludes": "final_output_serialization_compression_and_write", **FLAGS}
    metrics = {"status": status, "groups": groups, "diagnostic_rule": rule, "H1_identity": h1,
               "diagnostic_only": True, "partial_subset_method_ranking": False, **FLAGS}
    write_outputs(output, parameters, predictions, metrics, run)
    print(json.dumps({"status": status, "output": str(output), "cost": dict(cost), "failure": failure and
                      {key: failure[key] for key in ("type", "message")}, **FLAGS}, allow_nan=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit")
    parser.add_argument("--output", required=True)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if not args.self_check and not args.source_commit:
        parser.error("--source-commit required for formal execution")
    raise SystemExit(main_run(args))
