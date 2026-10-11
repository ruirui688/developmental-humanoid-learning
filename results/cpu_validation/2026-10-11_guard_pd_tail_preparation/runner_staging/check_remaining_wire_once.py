"""One new G wire/flag/API check only; no imports of model or simulator code."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import time
import traceback

root = Path(__file__).resolve().parents[2]
base = root/"external/c4_pd_tail_control_runner_staging"
output = base/"engineering_02"
if output.exists():
    raise FileExistsError("one-attempt new-wire output must not exist")
output.mkdir()
paths = [base/"pd_tail_control_development.py", base/"guard_lag_control_development.original.py",
         root/"external/c4_pd_tail_mpc_staging/pd_tail_pair_mpc.py",
         root/"src/developmental_physics/guard_lag_pair_mpc.py",
         root/"src/developmental_physics/local_pair_model.py",
         base/"engineering_01/source_snapshot/external/c4_pd_tail_control_runner_staging/pd_tail_control_development.py"]
started_wall, started_cpu = time.perf_counter(), time.process_time()
record = {"scope": "explicit source reads and AST/disabled-flag call only; excludes interpreter/standard-library internal reads and final report write",
          "model_imports": 0, "model_constructions": 0, "model_predict_calls": 0,
          "model_updates": 0, "physical_queries": 0, "actual_E_C_D_F_reads": 0,
          "old_E_fixture_reexecutions": 0, "old_tail_math_reexecutions": 0, "git_calls": 0}
checks = {}
try:
    prior_blob = (base/"engineering_01/run.json").read_bytes()
    prior = json.loads(prior_blob)
    record["prior_checkpoint_read"] = {"opens": 1, "binary_bytes": len(prior_blob), "hash_operations": 1, "sha256": hashlib.sha256(prior_blob).hexdigest()}
    assert prior["passed"] == 18 and prior["failed"] == 1 and prior["harness_exception"]["type"] == "KeyError"
    blobs = [path.read_bytes() for path in paths]
    identities = [{"path": path.relative_to(root).as_posix(), "bytes": len(blob),
                   "sha256": hashlib.sha256(blob).hexdigest()} for path, blob in zip(paths, blobs)]
    record.update(source_records=identities, source_read_opens=6,
                  source_binary_bytes_read=sum(map(len, blobs)), source_hash_operations=6,
                  AST_parses=6)
    for path, blob in zip(paths, blobs):
        snapshot = output/"source_snapshot"/path.relative_to(root)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with snapshot.open("xb") as writer:
            writer.write(blob)
    trees = [ast.parse(blob) for blob in blobs]
    methods = [{node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
               for tree in trees]
    def assignments(tree):
        found = {}
        def bind(target, value):
            if isinstance(target, ast.Name):
                found[target.id] = value
            elif isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
                assert len(target.elts) == len(value.elts)
                for item, data in zip(target.elts, value.elts):
                    bind(item, data)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    bind(target, node.value)
        return found
    gconst, econst = assignments(trees[0]), assignments(trees[1])
    dump = lambda node: ast.dump(node, include_attributes=False)
    assert identities[5]["sha256"] == prior["source_records"][0]["sha256"]
    assert all(identities[i]["sha256"] == prior["source_records"][i]["sha256"] for i in range(1, 5))
    class StripAddedTailFeeMetadata(ast.NodeTransformer):
        def visit_Dict(self, node):
            node = self.generic_visit(node)
            if any(isinstance(key, ast.Constant) and key.value == "suite" for key in node.keys):
                for index in reversed(range(len(node.keys))):
                    if isinstance(node.keys[index], ast.Constant) and node.keys[index].value in ("maximum_tail_request_vector_evaluations", "maximum_first_request_candidate_evaluations", "tail_request_accounting"):
                        node.keys.pop(index);node.values.pop(index)
            return node
    checks["only_tail_fee_metadata_added_since_preserved_checkpoint"] = dump(StripAddedTailFeeMetadata().visit(copy.deepcopy(trees[0]))) == dump(trees[5])
    assert checks["only_tail_fee_metadata_added_since_preserved_checkpoint"]
    record["reused_checkpoint_checks"] = 18
    for name in ("_emit", "_failure", "target_pair", "restore_lag_snapshot", "load_d_models",
                 "episode_plan", "native_history", "bind_prefix", "run_trial"):
        key = "unchanged_E_core_"+name
        checks[key] = prior["checks"][key]
    for name in ("D_ROOT", "D_COMMIT", "C_COMMIT", "C_ENVIRONMENT_FINGERPRINT", "D_HASHES",
                 "SEEDS", "RESET_SEEDS", "KINDS", "MODEL_NAMES", "PREFIX_STEPS", "CONTROL_STEPS",
                 "JOINT_INDICES", "PHASES", "EFFORT_KEYS", "PLANNING_KEYS"):
        key = "unchanged_E_constant_"+name
        checks[key] = prior["checks"][key] if key in prior["checks"] else dump(gconst[name]) == dump(econst[name])
    expected = {"SOURCE_PATH": "src/developmental_physics/pd_tail_control_development.py",
                "MPC_SOURCE_PATH": "src/developmental_physics/pd_tail_pair_mpc.py",
                "MPC_BASE_SOURCE_PATH": "src/developmental_physics/guard_lag_pair_mpc.py",
                "PROTOCOL_PATH": "docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md",
                "AUDITOR_PATH": "scripts/audit_guard_pd_tail_control.py"}
    for name, value in expected.items():
        checks["new_binding_"+name] = ast.literal_eval(gconst[name]) == value
    checks["formal_false"] = ast.literal_eval(gconst["FORMAL_CONTROL_ENABLED"]) is False
    supports = ast.literal_eval(gconst["AUDITOR_SUPPORT_PATHS"])
    checks["E_auditor_and_all_prior_support_preserved"] = supports == (
        "scripts/audit_guard_lag_control.py", *ast.literal_eval(econst["AUDITOR_SUPPORT_PATHS"]))

    g_run = methods[0]["run_pd_tail_control_development"]
    metadata = next(node.value for node in ast.walk(g_run) if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "metadata" for target in node.targets))
    fields = {key.value: value for key, value in zip(metadata.keys, metadata.values) if isinstance(key, ast.Constant)}
    tail = ast.literal_eval(fields["tail_policy"])
    checks["new_suite_and_disclosed_tail_gains"] = (
        ast.literal_eval(fields["suite"]) == "pd_tail_control_development"
        and ast.literal_eval(fields["planner_variant"]) == "first_free_fixed_pd_tail"
        and tail["kp"] == [64., 64.] and tail["kd"] == [0., 4.]
        and tail["target_preview"] is False and tail["future_actual_state"] is False)
    checks["tail_execution_cost_and_selected_request_scope_disclosed"] = (
        tail["first_stage"] == "original candidate vector b"
        and tail["remaining_stages"] == "clip(Kp*(current target-predicted q)-Kd*predicted v, -.5, .5)"
        and tail["execution"] == "apply b only; observe and replan after the next 20 ms interval"
        and tail["cost"] == "original per-stage weights using each stage request; change cost only for first b against previous actual request"
        and tail["trajectory_request_scope"] == "selected feasible trajectory only; independent auditor rebuilds all candidate requests")

    fee_rules = ast.literal_eval(fields["tail_request_accounting"])
    checks["tail_request_caps_and_exception_nonzero_accounting_disclosed"] = (ast.literal_eval(fields["maximum_tail_request_vector_evaluations"]) == 1360800 and ast.literal_eval(fields["maximum_first_request_candidate_evaluations"]) == 97200 and "lower bound" in fee_rules["planner_exception"] and "include rejected prediction stages" in fee_rules["complete_decision"] and "nonzero" in fee_rules["historical_compute"])

    rename_strings = {
        "ignored staging G collector is not authorized for formal physical execution": "ignored staging E collector is not authorized for formal physical execution",
        "one-attempt G output must not exist; failures are never overwritten": "one-attempt E output must not exist; failures are never overwritten",
        "pd_tail_control_development": "guard_lag_control_development"}
    class NormalizeWire(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            node = self.generic_visit(node)
            if node.name == "run_pd_tail_control_development":
                node.name = "run_guard_lag_control_development"
            return node
        def visit_Name(self, node):
            if node.id == "FixedPDTailGuardLagPairMPC":
                node.id = "FixedGuardLagPairMPC"
            elif node.id == "run_pd_tail_control_development":
                node.id = "run_guard_lag_control_development"
            return node
        def visit_ImportFrom(self, node):
            if node.module == "developmental_physics.pd_tail_pair_mpc":
                node.module = "developmental_physics.guard_lag_pair_mpc"
                for alias in node.names:
                    if alias.name == "FixedPDTailGuardLagPairMPC":
                        alias.name = "FixedGuardLagPairMPC"
            return node
        def visit_Constant(self, node):
            if isinstance(node.value, str):
                node.value = rename_strings.get(node.value, node.value)
            return node
        def visit_JoinedStr(self, node):
            node = self.generic_visit(node)
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    value.value = value.value.replace("sealed D dependency differs from G HEAD", "sealed D dependency differs from E HEAD")
            return node
        def visit_Dict(self, node):
            node = self.generic_visit(node)
            if any(isinstance(key, ast.Constant) and key.value == "suite" for key in node.keys):
                for index in reversed(range(len(node.keys))):
                    if isinstance(node.keys[index], ast.Constant) and node.keys[index].value in ("planner_variant", "tail_policy", "maximum_tail_request_vector_evaluations", "maximum_first_request_candidate_evaluations", "tail_request_accounting"):
                        node.keys.pop(index);node.values.pop(index)
            return node
    checks["formal_entry_only_intended_wire_metadata_changes"] = (
        dump(NormalizeWire().visit(copy.deepcopy(g_run))) == dump(methods[1]["run_guard_lag_control_development"]))
    checks["main_only_new_entry_name"] = dump(NormalizeWire().visit(copy.deepcopy(methods[0]["main"]))) == dump(methods[1]["main"])

    planner = methods[2]["FixedPDTailGuardLagPairMPC"]
    base_planner = methods[3]["FixedGuardLagPairMPC"]
    p_methods = {node.name: node for node in planner.body if isinstance(node, ast.FunctionDef)}
    b_methods = {node.name: node for node in base_planner.body if isinstance(node, ast.FunctionDef)}
    checks["planner_frozen_API_signature_and_inherited_constructor"] = (
        len(planner.bases) == 1 and isinstance(planner.bases[0], ast.Name)
        and planner.bases[0].id == "FixedGuardLagPairMPC" and "__init__" not in p_methods
        and dump(p_methods["select"].args) == dump(b_methods["select"].args))
    checks["planner_source_is_exact_selected_draft"] = identities[2]["sha256"] == "6d1af186eb02e033a31fcc294eedd38fa743a418a69d16744350fa02aec3beed"
    decision = methods[2]["PDTailMPCDecision"]
    pair_decision = methods[4]["PairMPCDecision"]
    dict_method = next(node for node in pair_decision.body if isinstance(node, ast.FunctionDef) and node.name == "to_dict")
    checks["extended_decision_uses_inherited_dataclass_serialization"] = (
        any(isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            and node.target.id == "trajectory_requested_torque" for node in decision.body)
        and isinstance(decision.bases[0], ast.Name) and decision.bases[0].id == "PairMPCDecision"
        and any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "asdict" for node in ast.walk(dict_method)))
    root_call = next(node for node in ast.walk(g_run) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id == "run_trial")
    checks["formal_factory_is_PD_tail_with_original_default_config"] = (
        next(keyword.value.id for keyword in root_call.keywords if keyword.arg == "mpc_factory") == "FixedPDTailGuardLagPairMPC"
        and any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "mpc_factory"
                and len(node.args) == 2 and not node.keywords for node in ast.walk(methods[0]["run_trial"])))
    provenance = methods[0]["_formal_provenance"]
    gains_guard = next(node for node in provenance.body if isinstance(node, ast.If)
                       and "pd['kp']" in ast.unparse(node.test))
    checks["tail_and_PDselected_gains_bound_before_source_archive"] = (
        ast.unparse(gains_guard.test) == "tuple(pd['kp']) != (64.0, 64.0) or tuple(pd['kd']) != (0.0, 4.0)"
        and any(isinstance(node, ast.Raise) for node in gains_guard.body))
    first = g_run.body[0]
    checks["formal_guard_precedes_output_source_model_physics"] = isinstance(first, ast.If) and ast.unparse(first.test) == "not FORMAL_CONTROL_ENABLED"
    disabled_namespace = {"FORMAL_CONTROL_ENABLED": False}
    extracted = ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(g_run)], type_ignores=[]))
    exec(compile(extracted, "<G-disabled-entry-only>", "exec"), disabled_namespace)
    caught = None
    try:
        disabled_namespace["run_pd_tail_control_development"](object())
    except RuntimeError as exc:
        caught = str(exc)
    checks["disabled_entry_exits_without_Path_or_source_or_model_resolution"] = caught == "ignored staging G collector is not authorized for formal physical execution"
    record.update(disabled_entry_calls=1, disabled_entry_expected_exceptions=1,
                  checks=checks, passed=sum(checks.values()), failed=sum(not value for value in checks.values()))
except BaseException as exc:
    record.update(checks=checks, passed=sum(checks.values()), failed=1+sum(not value for value in checks.values()),
        harness_exception={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
finally:
    record.update(wall_seconds=time.perf_counter()-started_wall, cpu_seconds=time.process_time()-started_cpu)
    with (output/"run.json").open("x", encoding="utf-8", newline="\n") as writer:
        json.dump(record, writer, indent=2, allow_nan=False)
        writer.write("\n")
    print(json.dumps(record, indent=2, allow_nan=False))
raise SystemExit(int(record["failed"] != 0))
