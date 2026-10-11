"""Pure-stdlib source preflight: never import the evaluator or any model."""
import ast
import hashlib
import json
from pathlib import Path
import time


started_wall, started_cpu = time.perf_counter(), time.process_time()
folder = Path(__file__).resolve().parent
repo = folder.parents[1]
paths = [folder/"guard_lag_offline_development.py", folder/"test_guard_lag_offline_development.py",
         repo/"src/developmental_physics/guard_coupled_pair_model.py", repo/"src/developmental_physics/guard_lag_pair_model.py"]
source = {str(p.relative_to(repo)).replace("\\", "/"): p.read_bytes() for p in paths}
runner = ast.parse(source[str(paths[0].relative_to(repo)).replace("\\", "/")].decode("utf-8"))
tests = ast.parse(source[str(paths[1].relative_to(repo)).replace("\\", "/")].decode("utf-8"))
assignments = {n.targets[0].id: ast.literal_eval(n.value) for n in runner.body
               if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id in ("FORMAL_OFFLINE_ENABLED", "CANONICAL_RUNNER", "PREDICTORS", "HORIZONS", "COLLECTION_COMMIT", "SUMMARY_SHA", "AUDIT_SHA")}
functions = {n.name: n for n in runner.body if isinstance(n, ast.FunctionDef)}
entry = functions["run_single_lag_offline"]
binding_line = next(n.lineno for n in ast.walk(entry) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_binding")
helper_import_line = next(n.lineno for n in ast.walk(entry) if isinstance(n, ast.ImportFrom) and n.module == "developmental_physics.guard_lag_pair_model")
imports = [n.module for n in ast.walk(runner) if isinstance(n, ast.ImportFrom)]+[a.name for n in ast.walk(runner) if isinstance(n, ast.Import) for a in n.names]
checks = {
    "source_ast_parse_both": True,
    "staging_formal_entry_disabled": assignments["FORMAL_OFFLINE_ENABLED"] is False,
    "fixed_predictor_horizons_canonical": assignments["CANONICAL_RUNNER"] == "src/developmental_physics/guard_lag_offline_development.py"
        and assignments["PREDICTORS"] == ("nominal9", "sparse9", "continuation9", "lag_sparse11", "lag_continuation11") and assignments["HORIZONS"] == (1, 2, 5, 15),
    "all_source_input_binding_precedes_helper_import": binding_line < helper_import_line,
    "no_simulator_controller_or_git_import": not any(any(word in (name or "").lower() for word in ("mujoco", "isaac", "subprocess", "environment", "ppo", "torch")) for name in imports),
    "protected_models_byte_identity": hashlib.sha256(source[str(paths[2].relative_to(repo)).replace("\\", "/")]).hexdigest() == "7f234760e8f3d5b9cc799c871e84e7adfebecdf92e11f315735fad8b38ad78ed"
        and hashlib.sha256(source[str(paths[3].relative_to(repo)).replace("\\", "/")]).hexdigest() == "f3bcedf05b2c956357929e51dcab026ec13311428fa3c6c3383db114da3f7e57",
    "ordinary_fixture_declared_in_test_source": any(isinstance(n, ast.FunctionDef) and n.name == "fixture" for n in tests.body),
}
record = {"checks": checks, "passed": sum(checks.values()), "failed": sum(not x for x in checks.values()),
          "source_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in source.items()},
          "read_files": len(source), "read_bytes": sum(len(x) for x in source.values()), "ast_parse_calls": 2,
          "production_module_imports": 0, "real_C_reads": 0, "model_predictions": 0, "rls_updates": 0,
          "physics_calls": 0, "git_calls": 0, "wall_seconds": time.perf_counter()-started_wall,
          "cpu_seconds": time.process_time()-started_cpu, "timing_scope": "all source reads/AST/checks; excludes JSON write"}
output = folder/"preflight_ast_01.json"
if output.exists():
    raise FileExistsError("preflight result cannot be overwritten")
output.write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
print(json.dumps(record, indent=2))
raise SystemExit(0 if not record["failed"] else 1)
