"""Add pre-data contact eligibility and descriptive ranges, never execute science."""
import ast
import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
root = repo / 'external/c4_free_learning_candidate'
path = root / 'free_root_pair_development.py'
original = path.read_bytes()
assert len(original) == 47105 and hashlib.sha256(original).hexdigest() == '7460c628b008f1bf6ba02e23b805005fe457a36938e82afd83300361c53bfa6b'
archive = root / 'collector_revision_01'
archive.mkdir(exist_ok=False)
with (archive / 'before.py').open('xb') as stream:
    stream.write(original)
text = original.decode('utf-8')
helpers = '''def native_input_ranges(records):
    """Descriptive known input bounds; incomplete populations stay explicit."""
    bounds = {}
    for name in ("q2", "v2", "requested2", "public_guarded_applied2"):
        values = []
        for row in records:
            try:
                if name in ("q2", "v2"):
                    field = "joint_position" if name == "q2" else "joint_velocity"
                    value = np.asarray(row["observation_before"][field], dtype=float)[:2]
                elif name == "requested2":
                    value = np.asarray(row["requested_torque"], dtype=float)[:2]
                else:
                    value = np.asarray(row["diagnostics"]["applied_torque"], dtype=float)[:2]
                if value.shape == (2,) and np.isfinite(value).all():
                    values.append(value)
            except (KeyError, TypeError, ValueError):
                continue
        bounds[name] = {"planned_record_count": len(records), "known_record_count": len(values),
                        "missing_record_count": len(records)-len(values),
                        "minimum_axis": np.min(values, axis=0).tolist() if values else None,
                        "maximum_axis": np.max(values, axis=0).tolist() if values else None}
    return bounds


def free_root_contact_population(trial):
    """Count positive endpoints separately from pairs, retaining unknown samples."""
    records, active_steps = trial["records"], trial["planned_active"]
    control = trial["kind"].startswith("control_")
    spans = [("prefix", "prefix", 0, PREFIX)]
    spans += ([("target_A", "active", 0, 1000), ("target_B", "active", 1000, 2000)]
              if control else [("active", "active", 0, active_steps)])
    def summarize(name, phase, start, end, gate):
        selected = [row for row in records if row["phase"] == phase and start <= row["phase_index"] < end]
        observed = [row for row in selected if row.get("contact_audit_complete") is True]
        paid = sum(row.get("confirmed_completed_substeps", 0) for row in selected)
        result = {"name": name, "planned_count": end-start, "record_count": len(selected),
                  "confirmed_substeps": paid, "observed_contact_endpoints": len(observed),
                  "unknown_paid_contact_substeps": paid-len(observed), "classes": {},
                  "native_input_ranges": native_input_ranges(selected), "is_qualification_phase": gate}
        for category in ("left_arm", "feet", "other"):
            sums = [sum(pair["positive_normal_force_n"] for pair in row["audit_contacts"]["floor_pairs"]
                        if pair["category"] == category) for row in observed]
            positives = sum(value > 0 for value in sums)
            result["classes"][category] = {
                "positive_contact_endpoint_count": positives,
                "known_positive_fraction_of_paid_substeps": positives/paid if paid else None,
                "positive_count_unknown_if_missing": len(observed) != paid,
                "sampled_positive_duration_s": positives*.002,
                "endpoint_sample_normal_impulse_ns": sum(sums)*.002,
                "maximum_endpoint_normal_force_n": max(sums, default=0.)}
        result["qualification_passed"] = bool(gate and trial["complete"] and len(selected) == end-start
            and paid == len(observed) == end-start and result["classes"]["left_arm"]["positive_contact_endpoint_count"] >= 1)
        return result
    phases = {name: summarize(name, phase, start, end, True) for name, phase, start, end in spans}
    blocks = []
    for phase, count in (("prefix", PREFIX), ("active", active_steps)):
        for start in range(0, count, 200):
            blocks.append(summarize(f"{phase}_{start}_{min(start+200, count)-1}", phase,
                                    start, min(start+200, count), False))
    return {"phases": phases, "blocks_0_4s_report_only": blocks,
            "qualification_passed": all(row["qualification_passed"] for row in phases.values()),
            "contact_causality_or_continuous_support_demonstrated": False,
            "no_contact_based_training_selection": True}


def score_qualified_population(trial, models, predictions, cost, *, scope):
    view = dict(trial)
    view["complete"] = bool(trial["complete"] and trial.get("free_root_domain_qualification_passed"))
    start = len(predictions)
    result = score_population(view, models, predictions, cost, scope=scope)
    result.update(native_execution_complete=trial["complete"],
                  free_root_domain_qualification_passed=trial.get("free_root_domain_qualification_passed", False))
    if not trial.get("free_root_domain_qualification_passed"):
        result["unavailable_reason"] = "complete_free_root_contact_domain_required"
        for row in predictions[start:]:
            row["domain_qualification_unavailable"] = True
    return result


def tracking_score_qualified(trial, *, required):
    view = dict(trial)
    view["complete"] = bool(trial["complete"] and (not required or trial.get("free_root_domain_qualification_passed")))
    result = tracking_score(view)
    result.update(native_execution_complete=trial["complete"],
                  free_root_domain_qualification_required=required,
                  free_root_domain_qualification_passed=trial.get("free_root_domain_qualification_passed", False))
    return result


def control_origin_domain(trial, calibration):
    """All active origins compared to the calibration's input q/v bounds; no selection."""
    active = [row for row in trial["records"] if row["phase"] == "active"]
    reference = calibration["contact_population"]["phases"]["active"]["native_input_ranges"]
    output = {}
    for signal, field in (("q2", "joint_position"), ("v2", "joint_velocity")):
        bounds = reference[signal]
        known, outside = 0, [0, 0]
        for row in active:
            try:
                value = np.asarray(row["observation_before"][field], dtype=float)[:2]
                if value.shape != (2,) or not np.isfinite(value).all() or bounds["minimum_axis"] is None:
                    continue
                known += 1
                for axis in range(2):
                    outside[axis] += not (bounds["minimum_axis"][axis] <= value[axis] <= bounds["maximum_axis"][axis])
            except (KeyError, TypeError, ValueError):
                continue
        output[signal] = {"planned_origins": CONTROL, "paid_origin_records": len(active),
                          "known_origins": known, "unknown_or_unattempted_origins": CONTROL-known,
                          "outside_axis_counts": outside,
                          "outside_axis_fractions_of_full_population": [n/CONTROL for n in outside] if known == CONTROL else None,
                          "not_used_to_select_origins_or_train": True}
    return output


'''
text = text.replace('def run_prediction(result):', helpers+'def run_prediction(result):', 1)
old = '        trial["constructor_model_builds_and_reset_forward_attempts"] = "unmeasured_unknown_not_zero"'
new = '''        trial["contact_population"] = free_root_contact_population(trial)
        trial["free_root_domain_qualification_passed"] = trial["contact_population"]["qualification_passed"]
        trial["native_execution_complete"] = trial["complete"]
        for phase, values in trial["actual_effort"].items():
            paid = sum(item.get("confirmed_completed_substeps", 0) for item in records if item["phase"] == phase)
            values["confirmed_paid_substeps"] = paid
            values["unknown_actual_effort_substeps"] = paid-values["captured_substeps"]
            values["actual_effort_population_complete"] = paid == values["captured_substeps"] and not values.get("nonfinite_or_missing_effort", False)
        trial["constructor_model_builds_and_reset_forward_attempts"] = "unmeasured_unknown_not_zero"'''
