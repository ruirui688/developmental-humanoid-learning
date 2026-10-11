"""M: fixed archived K/L matrix geometry; new offline projections, no controller."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np


SOURCE_PATH = "scripts/diagnose_guard_design_geometry.py"
PROTOCOL_PATH = "docs/GUARD_DESIGN_GEOMETRY_DIAGNOSTIC_PROTOCOL.md"
K_ROOT = "results/cpu_validation/2026-10-11_guard_native_transition/raw"
L_ROOT = "results/cpu_validation/2026-10-11_guard_native_augmentation/model_computation_02/raw"
L_FAILED_ROOT = "results/cpu_validation/2026-10-11_guard_native_augmentation"
C_ROOT = "results/cpu_validation/2026-10-11_guard_exploration/raw"
D_ROOT = "results/cpu_validation/2026-10-11_guard_lag_offline"
COMMITS = {"C": "5ea8df42b09588845760daf0dc1f270aef2a87f1",
           "D": "f7710c7b048dccab3e436d1fa16432f881a35992",
           "G": "91dcf6c111a87427c8f3fdd8b959d4792b1bb5a2",
           "K": "b46c6d37fddc8e6534384168fb76663bc2c5236c",
           "L": "3bbc34d05e83162cb052590e84981e3c690f9bd4"}
PINS = {
    f"{K_ROOT}/manifest.json": (921, "f8bf006eac1615e2a1bee801926c6157f265836011a847c24d19fe0f7341a588"),
    f"{K_ROOT}/run.json": (7106, "1ea85a61e1b6ecbc43770c52ce6a3435c0e4d919d8af5fc91bc317b7abc84b3e"),
    f"{K_ROOT}/parameters.json": (5053433, "1a5c426cfece2fe099ba2e13bfe6229ef7189f59870183620fcb1e1aa14de0aa"),
    f"{L_ROOT}/manifest.json": (918, "146ed37a3e70b61d57addd646f91a85d4dea14785580146e006b38f1754457de"),
    f"{L_ROOT}/run.json": (10949, "d4a9b3687592a63c0bcb4ada65bd1c1e693be1c1690957a9e267a72ff2366e1b"),
    f"{L_ROOT}/parameters.json": (4418111, "d0602e0de156b478cd61e8c5886d02380143a790778c43627c219881acbefc55"),
    f"{L_FAILED_ROOT}/manifest.json": (3200, "368354d9e36675b9f5782e5afa8fc358983eaabb0f7c644fe8779a2b29681cc1"),
}
FAILED_BINDINGS = {
    "raw/failure.json": (7537, "f5ff0de23d00da60b411695091c09d864cb6e8078c3efb59dc26a6da2a63798a"),
    "raw/manifest.json": (768, "6e73de28b8de76515196b9091ee62d7c412ff3b7642c34d80ae30b05756ec509"),
}
STATE_NAMES = tuple([f"q{i}-qref{i}" for i in range(8)] + [f"v{i}" for i in range(8)]
                    + ["gyro_x", "gyro_y", "gyro_z", "accel_x/9.81", "accel_y/9.81", "accel_z/9.81"])
FEATURE_NAMES = (*STATE_NAMES, "startG0", "startG1", "hinge_startG0_.25", "hinge_startG1_.25",
                 "1", "v0-previous_v0", "v1-previous_v1")
STATE_UNITS = ("rad",)*8 + ("rad/s",)*11 + ("dimensionless (/g)",)*3
FEATURE_UNITS = (*STATE_UNITS, "Nm", "Nm", "Nm", "Nm", "dimensionless", "rad/s", "rad/s")
A_COLUMNS = (22, 23, 24, 25)
Z_COLUMNS = (*range(22), 26, 27, 28)
SEEDS, RIDGE = (0, 1, 2), .01


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")


def identity(data):
    return {"bytes": len(data), "sha256": digest(data)}


def same_identity(binding, actual):
    return isinstance(binding, dict) and all(binding.get(k) == actual[k] for k in ("bytes", "sha256"))


def frozen_sources(repo, commit, cost):
    """Only read-only Git queries at formal execution; no model imports."""
    if (len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit)
            or Path(__file__).resolve() != (repo/SOURCE_PATH).resolve()):
        raise ValueError("exact M commit and canonical script path required")
    def git(*args):
        cost["git_query_attempts"] += 1
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
        cost["git_query_returns"] += 1
        cost["git_return_bytes"] += len(result.stdout)+len(result.stderr)
        if result.returncode:
            raise ValueError("read-only source verification failed")
        return result.stdout
    if (git("rev-parse", "HEAD").decode().strip() != commit
            or git("status", "--porcelain", "--untracked-files=no").strip()):
        raise ValueError("clean exact M HEAD required")
    files = {}
    for name in (SOURCE_PATH, PROTOCOL_PATH):
        cost["source_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["source_file_read_returns"] += 1
        cost["source_raw_bytes"] += len(data)
        files[name] = identity(data)
        if git("show", f"{commit}:{name}") != data:
            raise ValueError(f"M source byte mismatch: {name}")
    return {"commit": commit, "files": files, "clean_committed_bytes_verified": True}


def read_inputs(repo, records, cost):
    """Actual matrices are read only by the frozen formal run."""
    docs = {}
    for name, (size, sha) in PINS.items():
        cost["input_file_read_attempts"] += 1
        data = (repo/name).read_bytes()
        cost["input_file_read_returns"] += 1
        cost["input_raw_bytes"] += len(data)
        cost["input_hash_bytes"] += len(data)
        records[name] = identity(data)
        if records[name] != {"bytes": size, "sha256": sha}:
            raise ValueError(f"pinned input mismatch: {name}")
        cost["json_parse_attempts"] += 1
        docs[name] = json.loads(data)
        cost["json_parse_returns"] += 1
    krun, lrun = docs[f"{K_ROOT}/run.json"], docs[f"{L_ROOT}/run.json"]
    for label, root, run, originals in (("K", K_ROOT, krun, ("C", "D")),
                                       ("L", L_ROOT, lrun, ("C", "D", "G", "K"))):
        manifest = docs[f"{root}/manifest.json"]
        if (manifest.get("status") != "completed" or run.get("status") != "completed"
                or run.get("source", {}).get("commit") != COMMITS[label]
                or run["source"].get("clean_committed_bytes_verified") is not True
                or run.get("original_source_commits") != {k: COMMITS[k] for k in originals}):
            raise ValueError(f"{label} clean completed source identity mismatch")
        for name in ("run.json", "parameters.json"):
            if not same_identity(manifest["files"][name], records[f"{root}/{name}"]):
                raise ValueError(f"{label} raw manifest payload mismatch")
    original_paths = (f"{C_ROOT}/manifest.json", f"{C_ROOT}/metadata.json", f"{C_ROOT}/trace.jsonl.gz",
                      f"{D_ROOT}/manifest.json", f"{D_ROOT}/raw/manifest.json", f"{D_ROOT}/raw/diagnostics.json")
    for name in original_paths:
        if not same_identity(krun["inputs"][name], lrun["inputs"][name]):
            raise ValueError("K/L original C/D input identities differ")
    for name in ("manifest.json", "run.json", "parameters.json"):
        if not same_identity(lrun["inputs"][f"{K_ROOT}/{name}"], records[f"{K_ROOT}/{name}"]):
            raise ValueError("L original K input identity differs")
    failed_manifest = docs[f"{L_FAILED_ROOT}/manifest.json"]
    for name, (size, sha) in FAILED_BINDINGS.items():
        binding = failed_manifest["files"][name]
        if (not same_identity(binding, {"bytes": size, "sha256": sha})
                or binding.get("copy_verified") is not True):
            raise ValueError("L first failed-source archive identity differs")
    return docs


def finite_array(value, shape):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f"finite float64 array {shape} required; got {array.shape}")
    return array


def datasets(docs, cost):
    """Validate all six and shared C bytes/IDs before any projection; no repair."""
    payloads = {"K": docs[f"{K_ROOT}/parameters.json"], "L": docs[f"{L_ROOT}/parameters.json"]}
    for records in payloads.values():
        if not isinstance(records, list) or len(records) != 3 or [r.get("seed") for r in records] != list(SEEDS):
            raise ValueError("exact three ordered seed records required")
    selected = []
    for seed in SEEDS:
        pair = {}
        cids = [f"seed{seed}_calibration_sparse:{i}" for i in range(100, 500)]
        gids = [f"seed{seed}_PDselected:{i}" for i in range(100, 300)]
        for label, count in (("K", 400), ("L", 600)):
            record = payloads[label][seed]
            ids = cids if label == "K" else cids+gids
            if (record.get("available") is not True or record.get("fixed_lambda") != RIDGE
                    or record.get("state_order") != list(STATE_NAMES)
                    or record.get("feature_order") != list(FEATURE_NAMES)
                    or record.get("training_transition_ids") != ids):
                raise ValueError(f"{label} seed{seed} definition/ID mismatch")
            if label == "K":
                if (record.get("training_usable_count") != 400 or record.get("training_source_active_count") != 400):
                    raise ValueError("K complete C400 required")
                phi, delta = record["fit"]["phi400x29"], record["fit"]["delta_labels400x22"]
            else:
                if (record.get("qualified_training_count") != 600
                        or record.get("training_collection_labels") != ["C"]*400+["G"]*200):
                    raise ValueError("L ordered C400+G200 required")
                phi, delta = record["phi600x29"], record["delta_labels600x22"]
            qref = finite_array(record["qref8"], (8,))
            phi = finite_array(phi, (count, 29))
            delta = finite_array(delta, (count, 22))
            weights = finite_array(record["fit"]["weights29x22"], (29, 22))
            cost["validated_archived_design_scalars"] += int(phi.size)
            cost["validated_archived_native_label_scalars"] += int(delta.size)
            cost["validated_archived_weight_scalars"] += int(weights.size)
            pair[label] = {"seed": seed, "collection": label, "count": count, "ids": ids,
                           "qref": qref, "phi": phi, "delta": delta, "weights": weights}
        if (not np.array_equal(pair["K"]["phi"], pair["L"]["phi"][:400])
                or not np.array_equal(pair["K"]["delta"], pair["L"]["delta"][:400])
                or not np.array_equal(pair["K"]["qref"], pair["L"]["qref"])):
            raise ValueError(f"seed{seed} K400 and L first400 differ; comparison forbidden")
        selected.extend((pair["K"], pair["L"]))
    return selected


def svd(matrix, name, cost, operations):
    event = {"kind": "svd", "name": name, "input_shape": list(matrix.shape),
             "input_scalars": int(matrix.size), "full_matrices": False, "status": "attempted"}
    operations.append(event)
    cost["svd_attempts"] += 1
    try:
        u, s, vt = np.linalg.svd(matrix, full_matrices=False)
        event.update(status="returned", output_shapes=[list(a.shape) for a in (u, s, vt)],
                     output_scalars=sum(int(a.size) for a in (u, s, vt)))
        cost["svd_returns"] += 1
        if not all(np.isfinite(a).all() for a in (u, s, vt)):
            raise ValueError("nonfinite SVD output")
        tol = float(np.finfo(np.float64).eps*max(matrix.shape)*(float(s[0]) if s.size else 0.))
        rank = int(np.count_nonzero(s > tol))
        event.update(rank=rank, tolerance=tol)
        return u[:, :rank], s, vt, {"singular_values": s.tolist(), "rank": rank,
            "tolerance": tol, "discarded_singular_values": s[rank:].tolist()}
    except BaseException as exc:
        event["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        cost["svd_failures"] += 1
        raise


def multiply(left, right, name, cost, operations, response_kind=None):
    rows, inner, columns = left.shape[0], left.shape[1], right.shape[1]
    event = {"kind": "matmul", "name": name, "left_shape": list(left.shape),
             "right_shape": list(right.shape), "output_shape": [rows, columns],
             "left_input_scalars": int(left.size), "right_input_scalars": int(right.size),
             "output_scalars": rows*columns, "logical_multiplications_requested": rows*inner*columns,
             "logical_additions_requested": rows*columns*max(inner-1, 0), "status": "attempted"}
    operations.append(event)
    cost["matmul_attempts"] += 1
    cost["logical_matmul_multiplications_requested"] += event["logical_multiplications_requested"]
    cost["logical_matmul_additions_requested"] += event["logical_additions_requested"]
    if response_kind:
        event["response_kind"] = response_kind
        event["response_scalars"] = int(right.size)
        cost[f"{response_kind}_scalar_uses_requested"] += int(right.size)
    try:
        result = left @ right
        event["status"] = "returned"
        cost["matmul_returns"] += 1
        cost["matmul_output_scalars_returned"] += int(result.size)
        if response_kind:
            cost[f"{response_kind}_scalar_uses_returned"] += int(right.size)
        if not np.isfinite(result).all():
            raise ValueError("nonfinite matrix product")
        return result
    except BaseException as exc:
        event["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        cost["matmul_failures"] += 1
        raise


def output_summaries(floor, shrink, saved, subsets):
    result = []
    for name, section in subsets:
        f, s, r = floor[section], shrink[section], saved[section]
        for column, (channel, unit) in enumerate(zip(STATE_NAMES, STATE_UNITS)):
            fv, sv, rv = f[:, column], s[:, column], r[:, column]
            result.append({"subset": name, "count": len(fv), "output_index": column,
                "output": channel, "delta_unit": unit, "squared_energy_unit": f"({unit})^2",
                "scientific_focus": column in (0, 1, 8, 9),
                "floor_squared_energy": float(np.sum(fv*fv)),
                "shrink_squared_energy": float(np.sum(sv*sv)),
                "twice_floor_shrink_cross_term": float(2*np.sum(fv*sv)),
                "reconstructed_squared_energy": float(np.sum((fv+sv)**2)),
                "saved_ridge_squared_energy": float(np.sum(rv*rv)),
                "max_abs_residual_identity_discrepancy": float(np.max(np.abs(fv+sv-rv)))})
    return result


def diagnose(dataset, cost, operations, result):
    """Six products and three SVDs per full dataset; subgroups never refit."""
    phi, delta, weights = dataset["phi"], dataset["delta"], dataset["weights"]
    count = dataset["count"]
    name = f"seed{dataset['seed']}_{dataset['collection']}{count}"
    result.update(name=name, seed=dataset["seed"], collection=dataset["collection"], count=count,
                  full_training_transition_ids=dataset["ids"], status="started")
    ur, singular, _, spectrum = svd(phi, f"{name}:Phi", cost, operations)
    result["full_design_spectrum"] = spectrum
    cost["native_projection_estimation_attempts"] += 1
    try:
        coordinates = multiply(ur.T, delta, f"{name}:UrT_Delta", cost, operations,
                               response_kind="native_projection_label")
        projected = multiply(ur, coordinates, f"{name}:Ur_coordinates", cost, operations)
        floor = delta-projected
    except BaseException:
        cost["native_projection_estimation_failures"] += 1
        raise
    cost["native_projection_estimation_returns"] += 1
    result["floor"] = floor.tolist()
    retained = singular[:spectrum["rank"]]
    factors = RIDGE/(retained**2+RIDGE)
    shrink = multiply(ur, factors[:, None]*coordinates, f"{name}:Ur_shrink_coordinates", cost, operations)
    result["shrink"] = shrink.tolist()
    saved_forward = multiply(phi, weights, f"{name}:Phi_archived_W", cost, operations)
    cost["archived_ridge_forward_output_scalars_returned"] += int(saved_forward.size)
    saved = delta-saved_forward
    result["saved_ridge_residual"] = saved.tolist()
    subsets = [("ALL", slice(None)), ("C400", slice(0, 400))]
    if dataset["collection"] == "L":
        subsets.append(("G200", slice(400, 600)))
    result["output_summaries"] = output_summaries(floor, shrink, saved, subsets)
    result["feature_column_scales"] = [{"index": i, "feature": feature, "unit": unit,
        "squared_energy": float(np.sum(phi[:, i]**2)), "mean_square": float(np.mean(phi[:, i]**2))}
        for i, (feature, unit) in enumerate(zip(FEATURE_NAMES, FEATURE_UNITS))]
    action, context = phi[:, A_COLUMNS], phi[:, Z_COLUMNS]
    uz, _, _, zspectrum = svd(context, f"{name}:Z", cost, operations)
    result["context_spectrum"] = zspectrum
    cost["command_projection_estimation_attempts"] += 1
    try:
        action_coordinates = multiply(uz.T, action, f"{name}:UzT_A", cost, operations,
                                      response_kind="command_projection_response")
        conditional = action-multiply(uz, action_coordinates, f"{name}:Uz_action_coordinates", cost, operations)
    except BaseException:
        cost["command_projection_estimation_failures"] += 1
        raise
    cost["command_projection_estimation_returns"] += 1
    result["conditional_action"] = conditional.tolist()
    _, _, avt, aspectrum = svd(conditional, f"{name}:A_perp", cost, operations)
    result["conditional_action_spectrum"] = dict(aspectrum, right_singular_directions_Vt=avt.tolist())
    raw_energy, residual_energy = np.sum(action**2, axis=0), np.sum(conditional**2, axis=0)
    result["action_column_energies"] = [{"feature_index": index, "feature": FEATURE_NAMES[index], "unit": "Nm",
        "raw_squared_energy": float(raw_energy[j]), "conditional_squared_energy": float(residual_energy[j]),
        "raw_mean_square": float(raw_energy[j]/count), "conditional_mean_square": float(residual_energy[j]/count),
        "conditional_energy_retained_ratio": float(residual_energy[j]/raw_energy[j]) if raw_energy[j] > 0 else None}
        for j, index in enumerate(A_COLUMNS)]
    result["status"] = "completed"
    cost["datasets_completed"] += 1


def main_run(args):
    repo, output = Path(args.repo).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    cpu_started = time.process_time()
    cost = Counter({key: 0 for key in ("svd_attempts", "svd_returns", "svd_failures", "matmul_attempts",
        "matmul_returns", "matmul_failures", "native_projection_label_scalar_uses_requested",
        "native_projection_label_scalar_uses_returned", "command_projection_response_scalar_uses_requested",
        "command_projection_response_scalar_uses_returned", "archived_ridge_forward_output_scalars_returned",
        "native_projection_estimation_attempts", "native_projection_estimation_returns", "native_projection_estimation_failures",
        "command_projection_estimation_attempts", "command_projection_estimation_returns", "command_projection_estimation_failures",
        "validated_archived_native_label_scalars", "validated_archived_weight_scalars", "datasets_completed",
        "physics_control_calls", "physics_substeps", "RLS_updates", "MPC_calls", "model_restores",
        "recursive_forecast_calls", "new_parameter_space_coefficients")})
    inputs, source, operations, results = {}, None, [], []
    input_qualification = "unknown_before_validator_returned"
    status, failure = "failed", None
    try:
        source = frozen_sources(repo, args.source_commit, cost)
        docs = read_inputs(repo, inputs, cost)
        selected = datasets(docs, cost)
        input_qualification = "all_six_validated_and_K400_L_first400_exactly_equal_each_seed"
        for dataset in selected:
            result = {}
            results.append(result)
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                diagnose(dataset, cost, operations, result)
        status = "completed"
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    wall_seconds, cpu_seconds = time.perf_counter()-started, time.process_time()-cpu_started
    cost["wall_seconds_before_serialization"] = wall_seconds
    cost["cpu_process_seconds_before_serialization"] = cpu_seconds
    diagnostics = {"schema_version": 1, "status": status, "fixed_lambda": RIDGE,
        "computation_type": "new_offline_unregularized_projection_estimation", "mixed_output_unit_loss_aggregation": False,
        "A_columns": A_COLUMNS, "Z_columns": Z_COLUMNS, "physical_request_channel_count": 2,
        "subgroup_refits": 0, "scientific_pass_threshold": None,
        "scientific_adoption": False, "C4_passed": False, "C5_passed": False,
        "limitations": ["Training-data geometry does not establish generalization or causal action sufficiency.",
            "Rank<4 can reflect dependence of four basis columns for two physical request channels.",
            "Mixed-unit full-design singular values describe only the frozen numerical units.",
            "C/G subgroup cross terms need not vanish; no subgroup refit or causal attribution.",
            "K/L/D old failed gates remain failed; no controller or candidate is selected."],
        "datasets": results}
    run = {"schema_version": 1, "status": status, "requested_source_commit": args.source_commit,
        "source": source if source is not None else {"status": "unknown", "reason": "source verifier did not return"},
        "original_source_commits": COMMITS, "expected_input_pins": {name: {"bytes": size, "sha256": sha}
            for name, (size, sha) in PINS.items()}, "inputs": inputs,
        "input_qualification": input_qualification,
        "inputs_without_returned_read_record": {name: "unknown_before_read_record_returned" for name in PINS if name not in inputs},
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()},
        "cost": dict(cost), "operations": operations, "failure": failure,
        "expected_successful_cost": {"SVD_calls": 18, "matmul_calls": 36,
            "native_projection_label_scalars": 66000, "already_used_unique_native_label_scalars": 39600,
            "command_projection_response_scalars": 12000, "archived_ridge_forward_output_scalars": 66000,
            "native_projection_estimations": 6, "command_projection_estimations": 6,
            "archived_weights_validated_scalars": 3828},
        "cost_interpretation": "Projection is new offline estimation. Logical operation requests are algebraic counts, not measured hardware FLOPs. All earlier costs remain cumulative.",
        "wall_seconds_before_serialization": wall_seconds, "cpu_process_seconds_before_serialization": cpu_seconds}
    files = {}
    for name, value in (("diagnostics.json", diagnostics), ("run.json", run)):
        data = json_bytes(value)
        (output/name).write_bytes(data)
        files[name] = identity(data)
    (output/"manifest.json").write_bytes(json_bytes({"schema_version": 1, "status": status, "files": files}))
    print(json.dumps({"status": status, "output": str(output), "cost": dict(cost), "failure": failure}, ensure_ascii=False))
    return 0 if status == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True)
    return main_run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
