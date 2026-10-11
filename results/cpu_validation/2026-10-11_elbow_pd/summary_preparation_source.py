"""Small read-only C4-A summary: native j1 scores/costs and exact gain selection.

Called once by the provenance wrapper, only after the first audit is complete.
It imports neither simulator/controller nor the audit implementation.
"""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET
import zipfile

SEEDS = (0, 1, 2)
GAINS = tuple((kp, kd) for kp in (4., 16., 64.) for kd in (0., .2, 1.))
JOINTS = ("left_shoulder", "left_elbow", "right_shoulder", "right_elbow",
          "left_hip", "left_knee", "right_hip", "right_knee")
BUDGET = ("control_calls_attempted", "control_steps", "physics_steps")
EFFORT = ("requested_absolute_effort_nms", "requested_squared_effort_nm2s",
          "actual_absolute_effort_nms", "actual_squared_effort_nm2s")
PHASES = ("prefix", "control")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def risk_zero():
    return {"ground_force_peak_n": 0., "ground_normal_impulse_ns": 0.,
        "kinetic_energy_peak_j": 0., "minimum_contact_distance_m": 0.,
        "penetration_peak_m": 0., "joint_speed_peak_rad_s": [0.]*8,
        "joint_public_limit_violation_endpoints": [0]*8,
        "joint_public_limit_margin_endpoints": [0]*8,
        "joint_requested_but_shielded_substeps": [0]*8, "guarded_substeps": 0,
        "outside_any_public_limit_endpoint_count": 0,
        "native_endpoint_count": 0, "observed_diagnostic_substeps": 0}


def append_risk(risk, after, request, diagnostic, ranges):
    risk["ground_force_peak_n"] = max(risk["ground_force_peak_n"], *diagnostic["substep_ground_normal_forces"], 0.)
    risk["ground_normal_impulse_ns"] += math.fsum(diagnostic["substep_ground_normal_forces"])*.002
    risk["kinetic_energy_peak_j"] = max(risk["kinetic_energy_peak_j"], *diagnostic["substep_kinetic_energies"], 0.)
    risk["minimum_contact_distance_m"] = min(risk["minimum_contact_distance_m"], *diagnostic["substep_minimum_contact_distances"], 0.)
    risk["penetration_peak_m"] = -risk["minimum_contact_distance_m"]
    risk["guarded_substeps"] += diagnostic["guarded_substeps"]
    violations = []
    for j, (q, v, (low, high)) in enumerate(zip(after["joint_position"], after["joint_velocity"], ranges)):
        outside = q < low or q > high
        violations.append(outside)
        risk["joint_speed_peak_rad_s"][j] = max(risk["joint_speed_peak_rad_s"][j], abs(v))
        risk["joint_public_limit_violation_endpoints"][j] += outside
        risk["joint_public_limit_margin_endpoints"][j] += q <= low+.03 or q >= high-.03
        risk["joint_requested_but_shielded_substeps"][j] += sum(a[j] != request[j] for a in diagnostic["applied_torque_history"])
    risk["outside_any_public_limit_endpoint_count"] += any(violations)
    risk["native_endpoint_count"] += 1
    risk["observed_diagnostic_substeps"] += diagnostic["executed_substeps"]