assert text.count(old) == 1
text = text.replace(old, new)
old = 'if not seed_row["calibration"]["complete"] or models.get("learned") is None'
new = 'if not seed_row["calibration"]["complete"] or not seed_row["calibration"].get("free_root_domain_qualification_passed") or models.get("learned") is None'
assert text.count(old) == 1
text = text.replace(old, new)
text = text.replace('calibration_incomplete_or_not_4000_atomic_updates', 'calibration_incomplete_or_contact_domain_unqualified_or_not_4000_atomic_updates')
text = text.replace('seed_row["prediction_scores"] = score_population(', 'seed_row["prediction_scores"] = score_qualified_population(')
text = text.replace('any(not row.get("complete") for row in references.values())',
                    'any(not row.get("complete") or not row.get("free_root_domain_qualification_passed") for row in references.values())')
text = text.replace('seed_row["tracking_scores"][name] = tracking_score(trial)',
                    'trial["control_origin_domain"] = control_origin_domain(trial, references[seed])\n            seed_row["tracking_scores"][name] = tracking_score_qualified(trial, required=name != "zero")')
text = text.replace('seed_row["conditional_prediction_scores"][name] = score_population(',
                    'seed_row["conditional_prediction_scores"][name] = score_qualified_population(')
before, after = ast.parse(original), ast.parse(text)
before_nodes = {node.name: node for node in before.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
after_nodes = {node.name: node for node in after.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
preserved = json.loads((root / 'collector_preparation.json').read_bytes())['unchanged_math_ASTs']
preserved += ['prediction_gate', 'control_gate', 'new_result']
for name in preserved:
    assert ast.dump(before_nodes[name], include_attributes=False) == ast.dump(after_nodes[name], include_attributes=False), name
data = text.encode('utf-8')
path.write_bytes(data)
receipt = dict(candidate=dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()),
               previous_candidate=dict(bytes=len(original), sha256=hashlib.sha256(original).hexdigest()),
               unchanged_math_ASTs=preserved, added_before_any_FR1_data=True,
               numerical_metric_rules_unchanged=True, physical_completeness_not_falsified_for_domain_failure=True,
               formal_import_test_model_fit_physics_calls=0, automatic_retry=False)
with (root / 'contact_revision_preparation.json').open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, indent=2)
print(json.dumps(receipt))
