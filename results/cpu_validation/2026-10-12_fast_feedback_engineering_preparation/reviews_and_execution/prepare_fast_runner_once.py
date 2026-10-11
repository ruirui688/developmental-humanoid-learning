"""Derive first Z0 runner from frozen Y0; static transformations only."""
import ast
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
began = time.perf_counter()
original = (repo / "scripts/validate_damped_suspended_pair_engineering.py").read_bytes()
text = original.decode()
text = text.replace("Y0", "Z0").replace("Y_damped_suspended", "Z_fast_feedback_suspended")
text = text.replace("scripts/validate_damped_suspended_pair_engineering.py", "scripts/validate_fast_feedback_engineering.py")
text = text.replace('ENV_PATH = "src/developmental_physics/suspended_environment.py"', 'ENV_PATH = "src/developmental_physics/fast_feedback_environment.py"')
text = text.replace("docs/DAMPED_SUSPENDED_PAIR_PROTOCOL.md", "docs/FAST_FEEDBACK_ENGINEERING_PROTOCOL.md")
text = text.replace('DEPENDENCY_PINS = {', 'DEPENDENCY_PINS = {\n    "src/developmental_physics/suspended_environment.py": {"bytes": 7076, "sha256": "f5154b7e059ed9939ed130d9a5c9eda2af455b9f660a4e843c72b996a44d81f8"},')
text = text.replace('PROTOCOL_PIN = {"bytes": 14175, "sha256": "1df461102e3c93613b0dedddb202b1c6929ff38516459c3aecf5accb6d167d57"}', 'PROTOCOL_PIN = {"bytes": 0, "sha256": "pending_first_Z_protocol"}')
text = text.replace("SEED, PREFIX, ACTIVE = 7500, 100, 200", "SEED, PREFIX, ACTIVE = 7600, 1000, 2000")
text = text.replace("Z0_seed7500", "Z0_seed7600")
text = text.replace('"prefix_last20"', '"prefix_last200"').replace('80 <= row["phase_index"] < 100', '800 <= row["phase_index"] < 1000')
lower = text.index("def qualification(")
upper = text.index("def effort_summary(")
text = text[:lower] + '''def complete_fast_telemetry(row):
    samples = (row.get("diagnostics") or {}).get("substep_native_and_contact_records", [])
    if len(samples) != 1:
        return False
    sample = samples[0]
    step = row["control_index"] + 1
    if sample.get("physics_step") != step or not np.isfinite(sample.get("time", float("nan"))):
        return False
    if abs(sample["time"] - step * .002) > 1e-10:
        return False
    values = [(sample.get("applied_command8"), 8), (sample.get("actual_actuator_torque8"), 8)]
    observation = sample.get("observation", {})
    values.extend((observation.get(key), size) for key, size in (("joint_position", 8), ("joint_velocity", 8),
                  ("imu_gyro", 3), ("imu_acceleration", 3), ("actuator_torque", 8), ("previous_command", 8)))
    if any(np.asarray(value).shape != (size,) or not np.isfinite(np.asarray(value, dtype=float)).all()
           for value, size in values):
        return False
    for pair in sample.get("floor_contacts", []):
        if not np.isfinite(pair.get("normal_force_n", float("nan"))) or not np.isfinite(pair.get("distance_m", float("nan"))):
            return False
    return True


def qualification(records, support, helpers):
    """New one-substep population; old 20ms qualification is never called."""
    full = (len(records) == PREFIX+ACTIVE and all(
        row.get("control_index") == index and row.get("seed") == SEED
        and row.get("phase") == ("prefix" if index < PREFIX else "active")
        and row.get("phase_index") == (index if index < PREFIX else index-PREFIX)
        and row.get("returned") is True and (row.get("diagnostics") or {}).get("executed_substeps") == 1
        and row.get("environment_terminated") is False and row.get("study_abort") is None
        and complete_fast_telemetry(row) for index, row in enumerate(records)))
    mount = (support or {}).get("installation") or {}
    samples = [sample for row in records for sample in
               (row.get("diagnostics") or row.get("saved_partial") or {}).get("substep_native_and_contact_records", [])]
    fixed = bool(mount) and len(samples) == 3000 and all(
        sample["diagnostics"]["root_position"] == mount["fixed_torso_world_position"]
        and sample["diagnostics"]["root_quaternion"] == mount["fixed_torso_world_quaternion"]
        for sample in samples)
    windows = []
    for segment, lower, upper in ((0, 800, 1000), (1, 1800, 2000)):
        selected = [row for row in records if row.get("phase") == "active" and lower <= row["phase_index"] < upper]
        available = full and len(selected) == 200 and all(row.get("target_error_rad") is not None for row in selected)
        errors = np.asarray([row["target_error_rad"] for row in selected], dtype=float) if available else None
        if available and (errors.shape != (200, 2) or not np.isfinite(errors).all()):
            available = False
        mae = np.mean(np.abs(errors), axis=0).tolist() if available else None
        windows.append({"segment": segment, "active_indices": [lower, upper-1], "planned_count": 200,
                        "observed_count": len(selected), "duration_seconds": .4,
                        "full_trial_required": True, "available": available, "per_axis_mae_rad": mae,
                        "threshold_rad": .01, "passed": bool(available and all(value <= .01 for value in mae))})
    passed = full and fixed and all(window["passed"] for window in windows)
    return {"full_1000_prefix_2000_active": full, "complete_finite_substep_native_effort_required": True,
            "fixed_upright_mount_observed_all_3000_substeps": fixed, "last200_post_step_windows": windows,
            "contact_observations": contact_summary(records), "contact_required_for_pass": False,
            "engineering_qualification_passed": bool(passed), "partial_subset_gate": False,
            "meaning": "fast_feedback_suspended_noncontact_engineering_only", **FLAGS}


''' + text[upper:]
text = text.replace("from developmental_physics.suspended_environment import SuspendedGroundBodyEnv", "from developmental_physics.fast_feedback_environment import FastFeedbackSuspendedEnv")
text = text.replace("env = SuspendedGroundBodyEnv()", "env = FastFeedbackSuspendedEnv()")
branch_start = text.index("        if args.self_check:\n            cases.append(")
branch_end = text.index('        cost["parameter_fingerprint_attempts"] += 1', branch_start)
branch = text[branch_start:branch_end]
body = branch[branch.index("        else:\n")+len("        else:\n"):]
body = "\n".join(line[4:] if line.startswith("    ") else line for line in body.split("\n"))
text = text[:branch_start] + body + text[branch_end:]
text = text.replace('targets[0 if active < 100 else 1]', 'targets[0 if active < 1000 else 1]')
text = text.replace('result.diagnostics["executed_substeps"] == 10', 'result.diagnostics["executed_substeps"] == 1')
text = text.replace('"planned_calls": 300, "planned_substeps": 3000, "control_substeps": 10', '"planned_calls": 3000, "planned_substeps": 3000, "control_substeps": 1')
text = text.replace('"Z_shared_PD64_Kd4_4_reusing_existing_elbow_damping_no_scan"', '"Z_shared_Y_PD64_Kd4_4_no_gain_change_or_scan"')
text = text.replace('"Y_shared_PD64_Kd4_4_reusing_existing_elbow_damping_no_scan"', '"Z_shared_Y_PD64_Kd4_4_no_gain_change_or_scan"')
text = text.replace('"complete_prefix99_after_native_q_only"', '"complete_prefix999_after_native_q_only"')
text = text.replace('"physics_dt": .002,', '"physics_dt": .002, "control_dt": .002,\n           "prefix_duration_seconds": 2., "active_duration_seconds": 4.,\n           "research_stop_observation_cadence_seconds": .002,')
# Formal-only entry point: an assembly path would duplicate an already passed fixture.
text = text.replace("def sources(repo, commit, self_check, cost, files):", "def sources(repo, commit, cost, files):")
start = text.index("    if not self_check:\n")
end = text.index("    for name in", start)
text = text[:start] + "\n".join(line[4:] for line in text[start+len("    if not self_check:\n"):end].splitlines()) + "\n" + text[end:]
text = text.replace('if not self_check and git("show",', 'if git("show",')
text = text.replace("sources(repo, args.source_commit, args.self_check, cost, files)", "sources(repo, args.source_commit, cost, files)")
text = text.replace("verified = not args.self_check", "verified = True")
text = text.replace('"self_check_only": args.self_check, ', '')
text = text.replace('            if not args.self_check:\n                metrics = qualification(records, support, helpers)', '            metrics = qualification(records, support, helpers)')
text = text.replace('"status": status, "self_check": args.self_check,', '"status": status, "self_check": False,')
text = text.replace('    parser.add_argument("--self-check", action="store_true")\n', '')
text = text.replace("if not args.self_check and not args.source_commit:", "if not args.source_commit:")
text = text.replace('"Z0 native feedback: new shared shoulder damping, no feedforward model."', '"Z0 native feedback: unchanged Y gains, now every 2ms, no feedforward model."')
text = text.replace('"""Z0: one upright, suspended two-joint engineering trial; no body learning."""', '"""Z0: 2ms feedback, unchanged physical durations and gains; no body learning."""')
assert "args.self_check" not in text and "assembly_check" not in text and "helpers.qualification" not in text
ast.parse(text)
path = repo / "scripts/validate_fast_feedback_engineering.py"
with path.open("x", encoding="utf-8", newline="\n") as stream:
    stream.write(text)
data = text.encode()
record = {"source": {"bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()},
          "output": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
          "source_reads": 1, "read_bytes": len(original), "AST_parses": 1,
          "imports_physics_model_fit_RLS_tests": 0, "protocol_pin_final": False,
          "wall_seconds": time.perf_counter()-began}
with (repo / "external/c4_z_runner_derivation.json").open("x", encoding="utf-8") as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(record))
