"""Derive an unexecuted free-root collector; retain exact unchanged math ASTs."""
import ast
import hashlib
import json
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source_path = repo / 'src/developmental_physics/fast_feedback_pair_development.py'
original = source_path.read_bytes()
assert len(original) == 45301
assert hashlib.sha256(original).hexdigest() == 'f29196f9a2e54743b6da29f3fe587871559065959a746d25fe8347dc8dcd96c7'
source = original.decode('utf-8')
tree = ast.parse(source)
nodes = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}

collector = '''def collect_trial(trial, trace, cost, *, seed, active_steps, kind,
                  expected_qref=None, expected_installation=None, after_prefix=None,
                  actor=None, after_transition=None, paid_writer=None):
    """Original supine free-root physics; save paid native before audit or learning."""
    trial.update(trial_id=f"FR_{seed}_{kind}", seed=seed, kind=kind, status="failed", complete=False,
                 planned_prefix=PREFIX, planned_active=active_steps, record_start=len(trace), stop=None,
                 failure=None, qref2=None, public_joint_ranges2=None, records=[])
    records, env, row, qref = trial["records"], None, None, None
    before_metadata = None
    def journal(entry_kind, item):
        if paid_writer is not None:
            paid_writer({"entry_kind": entry_kind, "record": item})
    try:
        cost["environment_constructor_attempts"] += 1
        env = FreeRootFastFeedbackGroundBodyEnv(audit_cost=cost)
        cost["environment_constructor_returns"] += 1
        cost["reset_attempts"] += 1
        observation = env.reset(seed=seed, pose="supine")
        cost["reset_returns"] += 1
        before_metadata = safe(env.frozen_metadata())
        trial["support"] = before_metadata["support"]
        asset = MODEL_PATH.read_bytes()
        cost["collector_asset_reads"] += 1
        cost["collector_asset_read_bytes"] += len(asset)
        trial["installed_xml_utf8"] = asset.decode("utf-8")
        trial["installed_xml_identity"] = identity(asset)
        trial["original_asset_unchanged_no_mount"] = True
        trial["physical_fingerprint_before"] = before_metadata["physical_fingerprint"]
        trial["execution_fingerprint_before"] = before_metadata["execution_fingerprint"]
        interface = dict(before_metadata["action_interface"])
        interface.update(actor_inputs=["current_native_qv2", "known_previous_request2", "current_target",
                                      "public_limits_and_initialized_or_learned_body_model"],
                         residual_decision_microsteps=MACRO_HOLD, predictive_horizon_microsteps=150,
                         pulse_schedule="declared_only_in_calibration_or_independent_prediction")
        trial["action_interface"] = interface
        trial["interface_fingerprint"] = hashlib.sha256(json.dumps(interface, sort_keys=True).encode()).hexdigest()
        if expected_installation is not None and any(trial[key] != expected_installation[key] for key in
                ("installed_xml_identity", "physical_fingerprint_before", "execution_fingerprint_before", "interface_fingerprint")):
            raise ValueError("same_seed_original_free_root_installation_differs_no_retry")
        ranges = np.asarray(env.model.jnt_range[env._joint_ids], dtype=float)[:2]
        if ranges.shape != (2, 2) or not np.isfinite(ranges).all():
            raise ValueError("finite_public_two_joint_ranges_required")
        trial["public_joint_ranges2"] = ranges.tolist()
        for index in range(PREFIX+active_steps):
            phase, phase_index = ("prefix", index) if index < PREFIX else ("active", index-PREFIX)
            if phase == "active" and qref is None:
                qref = native(observation)[0]
                trial["qref2"] = list(qref)
                if expected_qref is not None and any(abs(qref[i]-expected_qref[i]) > 1e-12 for i in range(2)):
                    trial["stop"] = {"primary_reason": "fresh_prefix_reference_mismatch_no_retry",
                                     "expected_qref2": expected_qref, "actual_qref2": qref}
                    break
                if after_prefix is not None and after_prefix(trial) is False:
                    trial["stop"] = {"primary_reason": "infeasible_fixed_target_no_clipping_or_direction_retry"}
                    break
            request = [0.]*8
            info = {"current_target_q2": None}
            if phase == "active":
                if actor is not None:
                    command, info = actor(observation, phase_index, trial)
                else:
                    q, v = native(observation)
                    pd = counted_pd(q, v, qref, cost, kind)
                    excitation = pulse(phase_index, kind)
                    command = tuple(float(np.clip(pd[i]+excitation[i], -.5, .5)) for i in range(2))
                    info = {"current_target_q2": qref, "public_pd_request2": pd, "pulse2": excitation}
                if len(command) != 2 or not np.isfinite(command).all() or any(abs(u) > .5 for u in command):
                    raise ValueError("finite_final_request_with_shared_permission_required")
                request[:2] = command
            row = {"seed": seed, "trial_id": trial["trial_id"], "transition_id": f"{trial['trial_id']}:{index}",
                   "control_index": index, "phase": phase, "phase_index": phase_index,
                   "observation_before": safe(observation), "requested_torque": list(request),
                   "returned": False, "study_abort": None, "diagnostics": None,
                   "contact_audit_complete": False, "complete_native_endpoint": False, **safe(info)}
            records.append(row)
            trace.append(row)
            before_steps = env.physics_steps
            cost["control_call_attempts"] += 1
            try:
                stepped = env.step(request)
                row["returned"] = True
                cost["control_call_returns"] += 1
            except BaseException as exc:
                cost["control_call_exceptions"] += 1
                row["collector_exception"] = failure(exc)
                raise
            finally:
                delta = env.physics_steps-before_steps
                if type(delta) is not int or delta < 0:
                    raise ValueError("invalid_substep_delta_unknown")
                row["confirmed_completed_substeps"] = delta
                cost["confirmed_physics_substeps"] += delta
            observation = stepped.observation
            row.update(observation_after=safe(observation), diagnostics=safe(stepped.diagnostics),
                       environment_terminated=bool(stepped.terminated), environment_reason=stepped.reason)
            journal("paid_native_endpoint", row)
            if delta not in (0, 1) or stepped.diagnostics.get("executed_substeps") != delta:
                raise ValueError("unexpected_paid_substep_count_preserved")
            complete = delta == 1
            if complete:
                # Preserve actual effort even if a subsequent contact query fails.
                sample = {"physics_step": env.physics_steps, "time": float(env.data.time),
                          "observation": safe(observation),
                          "actual_actuator_torque8": safe(observation["actuator_torque"]),
                          "applied_command8": safe(stepped.diagnostics["applied_torque"]),
                          "floor_contacts": [], "contact_audit_complete": False}
                row["diagnostics"]["substep_native_and_contact_records"] = [sample]
                native(observation)
                row["complete_native_endpoint"] = True
                cost["captured_native_endpoints"] += 1
                contacts = safe(env.audit_floor_pairs())
                if abs(contacts["time_s"]-(index+1)*.002) > 1e-9:
                    raise ValueError("fixed_endpoint_time_mismatch")
                row["audit_contacts"] = contacts
                sample["floor_contacts"] = [{"contact_class": pair["category"],
                    "left_arm": pair["category"] == "left_arm", "other_geom_name": pair["other_geom_name"],
                    "normal_force_n": pair["positive_normal_force_n"],
                    "signed_normal_force_n": pair["signed_normal_force_n"],
                    "distance_m": pair["distance_m"]} for pair in contacts["floor_pairs"]]
                sample["contact_audit_complete"] = row["contact_audit_complete"] = True
                row["study_abort"] = study_abort(observation, qref) if phase == "active" else None
                if row.get("current_target_q2") is not None:
                    q, _ = native(observation)
                    row["target_error_rad"] = [q[i]-row["current_target_q2"][i] for i in range(2)]
            journal("endpoint_audit_annotation", row)
            if stepped.terminated or not complete or row["study_abort"] is not None:
                trial["stop"] = {"transition_id": row["transition_id"], "environment_reason": stepped.reason,
                    "environment_terminated": bool(stepped.terminated), "study_abort": row["study_abort"],
                    "executed_substeps": delta,
                    "primary_reason": stepped.reason or ("partial_interval" if not complete else "StudyAbort")}
                break
            if not complete_telemetry(row):
                raise ValueError("complete_interval_native_effort_or_contact_telemetry_missing")
            if phase == "active" and after_transition is not None:
                after_transition(row)
            if phase == "active" and phase_index % 100 == 99:
                print(json.dumps(safe({"progress": "paid_active_block_complete", "seed": seed,
                    "phase": kind, "active_returns": phase_index+1,
                    "control_returns_total": cost["control_call_returns"],
                    "confirmed_substeps_total": cost["confirmed_physics_substeps"]}), allow_nan=False), flush=True)
        trial["status"] = "stopped" if trial["stop"] else "completed"
    except BaseException as exc:
        trial["failure"] = failure(exc)
        trial["status"] = "failed"
        if row is not None:
            try:
                journal("collector_failure_annotation", row)
            except BaseException as journal_exc:
                trial["failure"]["failure_annotation_write_failure"] = failure(journal_exc)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
    finally:
        if env is not None:
            try:
                after_metadata = safe(env.frozen_metadata())
                trial["physical_fingerprint_after"] = after_metadata["physical_fingerprint"]
                trial["execution_fingerprint_after"] = after_metadata["execution_fingerprint"]
                trial["metadata_stable"] = before_metadata is not None and before_metadata == after_metadata
                if not trial["metadata_stable"]:
                    raise ValueError("original_free_root_configuration_changed")
            except BaseException as exc:
                trial.setdefault("finalization_failures", []).append(failure(exc))
                trial["failure"] = trial["failure"] or failure(exc)
                trial["status"] = "failed"
        trial["record_end"] = len(trace)
        trial["returned_intervals"] = sum(item.get("returned") is True for item in records)
        trial["actual_effort"], trial["floor_contact_classes"] = effort(records)
        captured = sum(values["captured_substeps"] for values in trial["actual_effort"].values())
        cost["captured_substep_endpoint_forward_returns"] += captured
        trial["complete"] = bool(len(records) == PREFIX+active_steps and trial["failure"] is None
            and trial["stop"] is None and trial.get("metadata_stable") is True
            and all(complete_telemetry(item) for item in records))
        trial["actual_effort"]["active"]["complete"] &= trial["complete"]
        trial["constructor_model_builds_and_reset_forward_attempts"] = "unmeasured_unknown_not_zero"
        print(json.dumps(safe({"progress": "trial_finished", "seed": seed, "phase": kind,
            "status": trial["status"], "returned_intervals": trial["returned_intervals"],
            "control_attempts_total": cost["control_call_attempts"],
            "confirmed_substeps_total": cost["confirmed_physics_substeps"], "stop": trial["stop"]}),
            allow_nan=False), flush=True)
'''
lines = source.splitlines(keepends=True)
node = nodes['collect_trial']
lines[node.lineno-1:node.end_lineno] = [collector]
text = ''.join(lines)
text = text.replace('SEEDS = (7701, 7702, 7703)', 'SEEDS = (7901, 7902, 7903)')
text = text.replace('def run_prediction(result, env_factory):', 'def run_prediction(result):')
text = text.replace('def run_control(result, env_factory, saved_models, saved_seed_results):', 'def run_control(result, saved_models, saved_seed_results):')
text = text.replace('env_factory=env_factory, ', '')
assert 'env_factory' not in text
text = text.replace('z1_prediction_gate_passed', 'fr1_prediction_gate_passed')
text = text.replace('z2_model_contribution_gate_passed', 'fr2_model_contribution_gate_passed')
text = text.replace('z2_pd_reference_gate_passed', 'fr2_pd_reference_gate_passed')
text = text.replace('suspended_mechanism_validation', 'free_root_mechanism_validation')
text = text.replace('Z1', 'FR1').replace('Z2', 'FR2')
text = text.replace('New support-domain protocol only.', 'Original free-root supine domain; no suspended snapshots.')
text = text.replace('adds paid-interval capture, exact forward counters, and complete-population',
                    'adds paid-first native/audit capture, exact forward counters, and complete-population')