def summarize(archive, audit_path):
    wall, cpu = time.perf_counter(), time.process_time()
    archive, audit_path = Path(archive), Path(audit_path)
    names = ("metadata.json", "episodes.json", "trace.jsonl.gz", "manifest.json", "source_snapshot.zip")
    inputs = {name: sha(archive/name) for name in names}
    inputs["first_audit_json"] = sha(audit_path)
    metadata, episodes, audit = read_json(archive/"metadata.json"), read_json(archive/"episodes.json"), read_json(audit_path)
    if audit["failed"] != 0 or audit["archive"].get("source_git_blob_verification_performed") is not True:
        raise ValueError("First independent audit must have zero failures and Git source verification.")
    if audit["archive"]["input_hashes"] != {name: inputs[name] for name in names}:
        raise ValueError("Archive inputs differ from the first audit.")
    if (metadata["source_dirty"] is not False or metadata["source_status"] != ""
        or metadata["source_commit"] != "91223b39c86fbeb09f7bc399229789b1e00ce181"
        or metadata["source_commit"] != audit["archive"]["source_commit"]
        or metadata["seeds"] != list(SEEDS) or metadata["gains"] != [list(g) for g in GAINS]
        or metadata["joint_index"] != 1 or metadata["split"] != "development"):
        raise ValueError("This summary accepts only the frozen clean C4-A j1 development collection.")
    with zipfile.ZipFile(archive/"source_snapshot.zip") as source:
        xml = ET.fromstring(source.read("src/developmental_physics/assets/ground_body.xml"))
    factor = math.pi/180. if xml.find("compiler").get("angle", "degree") == "degree" else 1.
    public = {j.get("name"): [float(x)*factor for x in j.get("range").split()]
              for j in xml.findall(".//joint") if j.get("range")}
    ranges = [public[name] for name in JOINTS]
    expected = [f"seed{s}_candidate{i}" for s in SEEDS for i in range(9)]
    if [e["trial_id"] for e in episodes] != expected:
        raise ValueError("All 27 planned outcomes must be retained in the fixed order.")
    grouped = {tid: [] for tid in expected}
    with gzip.open(archive/"trace.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            grouped[row["trial_id"]].append(row)
    audit_trials = {t["trial_id"]: t for t in audit["archive"]["trials"]}
    checks, violations = 0, []

    def check(condition, label, tid=None):
        nonlocal checks
        checks += 1
        if not condition:
            violations.append({"check": label, "trial_id": tid})

    def near(a, b, label, tid):
        check(a is None and b is None or type(a) in (int, float) and type(b) in (int, float)
              and math.isfinite(a) and math.isfinite(b) and abs(a-b) <= 1e-10, label, tid)

    trials = []
    for ep in episodes:
        tid, trial_start = ep["trial_id"], len(violations)
        rows = grouped[tid]
        exceptions = [r for r in rows if "collector_exception" in r]
        regular = [r for r in rows if "collector_exception" not in r]
        indexes = {r["control_index"] for r in regular}
        # An endpoint returned but not written as an ordinary row may still
        # be visible in the exception snapshot. Never count a duplicate twice.
        recovered = []
        for error in exceptions:
            i, d, after = error.get("control_index"), error.get("returned_step_diagnostics"), error.get("returned_observation_after")
            if i not in indexes and d is not None and after is not None:
                recovered.append({**error, "diagnostics": d, "observation_after": after})
                indexes.add(i)
        observed = sorted(regular+recovered, key=lambda r: r["control_index"])
        phase_steps, complete_steps = dict.fromkeys(PHASES, 0), dict.fromkeys(PHASES, 0)
        efforts = {p: dict.fromkeys(EFFORT, 0.) for p in PHASES}
        risks = {p: risk_zero() for p in ("full", *PHASES)}
        errors, partial, stops = [], [], []
        qref, direction, saturated, previous, prefix_bytes = None, None, 0, None, []
        for row in observed:
            i, before, after, d = row["control_index"], row["observation_before"], row["observation_after"], row["diagnostics"]
            phase, n, request = "prefix" if i < 100 else "control", d["executed_substeps"], row["requested_torque"]
            check(row["phase"] == phase and row["seed"] == ep["seed"] and row["candidate"] == ep["candidate"], "raw_identity", tid)
            check(previous is None or before == previous, "raw_native_chain", tid)
            previous = after
            check(len(request) == 8 and all(type(u) in (int, float) and math.isfinite(u) and abs(u) <= .5 for u in request)
                  and all(request[j] == 0. for j in range(8) if j != 1), "raw_permission_j1_only", tid)
            check(row["qpos"][7:] == after["joint_position"] and row["qvel"][6:] == after["joint_velocity"], "native_raw_mapping", tid)
            check(all(len(after[k]) == 8 and all(type(x) in (int, float) and math.isfinite(x) for x in after[k])
                      for k in ("joint_position", "joint_velocity")), "native_finite", tid)
            check(type(n) is int and 0 <= n <= 10 and (n == 10 or d["terminated"]), "physical_interval", tid)
            check(len(d["applied_torque_history"]) == n, "actual_history_count", tid)
            phase_steps[phase] += n
            complete_steps[phase] += n == 10
            u = request[1]
            efforts[phase][EFFORT[0]] += abs(u)*n*.002
            efforts[phase][EFFORT[1]] += u*u*n*.002
            actual = [a[1] for a in d["applied_torque_history"]]
            efforts[phase][EFFORT[2]] += math.fsum(abs(a) for a in actual)*.002
            efforts[phase][EFFORT[3]] += math.fsum(a*a for a in actual)*.002
            for scope in ("full", phase):
                append_risk(risks[scope], after, request, d, ranges)
            if phase == "prefix":
                check(request == [0.]*8 and row["target_q_rad"] is None, "zero_paid_prefix", tid)
                prefix_bytes.append(json.dumps({k: row[k] for k in ("observation_before", "observation_after", "diagnostics", "qpos", "qvel")}, sort_keys=True, separators=(",", ":")))
                if i == 99:
                    qref = after["joint_position"][1]
                    direction = 1 if ranges[1][1]-qref >= qref-ranges[1][0] else -1
                if d["terminated"]:
                    stops.append({"index": i, "study": False, "environment": True, "reason": d["reason"]})
                continue
            check(qref is not None, "paid_prefix_has_reference", tid)
            target = qref+direction*(.04 if i < 200 else .08)
            q, v = before["joint_position"][1], before["joint_velocity"][1]
            near(row["target_q_rad"], target, "current_native_target", tid)
            check(ranges[1][0]+.03 <= target <= ranges[1][1]-.03, "unclipped_public_target", tid)
            raw = ep["kp"]*(target-q)-ep["kd"]*v
            near(row["raw_pd_torque_nm"], raw, "native_pd_raw", tid)
            near(u, max(-.5, min(.5, raw)), "native_pd_request", tid)
            error = after["joint_position"][1]-target
            if n == 10:
                errors.append(error)
                saturated += abs(u) == .5
            else:
                partial.append(error)
            study = abs(after["joint_position"][1]-qref) >= .12 or abs(after["joint_velocity"][1]) >= 1.
            check(bool(row.get("study_abort")) == study, "native_study_stop", tid)
            if study or d["terminated"]:
                stops.append({"index": i, "study": study, "environment": bool(d["terminated"]), "reason": d["reason"]})
        missing = {p: ep["phase_budgets"][p]["physics_steps"]-phase_steps[p] for p in PHASES}
        requested_unknown = dict.fromkeys(PHASES, 0)
        for phase in PHASES:
            if missing[phase] > 0:
                commands = [r.get("requested_torque") for r in exceptions if r.get("phase") == phase]
                if len(commands) == 1 and isinstance(commands[0], list) and len(commands[0]) == 8:
                    u = commands[0][1]
                    efforts[phase][EFFORT[0]] += abs(u)*missing[phase]*.002
                    efforts[phase][EFFORT[1]] += u*u*missing[phase]*.002
                else:
                    requested_unknown[phase] = missing[phase]
        tracking = math.sqrt(math.fsum(e*e for e in errors)/len(errors)) if errors else None
        paid = {k: ep[k] for k in BUDGET}
        complete = (ep["status"] == "completed" and ep.get("collector_exception") is None and not exceptions
            and len(regular) == 300 and [r["control_index"] for r in regular] == list(range(300))
            and complete_steps == {"prefix": 100, "control": 200} and len(errors) == 200 and not stops
            and paid == {"control_calls_attempted": 300, "control_steps": 300, "physics_steps": 3000}
            and all(value == 0 for value in missing.values()))
        reference = audit_trials[tid]
        near(tracking, reference["tracking_rmse_rad"], "first_audit_tracking", tid)
        if complete:
            near(efforts["control"][EFFORT[1]], reference["requested_squared_effort_nm2s"], "first_audit_requested_square", tid)
        eligible = complete and len(violations) == trial_start
        check(eligible == reference["eligible"], "independent_candidate_trial_eligible", tid)
        trials.append({"trial_id": tid, "seed": ep["seed"], "candidate": ep["candidate"], "kp": ep["kp"], "kd": ep["kd"],
            "status": ep["status"], "eligible": eligible, "tracking_rmse_rad": tracking,
            "scored_complete_endpoints": len(errors), "planned_control_endpoints": 200,
            "missing_planned_control_endpoints": 200-len(errors), "qref_rad": qref, "direction": direction,
            "partial_interval_target_errors_rad": partial, "stops": stops, "saturated_control_steps": saturated,
            "paid_budget": paid, "phase_budget": ep["phase_budgets"], "phase_effort": efforts,
            "missing_actual_and_risk_substeps": missing, "unknown_requested_effort_substeps": requested_unknown,
            "actual_effort_and_risk_are_lower_bounds": any(missing.values()), "phase_risk": risks,
            "prefix_sha256": hashlib.sha256("\n".join(prefix_bytes).encode()).hexdigest(),
            "reason": ep.get("reason"), "collector_exception": ep.get("collector_exception"),
            "exception_trace_rows": exceptions, "collector_episode_record": ep})
    candidates = []
    for i, (kp, kd) in enumerate(GAINS):
        rows = [t for t in trials if t["candidate"] == i]
        eligible = len(rows) == 3 and {r["seed"] for r in rows} == set(SEEDS) and all(r["eligible"] for r in rows)
        candidates.append({"candidate": i, "kp": kp, "kd": kd, "eligible": eligible,
            "mean_tracking_rmse_rad": math.fsum(r["tracking_rmse_rad"] for r in rows)/3 if eligible else None,
            "mean_requested_squared_effort_nm2s": math.fsum(r["phase_effort"]["control"][EFFORT[1]] for r in rows)/3 if eligible else None,
            "trial_ids": [r["trial_id"] for r in rows], "per_seed_tracking_rmse_rad": [r["tracking_rmse_rad"] for r in rows]})
    eligible = [c for c in candidates if c["eligible"]]
    selected = min(eligible, key=lambda c: (c["mean_tracking_rmse_rad"], c["mean_requested_squared_effort_nm2s"], c["kp"], c["kd"], c["candidate"])) if eligible else None
    audited = audit["archive"]["selection"]["selected"]
    check((selected is None) == (audited is None), "first_audit_selection_presence")
    if selected is not None and audited is not None:
        check(all(selected[k] == audited[k] for k in ("candidate", "kp", "kd", "mean_tracking_rmse_rad", "mean_requested_squared_effort_nm2s", "trial_ids")), "exact_independent_selection_matches_first_audit")
    paid = {k: sum(e[k] for e in episodes) for k in BUDGET}
    phase_budget = {p: {k: sum(e["phase_budgets"][p][k] for e in episodes) for k in BUDGET} for p in PHASES}
    check(all(paid[k] == metadata[k] == audit["archive"]["budget"][k] for k in BUDGET), "all_paid_grid_costs")
    check(metadata["model_updates"] == 0 and metadata["parameter_updates"] == {"body_model": 0, "policy": 0, "gains": 0}, "zero_parameter_updates")
    check(all(sha(archive/name) == inputs[name] for name in names) and sha(audit_path) == inputs["first_audit_json"], "all_inputs_unchanged")
    return {"purpose": __doc__, "checks": checks, "failed": len(violations), "violations": violations,
        "input_hashes": inputs, "source_commit": metadata["source_commit"], "source_sha256": metadata["source_sha256"],
        "protocol": metadata["protocol"], "collection_runtime": {k: metadata.get(k) for k in ("wall_seconds", "cpu_seconds", "cpu_seconds_scope", "python_version", "dependencies", "mujoco_version", "gpu")},
        "budget": {**paid, "simulated_seconds": paid["physics_steps"]*.002, "planned_control_calls": 8100, "planned_physics_steps": 81000, "model_updates": 0, "gain_updates": 0, "policy_updates": 0},
        "phase_budget": phase_budget, "outcome_counts": dict(Counter(e["status"] for e in episodes)),
        "candidates": candidates, "selected": selected, "selection_success": selected is not None,
        "selection_rule": "Eligible three-seed raw RMSE mean, exact ties by requested squared effort mean, Kp, Kd, candidate; all 27 development trials are tuning cost.",
        "trials": trials, "first_audit": {"checks": audit["checks"], "failed": audit["failed"], "script_sha256": audit["audit_script_sha256"], "analysis_runtime": audit["analysis_runtime"]},
        "summary_runtime": {"wall_seconds": time.perf_counter()-wall, "cpu_seconds": time.process_time()-cpu, "physical_control_calls": 0, "model_parameter_updates": 0},
        "claim_boundary": "Local classical development selection only. No online body learning, unknown holdout advantage, safety or full-body skill claim."}
