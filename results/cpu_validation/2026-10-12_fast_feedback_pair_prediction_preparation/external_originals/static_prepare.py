"""First AST/compile-only Z candidate check; no implementation imports."""
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parent
wall, cpu = time.perf_counter(), time.process_time()
names = (
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/fast_feedback_pair_mpc.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
    "scripts/develop_fast_feedback_pair.py",
    "tests/test_fast_feedback_pair_model.py",
    "tests/test_fast_feedback_pair_mpc.py",
    "tests/test_fast_feedback_pair_development.py",
)
files, count = {}, 0
for name in names:
    data = (root/name).read_bytes()
    count += len(data)
    tree = ast.parse(data, filename=name)
    compile(tree, name, "exec")
    files[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "AST_and_compile_only": True,
        "API": [item.name for item in tree.body if isinstance(item, (ast.ClassDef, ast.FunctionDef))]}
    if name.endswith("development.py") and name.startswith("src/"):
        source = data.decode("utf-8")
        lines = source.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("def run_control"):
                print("\n".join(lines[index:]))
                break
    if name.startswith("scripts/"):
        print(data.decode("utf-8").split("def summary_only", 1)[0])
receipt = {
    "status": "external_Z1_Z2_candidate_static_ready_unexecuted_unpublished",
    "files": files,
    "first_static_preparation": {"source_file_reads": 7, "source_read_and_hash_bytes": count,
        "AST_attempts": 7, "AST_returns": 7, "compile_only_calls": 7,
        "wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu},
    "source_derivation": {"closed_Y_development_and_frozen_Y_controller_reads": 2,
        "closed_Y_development_and_frozen_Y_controller_bytes": 51066,
        "closed_Y_runner_reads": 1, "closed_Y_runner_bytes": 17840},
    "protocol_first_read": {"path": "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md", "bytes": 12655,
        "sha256": "2370f7b76f627936e18bd609d67f785e6a090bde3c7dea0097deda237b42305b"},
    "necessary_source_queries": ["MPCConfig section only: no gamma; local_model.py logical size 16564 bytes",
        "Z0 source path/dependencies/run schema excerpts only; OS/backend byte counts unknown"],
    "cached_source_reuse": "constructor, feature order, clone, atomic update, guard and decision API; no new old-source reads",
    "independent_review": {"agent": "/root/next_control_direction/y_static_contract_review",
        "source_file_reads": 4, "source_read_and_hash_bytes": 61890,
        "finding": "new model/controller/development time semantics and paid priority statically match; no executable issue",
        "tests_written": "two new fakepredictor timing/cost/fallback cases, unexecuted",
        "AST": 0, "production_imports": 0, "fixture_executions": 0, "model_calls": 0,
        "fit_calls": 0, "physical_calls": 0, "raw_reads": 0, "metrics_reads": 0,
        "MPC_test_initial_wrong_directory": "temporarily authored in production tests; immediately moved intact to external before import or execution",
        "MPC_test_content_changes_during_move": 0},
    "model_independent_review": {"receipt": "external/c4_z_pair_model_static_review.json",
        "scope": "bounded agent initial constructor/clone/time metadata only; loader restore boundary is separate static review"},
    "new_fixtures_prepared_not_run": {"model_adapter": 2, "micro_MPC": 2, "micro_development": 3},
    "later_static_changes_after_child_review": ["bind physical_configuration and execution/interface fingerprints separately",
        "H1/H10q availability reports cannot create extra scientific veto",
        "100-paid-active-step progress prints without new physical/model calls",
        "pin engineering plus learning protocols and independent Z0/Z1 artifact paths"],
    "planned_upper_bounds": {"Z1_calls_substeps": [21000, 21000], "online_vector_scalar_commits": [12000, 24000],
        "independent_pair_scalar_predictions": [124680, 249360], "RLS_preupdate_pair_scalar_separate": [12000, 24000],
        "Z2_calls_substeps": [36000, 36000], "MPC_decisions": 1200,
        "planning_pair_scalar_predictions": [14580000, 29160000],
        "conditional_pair_scalar_predictions": [526560, 1053120]},
    "production_imports": 0, "fixture_executions": 0, "body_model_constructors": 0, "model_calls": 0,
    "fit_calls": 0, "physical_calls": 0, "raw_reads": 0, "metrics_reads": 0,
    "production_publication": False, "old_X_Y_source_files_modified": False,
    "commit_push": 0, "unmeasured_source_edit_timing_and_backend_IO": "unknown_not_zero",
}
target = root/"implementation_status.json"
if target.exists():
    raise ValueError("first_Z_candidate_receipt_already_exists")
target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"files": files, "first_static_preparation": receipt["first_static_preparation"],
                  "production_imports": 0, "fixture_executions": 0, "model_calls": 0, "physical_calls": 0}))