text = text.replace('from .local_pair_model import _parameter_state',
                    'from .local_pair_model import _parameter_state\nfrom .free_root_fast_feedback_environment import FreeRootFastFeedbackGroundBodyEnv\nfrom .environment import MODEL_PATH')
text = text.replace('def complete_telemetry(row):\n',
                    'def complete_telemetry(row):\n    if row.get("contact_audit_complete") is not True:\n        return False\n')
derived_tree = ast.parse(text)
derived_nodes = {node.name: node for node in derived_tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
preserved = ('safe', 'identity', 'failure', 'native', 'study_abort', 'direction_targets', 'pulse', 'counted_pd',
             'CountedGuardModel', 'restore_model', 'effort', 'score_population', 'tracking_score')
for name in preserved:
    assert ast.dump(nodes[name], include_attributes=False) == ast.dump(derived_nodes[name], include_attributes=False), name
out = repo / 'external/c4_free_learning_candidate'
out.mkdir(exist_ok=True)
data = text.replace('\r\n', '\n').encode('utf-8')
with (out / 'free_root_pair_development.py').open('xb') as stream:
    stream.write(data)
record = dict(source={'path': source_path.relative_to(repo).as_posix(), 'bytes': len(original), 'sha256': hashlib.sha256(original).hexdigest()},
              candidate={'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()},
              unchanged_math_ASTs=list(preserved), static_AST_parse_passed=True,
              tests_model_fit_or_physics_calls=0, public_seed_search='one 7901 synthetic control-count match; zero discovered seed uses; nonpublic use unknown',
              production_writes=0, automatic_retry=False)
with (out / 'collector_preparation.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps(record))
