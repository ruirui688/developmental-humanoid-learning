"""Derive first Z1/Z2 invocation/archive helpers; no learning invocation."""
import ast
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
external = repo / "external"
def save(name, text):
    ast.parse(text)
    with (external / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)

text = (external / "run_damped_suspended_once.py").read_text(encoding="utf-8")
text = text.replace('choices=("prediction", "control", "engineering")', 'choices=("prediction", "control")')
start = text.index('prefix = ')
end = text.index('sources = {}', start)
text = text[:start] + '''prefix = {"prediction": "c4_z1_prediction_01", "control": "c4_z2_control_01"}[args.stage]
output = repo / "external" / prefix
output.mkdir(exist_ok=False)
source_paths = [
    "src/developmental_physics/fast_feedback_environment.py",
    "src/developmental_physics/fast_feedback_pair_model.py",
    "src/developmental_physics/fast_feedback_pair_mpc.py",
    "src/developmental_physics/fast_feedback_pair_development.py",
    "scripts/develop_fast_feedback_pair.py",
    "docs/FAST_FEEDBACK_LEARNING_PROTOCOL.md",
    "scripts/validate_fast_feedback_engineering.py",
    "scripts/validate_supported_pair_engineering.py",
    "src/developmental_physics/suspended_environment.py",
    "src/developmental_physics/supported_environment.py",
    "src/developmental_physics/environment.py",
    "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/__init__.py",
    "src/developmental_physics/guard_coupled_pair_model.py",
    "src/developmental_physics/guard_pair_model.py",
    "src/developmental_physics/local_pair_model.py",
    "src/developmental_physics/local_model.py",
]
''' + text[end:]
start = text.index('if args.stage in ("assembly", "engineering"):', text.index('argv = '))
end = text.index('started, began', start)
text = text[:start] + '''argv += ["scripts/develop_fast_feedback_pair.py", "--repo", str(repo),
         "--output", str(output / "raw"), "--stage", args.stage]
commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
                        text=True, check=True).stdout.strip()
argv += ["--source-commit", commit]
''' + text[end:]
save("run_fast_pair_once.py", text)
text = (external / "archive_damped_suspended_stage_once.py").read_text(encoding="utf-8")
text = text.replace('choices=("engineering", "prediction", "control")', 'choices=("prediction", "control")')
text = text.replace('    "assembly": ("c4_y0_assembly_01", "damped_suspended_pair_engineering_preparation"),\n', '')
text = text.replace('    "engineering": ("c4_y0_engineering_01", "damped_suspended_pair_engineering"),\n', '')
text = text.replace("c4_y1_", "c4_z1_").replace("c4_y2_", "c4_z2_")
text = text.replace("damped_suspended_pair_prediction", "fast_feedback_pair_prediction").replace("damped_suspended_pair_control", "fast_feedback_pair_control")
text = text.replace("run_damped_suspended_once.py", "run_fast_pair_once.py").replace("archive_damped_suspended_stage_once.py", "archive_fast_pair_stage_once.py")
start = text.index('if args.stage == "assembly":')
end = text.index('record = ', start)
text = text[:start] + text[end:]
save("archive_fast_pair_stage_once.py", text)
print(json.dumps({"new_helpers": 2, "AST_parses": 2, "learning_physics_model_fit_calls": 0}))
