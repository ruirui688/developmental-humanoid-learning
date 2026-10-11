#!/usr/bin/env python3
"""O: saved-endpoint diagnostics only; no model imports, fits, or physics."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = "results/cpu_validation/2026-10-11_guard_scaled_native_transition/raw"
PINS = {
    "manifest.json": (646, "f393ee50b6f8de6d33264eee4ea9a20ca3328ea5a1d545d93a54240d37c36570"),
    "run.json": (12866, "f4a40fe58caae01f91df0678dbd6eff1def4aa8bc20a9fac076bb6fcf13bb9ff"),
    "predictions.jsonl": (16304217, "23c3c78afc4ba301a700cb0e4ad73fa6bc24a5c0072b7136f2933eacf058aff7"),
}
SCHEMA_SOURCES = {
    "scripts/develop_guard_scaled_native_transition.py": (27537, "df0833d08e722391f98de1bc2cbf81e2d0a866a3ea65def24e9b216d25787518"),
    "scripts/develop_guard_native_transition.py": (36390, "f910bb6fd9f01ebf5fd52426b40b43414e50bebcfe6460cf6132bccb1a2192bb"),
}
CANONICAL = ("scripts/diagnose_guard_saved_recursion.py", "docs/GUARD_SAVED_RECURSION_DIAGNOSTIC_PROTOCOL.md")
N_COMMIT = "74725ea22ec1e9a12085a1fa70ce228e848c761f"
PREDICTORS = ("N22", "K22", "D11")
CHANNELS = (("q0", 0, "rad"), ("q1", 1, "rad"), ("v0", 8, "rad/s"), ("v1", 9, "rad/s"))
PHASES = ("persistent_zero", "onset", "hold", "release", "change", "trial_first", "unavailable_request_history")
TOL = 1e-12


def identity(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("nonfinite_or_nonnumeric_scalar")
    return float(value)


def vector(value, n):
    if not isinstance(value, list) or len(value) != n:
        raise ValueError(f"vector_length_{n}_required")
    return tuple(finite(x) for x in value)


def close(a, b, cost):
    cost["coordinate_abs_difference_checks"] += 1
    return abs(a-b) <= TOL


def parse(raw, cost):
    cost["json_parse_attempts"] += 1
    value = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    cost["json_parse_returns"] += 1
    return value


def read(path, cost, inputs, key):
    cost["input_file_read_attempts"] += 1
    raw = path.read_bytes()
    cost["input_file_read_returns"] += 1
    cost["input_raw_bytes"] += len(raw)
    cost["input_hash_bytes"] += len(raw)
    inputs[key] = identity(raw)
    if inputs[key] != dict(zip(("bytes", "sha256"), PINS[key])):
        raise ValueError(f"input_pin_mismatch:{key}")
    return raw


def bind_sources(repo, commit, cost, journal):
    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError(f"git_query_failed:{args[0]}")
        cost["git_query_returns"] += 1
        return result.stdout
    if len(commit) != 40 or git("rev-parse", "HEAD").decode().strip() != commit:
        raise ValueError("exact_HEAD_required")
    if git("status", "--porcelain"):
        raise ValueError("clean_checkout_required")
    for name in CANONICAL:
        cost["source_file_read_attempts"] += 1
        raw = (repo/name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_raw_bytes"] += len(raw)
        journal[name] = identity(raw)
        if raw != git("show", f"{commit}:{name}"):
            raise ValueError(f"canonical_committed_bytes_differ:{name}")
    if Path(__file__).resolve() != (repo/CANONICAL[0]).resolve():
        raise ValueError("canonical_script_execution_required")


def index_records(raw, cost):
    index = {}
    for line in raw.splitlines():
        cost["prediction_line_attempts"] += 1
        row = parse(line, cost)
        seed, horizon, origin, predictor = (row[k] for k in ("seed", "horizon", "origin", "predictor"))
        if (any(type(x) is not int for x in (seed, horizon, origin)) or seed not in (0, 1, 2)
                or horizon not in (1, 2, 5, 15) or origin not in range(101-horizon) or predictor not in PREDICTORS):
            raise ValueError("unexpected_saved_record_identity")
        key = (seed, horizon, origin, predictor)
        if key in index:
            raise ValueError("duplicate_saved_record_identity")
        index[key] = row
        cost["prediction_line_returns"] += 1
    return index


def context(row, seed, origin, horizon, predictor, cost):
    cost["saved_record_validation_attempts"] += 1
    trial = f"seed{seed}_prediction"
    if (row.get("seed") != seed or row.get("origin") != origin or row.get("horizon") != horizon
            or row.get("predictor") != predictor or row.get("trial_id") != trial
            or row.get("available") is not True or row.get("scored") is not True
            or row.get("offline_saved_future_requests") is not True or row.get("source_stopped_at_endpoint") is not False):
        raise ValueError("saved_identity_or_availability_differs")
    if row["history_transition_ids"] != [f"{trial}:{98+origin}", f"{trial}:{99+origin}"]:
        raise ValueError("continuous_two_endpoint_history_required")
    if row["requested_transition_ids"] != [f"{trial}:{100+origin+j}" for j in range(horizon)]:
        raise ValueError("request_transition_IDs_differ")
    initial, actual, previous = vector(row["initial_x22"], 22), vector(row["actual_endpoint_x22"], 22), vector(row["previous_v2"], 2)
    if len(row["requested_sequence8"]) != horizon:
        raise ValueError("request_sequence_length_differs")
    requests = tuple(vector(x, 8) for x in row["requested_sequence8"])
    if predictor == "D11":
        saved_path = row["predicted_path_qv"]
        if not isinstance(saved_path, list) or len(saved_path) != horizon or any(not isinstance(x, list) or len(x) != 2 for x in saved_path):
            raise ValueError("complete_unfiltered_D11_path_required")
        if not isinstance(row["terminal_qv"], list) or len(row["terminal_qv"]) != 2:
            raise ValueError("D11_terminal_pair_shape_differs")
        path = tuple((*vector(x[0], 2), *vector(x[1], 2)) for x in saved_path)
        terminal = (*vector(row["terminal_qv"][0], 2), *vector(row["terminal_qv"][1], 2))
        errors = tuple(finite(row["terminal_errors_x22"][str(i)]) for _, i, _ in CHANNELS)
        cost["D11_saved_absolute_label_additions_requested"] += 4
        label = tuple(finite(x+y) for x, y in zip(terminal, errors))
        cost["D11_saved_absolute_label_additions_returned"] += 4
        if not all(close(label[j], actual[8+j-2], cost) for j in (2, 3)):
            raise ValueError("D11_absolute_velocity_label_differs")
    else:
        full_path = tuple(vector(x, 22) for x in row["predicted_path_x22"])
        if not full_path or full_path[-1] != vector(row["terminal_x22"], 22):
            raise ValueError("native_terminal_path_differs")
        path = tuple(tuple(x[i] for _, i, _ in CHANNELS) for x in full_path)
        terminal, label = path[-1], tuple(actual[i] for _, i, _ in CHANNELS)
    if len(path) != horizon or path[-1] != tuple(terminal):
        raise ValueError("complete_saved_path_required")
    cost["saved_record_validation_returns"] += 1
    return {"initial": initial, "actual": actual, "previous": previous, "requests": requests, "path": path, "label": label}


def phase(current, previous):
    if previous is None:
        return "trial_first"
    if current == 0:
        return "persistent_zero" if previous == 0 else "release"
    if previous == 0:
        return "onset"
    return "hold" if current == previous else "change"


def components(prediction, local_prediction, actual, cost):
    cost["decomposition_scalar_difference_requests"] += 3
    e, b, r = finite(prediction-actual), finite(local_prediction-actual), finite(prediction-local_prediction)
    cost["decomposition_scalar_difference_returns"] += 3
    cost["identity_residual_scalar_requests"] += 2
    residual = finite(e-(b+r))
    cost["identity_residual_scalar_returns"] += 2
    return (e, b, r, residual)


def summary(values, expected, cost):
    result = {"fixed_count": expected, "usable_count": len(values), "unavailable_count": expected-len(values), "complete": len(values) == expected}
    if not values:
        return {**result, "components": None, "cross_2_sum_br": None, "energy_identity_residual": None, "max_point_identity_residual": None}
    stats = {}
    for j, name in enumerate(("e", "b", "r")):
        v = [x[j] for x in values]
        cost["summary_scalar_square_requests"] += len(v)
        sq = math.fsum(finite(x*x) for x in v)
        cost["summary_scalar_square_returns"] += len(v)
        cost["summary_abs_requests"] += len(v)
        cost["summary_sum_input_uses"] += 3*len(v)
        cost["summary_division_requests"] += 3
        cost["summary_sqrt_requests"] += 1
        stats[name] = {"sum_sq": finite(sq), "bias": finite(math.fsum(v)/len(v)), "mae": finite(math.fsum(abs(x) for x in v)/len(v)), "rmse": finite(math.sqrt(sq/len(v)))}
    cost["cross_scalar_product_requests"] += len(values)
    cross = finite(2*math.fsum(finite(x[1]*x[2]) for x in values))
    cost["cross_scalar_product_returns"] += len(values)
    cost["cross_scale_requests"] += 1
    residual = finite(stats["e"]["sum_sq"]-(stats["b"]["sum_sq"]+stats["r"]["sum_sq"]+cross))
    return {**result, "components": stats, "cross_2_sum_br": cross, "energy_identity_residual": residual, "max_point_identity_residual": max(abs(x[3]) for x in values)}


def analyze(index, cost, records, groups, seeds=(0, 1, 2), h1_count=100, origins=86):
    cache, invalid = {}, {}
    def get(seed, h, t, p):
        key = (seed, h, t, p)
        if key not in cache:
            try:
                cache[key] = context(index[key], seed, t, h, p, cost)
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                cache[key] = None
                invalid[key] = f"{type(exc).__name__}:{exc}"
                cost["saved_record_unavailable"] += 1
        if cache[key] is None:
            raise ValueError(invalid[key])
        return cache[key]
    def one(seed, t, p):
        row = get(seed, 1, t, p)
        reference = get(seed, 1, t, "K22" if p == "N22" else "N22")
        for key in ("initial", "actual", "previous", "requests"):
            if row[key] != reference[key]:
                raise ValueError(f"cross_predictor_{key}_differs")
        if t:
            past = get(seed, 1, t-1, p)
            if past["actual"] != row["initial"] or row["previous"] != past["initial"][8:10]:
                raise ValueError("native_endpoint_or_previous_v_continuity_differs")
        if p == "D11":
            first = get(seed, 1, 0, p)
            cost["D11_coordinate_difference_requests"] += 4
            offsets = [row["label"][j]-row["actual"][j] for j in (0, 1)]
            first_offsets = [first["label"][j]-first["actual"][j] for j in (0, 1)]
            if not all(close(x, y, cost) for x, y in zip(offsets, first_offsets)):
                raise ValueError("D11_absolute_relative_coordinate_difference_not_constant")
        return row
    buckets, fixed = defaultdict(list), Counter()
    for seed in seeds:
        for t in range(h1_count):
            try:
                source = one(seed, t, "N22")
                previous = one(seed, t-1, "N22")["requests"][0] if t else None
                classes = tuple(phase(source["requests"][0][a], None if previous is None else previous[a]) for a in (0, 1))
                request = source["requests"][0]
            except (KeyError, TypeError, ValueError, ArithmeticError):
                classes, request = ("unavailable_request_history",)*2, None
            row = {"scope": "H1_request_conditions", "seed": seed, "origin": t, "phase_per_axis": classes, "known_request8": request, "guard_projection": "unavailable_not_saved", "predictors": {}}
            for p in PREDICTORS:
                for j, (name, _, _) in enumerate(CHANNELS):
                    fixed[("H1", seed, p, classes[j % 2], name)] += 1
                try:
                    local = one(seed, t, p)
                    values = {name: components(local["path"][0][j], local["path"][0][j], local["label"][j], cost) for j, (name, _, _) in enumerate(CHANNELS)}
                    row["predictors"][p] = {"available": True, "e_b_r_residual": values}
                    for j, (name, _, _) in enumerate(CHANNELS):
                        buckets[("H1", seed, p, classes[j % 2], name)].append(values[name])
                except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                    row["predictors"][p] = {"available": False, "reason": f"{type(exc).__name__}:{exc}"}
            records.append(row)
        for t in range(origins):
            for p in PREDICTORS:
                for k in range(1, 16):
                    row = {"scope": "common_H15_origins", "seed": seed, "origin": t, "k": k, "predictor": p, "endpoint_transition_id": f"seed{seed}_prediction:{99+t+k}", "available": False}
                    try:
                        roll, start, local = get(seed, 15, t, p), one(seed, t, p), one(seed, t+k-1, p)
                        if roll["initial"] != start["initial"] or roll["previous"] != start["previous"]:
                            raise ValueError("recursive_initial_or_history_differs")
                        for j in range(15):
                            if roll["requests"][j] != get(seed, 1, t+j, p)["requests"][0]:
                                raise ValueError("recursive_local_request_sequence_differs")
                        end = one(seed, t+14, p)
                        if roll["actual"] != end["actual"]:
                            raise ValueError("recursive_terminal_actual_differs")
                        if not all(close(x, y, cost) for x, y in zip(roll["label"], end["label"])):
                            raise ValueError("recursive_terminal_coordinate_labels_differ")
                        if roll["path"][0] != start["path"][0]:
                            raise ValueError("same_predictor_H1_path_differs")
                        cost["recursive_matched_H1_endpoint_uses"] += 1
                        cost["recursive_matched_H1_scalar_label_uses"] += 4
                        values = {name: components(roll["path"][k-1][j], local["path"][0][j], local["label"][j], cost) for j, (name, _, _) in enumerate(CHANNELS)}
                        row.update(available=True, e_b_r_residual=values)
                        for name, _, _ in CHANNELS:
                            buckets[("recursive", seed, p, k, name)].append(values[name])
                    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                        row["reason"] = f"{type(exc).__name__}:{exc}"
                    records.append(row)
        for scope, selectors in (("recursive", range(1, 16)), ("H1", PHASES)):
            for p in PREDICTORS:
                for selector in selectors:
                    for name, _, unit in CHANNELS:
                        key = (scope, seed, p, selector, name)
                        groups.append({"scope": scope, "seed": seed, "predictor": p, "k_or_phase": selector, "channel": name, "unit": unit, "squared_unit": f"({unit})^2", **summary(buckets[key], origins if scope == "recursive" else fixed[key], cost)})
    by_key = {(g["scope"], g["seed"], g["predictor"], g["k_or_phase"], g["channel"]): g for g in groups}
    differences = []
    for key, n in by_key.items():
        if key[2] != "N22":
            continue
        baseline = by_key[(key[0], key[1], "K22", key[3], key[4])]
        d = {"scope": key[0], "seed": key[1], "k_or_phase": key[3], "channel": key[4], "unit": n["squared_unit"], "available": n["complete"] and baseline["complete"] and n["usable_count"] > 0}
        if d["available"]:
            cost["N_minus_K_energy_difference_requests"] += 4
            d["sum_sq_differences"] = {x: finite(n["components"][x]["sum_sq"]-baseline["components"][x]["sum_sq"]) for x in ("e", "b", "r")}
            d["cross_2_sum_br_difference"] = finite(n["cross_2_sum_br"]-baseline["cross_2_sum_br"])
        else:
            d["reason"] = "empty_or_incomplete_fixed_group_no_ranking"
        differences.append(d)
    return differences


def self_check(cost, reports):
    """Small synthetic-only schema/alignment checks; journal expenses before asserts."""
    import copy
    event = {"case": "signed_cross_identity", "status": "attempted"}
    reports.append(event)
    value = components(2.0, 3.0, 0.0, cost)
    result = summary([value], 1, cost)
    assert value == (2.0, 3.0, -1.0, 0.0) and result["cross_2_sum_br"] == -6.0 and result["energy_identity_residual"] == 0.0
    event["status"] = "passed"
    def truth(t):
        x = [0.0]*22
        x[0], x[1], x[8], x[9] = .001*t, .002*t, .01*t, .02*t
        return x
    def command(t):
        return [[0.0, .125, .125, 0.0, -.125, .125, 0.0, 0.0][t % 8], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    fixture = {}
    for h, count in ((1, 16), (15, 2)):
        for t in range(count):
            for pi, p in enumerate(PREDICTORS):
                path = []
                for k in range(1, h+1):
                    x = truth(t+k)
                    for j, (_, ci, _) in enumerate(CHANNELS):
                        x[ci] += (.01, -.02, .03, -.04)[j]*(pi+1)*k
                    path.append(x)
                row = {"seed": 0, "origin": t, "horizon": h, "predictor": p, "trial_id": "seed0_prediction", "available": True, "scored": True, "offline_saved_future_requests": True, "source_stopped_at_endpoint": False, "initial_x22": truth(t), "actual_endpoint_x22": truth(t+h), "previous_v2": truth(t-1)[8:10], "history_transition_ids": [f"seed0_prediction:{98+t}", f"seed0_prediction:{99+t}"], "requested_transition_ids": [f"seed0_prediction:{100+t+j}" for j in range(h)], "requested_sequence8": [command(t+j) for j in range(h)]}
                if p == "D11":
                    row["predicted_path_qv"] = [[[x[0]+1.0, x[1]+2.0], [x[8], x[9]]] for x in path]
                    row["terminal_qv"] = row["predicted_path_qv"][-1]
                    terminal = [*row["terminal_qv"][0], *row["terminal_qv"][1]]
                    actual = truth(t+h)
                    absolute = (actual[0]+1.0, actual[1]+2.0, actual[8], actual[9])
                    row["terminal_errors_x22"] = {str(ci): a-b for (_, ci, _), a, b in zip(CHANNELS, absolute, terminal)}
                else:
                    row.update(predicted_path_x22=path, terminal_x22=path[-1])
                fixture[(0, h, t, p)] = row
                cost["synthetic_source_records_generated"] += 1
    event = {"case": "aligned_paths_coordinates_phases", "status": "attempted"}
    reports.append(event)
    rows, groups = [], []
    analyze(fixture, cost, rows, groups, seeds=(0,), h1_count=16, origins=2)
    assert len(rows) == 106 and all(g["complete"] for g in groups)
    assert {p for r in rows if r["scope"] == "H1_request_conditions" for p in r["phase_per_axis"]} >= set(PHASES[:6])
    event["status"] = "passed"
    event = {"case": "terminal_only_and_coordinate_request_history_rejection", "status": "attempted"}
    reports.append(event)
    bad = copy.deepcopy(fixture)
    del bad[(0, 15, 0, "K22")]["predicted_path_x22"]
    bad[(0, 15, 0, "N22")]["requested_sequence8"][0][0] = .25
    bad[(0, 1, 1, "D11")]["terminal_errors_x22"]["0"] += .01
    rows, groups = [], []
    analyze(bad, cost, rows, groups, seeds=(0,), h1_count=2, origins=1)
    assert all(not r["available"] for r in rows if r["scope"] == "common_H15_origins" and r["predictor"] in ("N22", "K22"))
    assert all(r["available"] == (r["k"] != 2) for r in rows if r["scope"] == "common_H15_origins" and r["predictor"] == "D11")
    for field, wrong in (("history_transition_ids", ["wrong", "wrong"]), ("requested_transition_ids", ["wrong"])):
        trial = copy.deepcopy(fixture[(0, 1, 0, "N22")])
        trial[field] = wrong
        try:
            context(trial, 0, 0, 1, "N22", cost)
        except ValueError:
            continue
        raise AssertionError(f"mismatched_{field}_accepted")
    malformed = copy.deepcopy(fixture[(0, 1, 0, "D11")])
    malformed["predicted_path_qv"].append(None)
    try:
        context(malformed, 0, 0, 1, "D11", cost)
    except ValueError:
        pass
    else:
        raise AssertionError("filtered_malformed_D11_path_accepted")
    event["status"] = "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit")
    parser.add_argument("--output", required=True)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if not args.source_commit and not args.self_check:
        parser.error("--source-commit is required")
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    if output == (repo/ROOT).resolve() or (repo/ROOT).resolve().is_relative_to(output):
        raise ValueError("output_must_not_contain_original_inputs")
    output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    cost = Counter({x: 0 for x in ("physics_calls", "physics_substeps", "RLS_updates", "MPC_calls", "model_calls", "fits", "old_metric_or_gate_recalculations")})
    inputs, source, records, groups, differences, failure = {}, {}, [], [], [], None
    checks = []
    source_verified = False
    status = "failed"
    try:
        if args.self_check:
            for name in CANONICAL:
                cost["source_file_read_attempts"] += 1
                raw = (repo/name).read_bytes()
                cost["source_file_read_returns"] += 1
                cost["source_raw_bytes"] += len(raw)
                source[name] = identity(raw)
            self_check(cost, checks)
            status = "self_check_passed"
        else:
            bind_sources(repo, args.source_commit, cost, source)
            source_verified = True
        if not args.self_check:
            manifest = parse(read(repo/ROOT/"manifest.json", cost, inputs, "manifest.json"), cost)
            saved_run = parse(read(repo/ROOT/"run.json", cost, inputs, "run.json"), cost)
        if args.self_check:
            saved_run, manifest = None, None
        else:
            if manifest.get("status") != "completed" or saved_run.get("status") != "completed" or saved_run["source"]["commit"] != N_COMMIT or saved_run["source"].get("clean_committed_bytes_verified") is not True:
                raise ValueError("completed_bound_N_run_required")
            for name, (size, digest) in SCHEMA_SOURCES.items():
                if saved_run["source"]["files"][name] != {"bytes": size, "sha256": digest}:
                    raise ValueError("N_schema_source_binding_differs")
            for name in ("run.json", "predictions.jsonl"):
                if manifest["files"][name] != dict(zip(("bytes", "sha256"), PINS[name])):
                    raise ValueError("N_manifest_payload_binding_differs")
            index = index_records(read(repo/ROOT/"predictions.jsonl", cost, inputs, "predictions.jsonl"), cost)
            cost["saved_prediction_records_indexed"] = len(index)
            differences = analyze(index, cost, records, groups)
            status = "completed" if all(g["complete"] for g in groups) else "completed_with_unavailable"
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
    diagnostics = {"status": status, "self_check": args.self_check, "self_check_cases": checks, "error_convention": "predicted_minus_actual; original_N_terminal_errors_have_opposite_sign", "group_components": groups, "N_minus_K": differences, "D11_scope": "descriptive_absolute_coordinates_only", "guard_projection": "unavailable_not_saved", "qref_value_verification": "not_saved; shared_N_K_coordinate_system_bound_by_N_source_and_exact_initial_actual_matching", "scientific_adoption": False, "c4_scientific_validation": False, "c5_scientific_dependency_released": False}
    payloads = {}
    for name, raw in (("records.jsonl", b"".join((json.dumps(r, allow_nan=False)+"\n").encode() for r in records)), ("diagnostics.json", (json.dumps(diagnostics, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode())):
        (output/name).write_bytes(raw)
        payloads[name] = identity(raw)
    cost["record_rows_written"] = len(records)
    cost["diagnostic_groups_written"] = len(groups)
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    run = {"status": status, "self_check": args.self_check, "requested_source_commit": args.source_commit, "source": {"files": source, "clean_committed_bytes_verified": source_verified}, "inputs": inputs, "runtime": {"python": sys.version.split()[0], "platform": sys.platform}, "cost": dict(cost), "failure": failure, "scientific_adoption": False, "c4_scientific_validation": False, "c5_scientific_dependency_released": False, "timing_excludes": "final run/manifest serialization and writes"}
    raw = (json.dumps(run, indent=2, allow_nan=False)+"\n").encode()
    (output/"run.json").write_bytes(raw)
    payloads["run.json"] = identity(raw)
    (output/"manifest.json").write_bytes((json.dumps({"schema_version": 1, "status": status, "scientific_adoption": False, "files": payloads}, indent=2)+"\n").encode())
    print(json.dumps({"status": status, "output": str(output), "cost": dict(cost), "failure": failure}))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
