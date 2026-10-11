"""Derive only standard-library Z gate/entry source; no production imports."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
repo = root.parent.parent
path = repo/"external/y_learning_candidate/scripts/develop_damped_suspended_pair.py"
data = path.read_bytes()
source = data.decode("utf-8")
replacements = (
    ("damped_suspended_pair_development", "fast_feedback_pair_development"),
    ("develop_damped_suspended_pair.py", "develop_fast_feedback_pair.py"),
    ("validate_damped_suspended_pair_engineering.py", "validate_fast_feedback_engineering.py"),
    ("damped_residual_pd_pair_mpc", "fast_feedback_pair_mpc"),
    ("DAMPED_SUSPENDED_PAIR_PROTOCOL.md", "FAST_FEEDBACK_LEARNING_PROTOCOL.md"),
    ("2026-10-12_damped_suspended_pair_engineering", "2026-10-12_fast_feedback_engineering"),
    ("2026-10-12_damped_suspended_pair_prediction", "2026-10-12_fast_feedback_pair_prediction"),
    ("7500", "7600"), ("7501", "7701"), ("7502", "7702"), ("7503", "7703"),
    ("Y0", "Z0"), ("Y1", "Z1"), ("Y2", "Z2"), ("y1", "z1"), ("y2", "z2"),
    ("canonical_frozen_Y_learning_runner_required", "canonical_frozen_Z_learning_runner_required"),
    ("clean_exact_Y_learning_HEAD_required", "clean_exact_Z_learning_HEAD_required"),
    ("full_100_prefix_200_active", "full_1000_prefix_2000_active"),
    ('"control_call_returns") != 300', '"control_call_returns") != 3000'),
    ('"RLS_vector_update_commits") != 1200', '"RLS_vector_update_commits") != 12000'),
    ('"RLS_scalar_update_commits") != 2400', '"RLS_scalar_update_commits") != 24000'),
    ('"vector_update_count") != 400', '"vector_update_count") != 4000'),
    ("zero_and_400_atomic", "zero_and_4000_atomic"),
    ('"control_calls": 2100, "physics_substeps": 21000, "RLS_vector_commits": 1200,', '"control_calls": 21000, "physics_substeps": 21000, "RLS_vector_commits": 12000,'),
    ('"RLS_scalar_commits": 2400, "independent_prediction_pairs": 12408', '"RLS_scalar_commits": 24000, "independent_prediction_pairs": 124680'),
    ('"control_calls": 3600, "physics_substeps": 36000', '"control_calls": 36000, "physics_substeps": 36000'),
    ('"planning_prediction_pairs": 1458000, "conditional_prediction_pairs": 52416', '"planning_prediction_pairs": 14580000, "conditional_prediction_pairs": 526560'),
    ("from developmental_physics.suspended_environment import SuspendedGroundBodyEnv", "from developmental_physics.fast_feedback_environment import FastFeedbackGroundBodyEnv"),
    ("run_prediction(result, SuspendedGroundBodyEnv)", "run_prediction(result, FastFeedbackGroundBodyEnv)"),
    ("run_control(result, SuspendedGroundBodyEnv,", "run_control(result, FastFeedbackGroundBodyEnv,"),
)
changes = []
for before, after in replacements:
    count = source.count(before)
    if count:
        source = source.replace(before, after)
        changes.append({"before": before, "after": after, "count": count})
source = source.replace('PROTOCOL_PATH = "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md"',
    'PROTOCOL_PATH = "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md"\nENGINEERING_PROTOCOL_PATH = "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md"')
source = source.replace('SOURCE_PATH, MODULE_PATH, PROTOCOL_PATH,',
    'SOURCE_PATH, MODULE_PATH, PROTOCOL_PATH, ENGINEERING_PROTOCOL_PATH,\n    "src/developmental_physics/fast_feedback_pair_model.py",\n    "src/developmental_physics/fast_feedback_environment.py",')
source = source.replace('required = {"scripts/validate_fast_feedback_engineering.py", PROTOCOL_PATH,',
    'required = {"scripts/validate_fast_feedback_engineering.py", ENGINEERING_PROTOCOL_PATH,\n                    "src/developmental_physics/fast_feedback_environment.py",')
target = root/"scripts/develop_fast_feedback_pair.py"
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists():
    raise ValueError("fresh_Z_entry_required")
target.write_text(source, encoding="utf-8")
(root/"runner_derivation.json").write_text(json.dumps({
    "source": {"path": str(path.relative_to(repo)), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
    "transformations": changes, "source_file_reads": 1, "source_read_and_hash_bytes": len(data),
    "production_imports": 0, "fixture_executions": 0, "model_calls": 0, "fit_calls": 0,
    "physical_calls": 0, "raw_reads": 0, "production_publication": False}, indent=2)+"\n", encoding="utf-8")
print(json.dumps({"source_file_reads": 1, "source_read_and_hash_bytes": len(data), "output": str(target.relative_to(root))}))
