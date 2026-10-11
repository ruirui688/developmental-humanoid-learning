"""Independent standard-library audit of the fixed C4-A left-elbow PD grid.

No simulator, controller, NumPy or learning code is imported. Raw j1 records
are audited without observation reordering or historical source changes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GAINS = [(kp,kd) for kp in (4.,16.,64.) for kd in (0.,.2,1.)]
SEEDS = [0,1,2]
RESET_SEEDS = {0:3757552657,1:1641411168,2:2001025171}
JOINT = 1
JOINTS = ("left_shoulder","left_elbow","right_shoulder","right_elbow","left_hip","left_knee","right_hip","right_knee")
NATIVE = {"joint_position":8,"joint_velocity":8,"imu_gyro":3,"imu_acceleration":3,"actuator_torque":8,"previous_command":8}
ENVIRONMENT = {"physics_dt":.002,"control_substeps":10,"torque_limit":.5,"joint_speed_limit":20.,"joint_limit_margin":.08,"kinetic_energy_limit":50.,"reset_clearance":.005,"ground_contact_profile":"baseline"}
ASSET = "src/developmental_physics/assets/ground_body.xml"
PROTOCOL = "docs/ELBOW_PD_DEVELOPMENT_PROTOCOL.md"
REQUIRED_SOURCES = {ASSET,PROTOCOL,"pyproject.toml"} | {"src/developmental_physics/"+name for name in ("__init__.py","environment.py","collect.py","probes.py","feedback_validate.py","local_coverage_ablation.py","local_model.py","local_integration.py","exploration.py","elbow_feedback_validate.py")}
PHASES = ("prefix","control")
BUDGET_KEYS = ("control_calls_attempted","control_steps","physics_steps")
EFFORT_KEYS = ("requested_absolute_effort_nms","requested_squared_effort_nm2s","actual_absolute_effort_nms","actual_squared_effort_nm2s")

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

class Checks:
    def __init__(self):
        self.count = self.failed = 0
        self.maximum_difference = 0.
        self.violations = []

    def check(self, condition, label, location=None):
        self.count += 1
        if not condition:
            self.failed += 1
            if len(self.violations) < 200:
                self.violations.append({"check": label, "location": location})

    def near(self, actual, expected, label, location=None):
        valid = type(actual) in (int, float) and type(expected) in (int, float)
        valid = valid and math.isfinite(actual) and math.isfinite(expected)
        difference = abs(actual - expected) if valid else None
        if valid:
            self.maximum_difference = max(self.maximum_difference, difference)
        self.check(valid and difference <= 1e-10, label,
                   {"location": location, "actual": actual, "expected": expected,
                    "difference": difference})

def finite_tree(value):
    if isinstance(value, dict):
        if value.get("invalid_numeric_fields"):
            raise ValueError("archive contains invalid numeric markers")
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite numeric value")

def vector(value, width):
    if not isinstance(value, list) or len(value) != width or any(
        type(item) not in (int, float) or not math.isfinite(item) for item in value
    ):
        raise ValueError(f"expected {width} finite numeric measurements")
    return value

def count(value):
    if type(value) is not int or value < 0:
        raise ValueError("expected nonnegative integer count")
    return value

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def rmse(values):
    return math.sqrt(math.fsum(x*x for x in values) / len(values)) if values else None

def audit_sources(path, metadata, checks, git_root):
    manifest = load_json(path / "manifest.json")
    checks.check(set(manifest) == {p.name for p in path.iterdir()
                                   if p.is_file() and p.name != "manifest.json"},
                 "manifest_exact_file_coverage")
    checks.check({"metadata.json", "episodes.json", "trace.jsonl.gz", "source_snapshot.zip"}
                 .issubset(manifest), "manifest_core_files")
    for name, expected in manifest.items():
        local = Path(name).name == name and name not in (".", "..")
        checks.check(local, "manifest_local_filename", name)
        if local:
            checks.check((path/name).is_file() and file_hash(path/name) == expected,
                         "manifest_hash", name)
    hashes = metadata["source_sha256"]
    checks.check(REQUIRED_SOURCES.issubset(hashes), "required_source_files")
    protocol = metadata.get("protocol", {})
    checks.check(protocol.get("path") == PROTOCOL and
                 protocol.get("sha256") == hashes.get(PROTOCOL), "frozen_protocol_hash")
    commit = metadata.get("source_commit", "")
    valid_commit = isinstance(commit, str) and bool(re.fullmatch(r"[0-9a-f]{40}", commit))
    checks.check(valid_commit, "source_commit_format")
    checks.check(metadata.get("source_status") == "" and metadata.get("source_dirty") is False,
                 "clean_collection_source")
    with zipfile.ZipFile(path / "source_snapshot.zip") as archive:
        names = archive.namelist()
        checks.check(len(names) == len(set(names)) and set(names) == set(hashes),
                     "source_zip_exact_unique_coverage")
        for name, expected in hashes.items():
            blob = archive.read(name)
            checks.check(hashlib.sha256(blob).hexdigest() == expected, "source_zip_hash", name)
            if git_root is not None and valid_commit:
                result = subprocess.run(["git", "show", f"{commit}:{name}"], cwd=git_root,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                checks.check(result.returncode == 0 and result.stdout == blob,
                             "source_git_blob_bytes", name)
        xml = ET.fromstring(archive.read(ASSET))
    compiler = xml.find("compiler")
    factor = math.pi/180. if compiler is not None and compiler.get("angle", "degree") == "degree" else 1.
    ranges = {j.get("name"): [float(x)*factor for x in j.get("range").split()]
              for j in xml.findall(".//joint") if j.get("range")}
    return [vector(ranges[name], 2) for name in JOINTS]

def select_candidates(trials, seeds=SEEDS):
    """No truncation, per-seed gain changes, approximate ties, or actual-effort substitution."""
    candidates = []
    for i, (kp, kd) in enumerate(GAINS):
        rows = [trial for trial in trials if trial["candidate"] == i]
        eligible = len(rows) == len(seeds) and {r["seed"] for r in rows} == set(seeds)
        eligible = eligible and all(r["eligible"] for r in rows)
        mean = math.fsum(r["tracking_rmse_rad"] for r in rows)/len(rows) if eligible else None
        effort = math.fsum(r["requested_squared_effort_nm2s"] for r in rows)/len(rows) if eligible else None
        candidates.append({"candidate": i, "kp": kp, "kd": kd, "eligible": eligible,
                           "mean_tracking_rmse_rad": mean, "mean_requested_squared_effort_nm2s": effort,
                           "trial_ids": [r["trial_id"] for r in rows]})
    available = [c for c in candidates if c["eligible"]]
    selected = min(available, key=lambda c: (c["mean_tracking_rmse_rad"],
                    c["mean_requested_squared_effort_nm2s"], c["kp"], c["kd"], c["candidate"])) if available else None
    return {"rule": "complete three-seed mean raw RMSE, exact ties by mean requested squared effort, Kp, Kd, candidate",
            "candidates": candidates, "selected": selected, "selection_success": selected is not None}

def validate_output_path(output, inputs):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite an existing audit output.")
    if any(output.is_relative_to(Path(path).resolve()) for path in inputs if path is not None):
        raise ValueError("Audit output must be outside every input archive and reference.")
    return output

def study_abort(q, v, qref, stage="endpoint", index=None):
    displacement = q-qref
    triggers = []
    if abs(displacement) >= .12:
        triggers.append("absolute_q_minus_qref_rad")
    if abs(v) >= 1.:
        triggers.append("absolute_velocity_rad_s")
    verdict = None if not triggers else {
        "type":"StudyAbort","message":"predeclared native active envelope reached",
        "stage":stage,"triggers":triggers,"q_rad":q,"qref_rad":qref,
        "q_minus_qref_rad":displacement,"velocity_rad_s":v,
        "thresholds":{"absolute_q_minus_qref_rad":.12,"absolute_velocity_rad_s":1.},
        "feedback_action":None}
    if verdict is not None and index is not None:
        verdict.update(phase="control",step_index=index)
    return verdict


def new_risk():
    return {"native_endpoint_count":0,"joint_speed_peak_rad_s":[0.]*8,
            "joint_public_limit_violation_endpoints":[0]*8,
            "joint_public_limit_margin_endpoints":[0]*8,
            "joint_requested_but_shielded_substeps":[0]*8,
            "guarded_substeps":0,"outside_any_public_limit_endpoint_count":0,"ground_force_peak_n":0.,"ground_normal_impulse_ns":0.,
            "kinetic_energy_peak_j":0.,"minimum_contact_distance_m":0.,
            "penetration_peak_m":0.,"observed_diagnostic_substeps":0}


def new_state(ep):
    return {"episode":ep,"rows":0,"exception_rows":[],"invalid":False,
            "previous_after":None,"stopped":False,"study_abort":None,
            "environment_terminated":False,"environment_stop_reason":None,
            "prefix":hashlib.sha256(),"prefix_rows":0,"qref":None,"direction":None,
            "tracking":[],"partial_errors":[],"saturated":0,
            "phase_rows":{p:0 for p in PHASES},"phase_physics":{p:0 for p in PHASES},
            "phase_complete":{p:0 for p in PHASES},
            "phase_effort":{p:dict.fromkeys(EFFORT_KEYS,0.) for p in PHASES},
            "phase_actual_effort_substeps":{p:0 for p in PHASES},
            "risk":{p:new_risk() for p in PHASES}}


def _consume(state,row,checks,ranges):
    ep=state["episode"]
    where=ep["trial_id"]+"/"+str(state["rows"])
    before_failed=checks.failed
    if "collector_exception" in row:
        state["exception_rows"].append(row)
        checks.check(ep.get("status") == "exception","exception_outcome_matches_row",where)
        return
    index=state["rows"]
    state["rows"] += 1
    try:
        finite_tree(row)
        checks.check(not state["stopped"],"no_transition_after_study_or_environment_stop",where)
        checks.check(index < 300 and row["control_index"] == index,"fixed_control_index",where)
        phase="prefix" if index < 100 else "control"
        checks.check(row["phase"] == phase,"fixed_phase",where)
        for key in ("seed","candidate","kp","kd"):
            checks.check(row[key] == ep[key],"row_trial_identity",where+"/"+key)
        before,after=row["observation_before"],row["observation_after"]
        for key,width in NATIVE.items():
            vector(before[key],width); vector(after[key],width)
        vector(row["qpos"],15); vector(row["qvel"],14)
        checks.check(row["qpos"][7:] == after["joint_position"] and row["qvel"][6:] == after["joint_velocity"],"raw_state_native_encoder_consistency",where)
        checks.check(state["previous_after"] is None or before == state["previous_after"],"exact_native_chain",where)
        state["previous_after"]=after
        q,v=before["joint_position"][JOINT],before["joint_velocity"][JOINT]
        if index == 100:
            state["qref"]=q
            low,high=ranges[JOINT]
            state["direction"]=1 if high-q >= q-low else -1
            checks.near(ep["prefix_end_q_rad"],q,"paid_prefix_reference",where)
            expected={"joint_index":JOINT,"joint_position_rad":q,"lower_limit_rad":low,
                "upper_limit_rad":high,"positive_room_rad":high-q,"negative_room_rad":q-low,
                "direction":state["direction"],"rule":"larger distance to the public joint limit; ties choose positive"}
            checks.check(ep["selection_record"] == expected,"public_limit_direction",where)
            checks.check(all(low+.03 <= q+state["direction"]*offset <= high-.03 for offset in (.04,.08)),"both_targets_public_interior",where)
        request=vector(row["requested_torque"],8)
        target=None if phase == "prefix" else state["qref"]+state["direction"]*(.04 if index < 200 else .08)
        expected=[0.]*8
        if target is None:
            checks.check(row["raw_pd_torque_nm"] is None and row["target_q_rad"] is None,"prefix_has_no_control_target",where)
        else:
            raw=ep["kp"]*(target-q)-ep["kd"]*v
            checks.near(row["raw_pd_torque_nm"],raw,"independent_raw_pd",where)
            checks.near(row["target_q_rad"],target,"fixed_task_target",where)
            expected[JOINT]=max(-.5,min(.5,raw))
        checks.check(request == expected,"independent_requested_pd_vector",where)
        d=row["diagnostics"]
        checks.check(d["requested_torque"] == request and d["accepted_torque"] == request,"common_permission_and_logged_request",where)
        n=count(d["executed_substeps"])
        checks.check(n <= 10 and (n == 10 or d["terminated"]),"executed_substep_count",where)
        complete=n == 10
        checks.check(row["complete_transition"] is complete,"complete_transition_from_actual_substeps",where)
        state["phase_rows"][phase] += 1
        state["phase_physics"][phase] += n
        physics=sum(state["phase_physics"].values())
        for key,expected_counter in (("control_steps_before",index),("control_steps_after",index+1),
                ("physics_steps_before",physics-n),("physics_steps_after",physics)):
            checks.check(row[key] == expected_counter,"returned_step_paid_counter",where+"/"+key)
        checks.near(d["time"],physics*.002,"executed_physics_time",where)
        if "physics_steps" in d:
            checks.check(d["physics_steps"] == physics,"diagnostic_cumulative_physics_steps",where)
        if "step_id" in d:
            checks.check(d["step_id"] == index+1,"diagnostic_cumulative_control_steps",where)
        env_stop=d["terminated"]
        checks.check(type(env_stop) is bool,"environment_flag_boolean",where)
        env_reason=d.get("reason")
        checks.check(env_stop == (env_reason is not None),"environment_reason_matches_flag",where)
        checks.check(row["environment_terminated"] is env_stop and row["environment_stop_reason"] == env_reason,"independent_environment_stop_preserved",where)
        verdict=None if phase == "prefix" else study_abort(after["joint_position"][JOINT],after["joint_velocity"][JOINT],state["qref"],index=index)
        checks.check(row["study_abort"] == verdict,"independent_native_study_abort",where)
        checks.check(not (verdict or env_stop) or ep["status"] in ("terminated","exception"),"stopped_outcome_matches_row",where)
        if verdict is not None:
            state["study_abort"]=verdict
        if env_stop:
            state["environment_terminated"]=True
            state["environment_stop_reason"]=env_reason
        state["stopped"] = bool(verdict or env_stop)
        error=None if target is None else after["joint_position"][JOINT]-target
        partial_error=error if not complete else None
        checks.check(row["partial_interval_target_error_rad"] == partial_error,"partial_native_error_separate_from_primary_metric",where)
        if phase == "control" and not complete:
            state["partial_errors"].append(error)
        effort=state["phase_effort"][phase]
        effort[EFFORT_KEYS[0]] += math.fsum(abs(x) for x in request)*n*.002
        effort[EFFORT_KEYS[1]] += math.fsum(x*x for x in request)*n*.002
        history=d.get("applied_torque_history")
        valid_history=(isinstance(history,list) and len(history) == n
            and all(isinstance(values,list) and len(values) == 8 and all(type(x) in (int,float) and math.isfinite(x) for x in values) for values in history))
        if not valid_history and row.get("exception_recovery"):
            # A returned incomplete telemetry payload is retained as missing,
            # never as zero actual torque or a healthy primary transition.
            state["invalid"] |= checks.failed != before_failed
            return
        checks.check(valid_history,"actual_history_length",where)
        shield=[0]*8
        for values in history:
            vector(values,8)
            checks.check(all(x in (0.,request[j]) for j,x in enumerate(values)),"actual_requested_or_shielded",where)
            for j,x in enumerate(values):
                shield[j] += int(request[j] != 0 and x == 0)
            effort[EFFORT_KEYS[2]] += math.fsum(abs(x) for x in values)*.002
            effort[EFFORT_KEYS[3]] += math.fsum(x*x for x in values)*.002
        state["phase_actual_effort_substeps"][phase] += len(history)
        forces=vector(d["substep_ground_normal_forces"],n)
        energies=vector(d["substep_kinetic_energies"],n)
        distances=vector(d["substep_minimum_contact_distances"],n)
        checks.check(all(x >= 0 for x in forces+energies),"nonnegative_force_energy",where)
        checks.near(d["peak_substep_ground_normal_force"],max(forces,default=0.),"force_summary",where)
        checks.near(d["ground_normal_impulse_ns"],math.fsum(forces)*.002,"force_impulse_summary",where)
        checks.near(d["peak_substep_kinetic_energy"],max(energies,default=0.),"energy_summary",where)
        checks.near(d["minimum_substep_contact_distance"],min(distances,default=0.),"distance_summary",where)
        guarded=count(d["guarded_substeps"])
        expected_guarded=sum(any(request[j] != 0 and values[j] == 0 for j in range(8)) for values in history)
        checks.check(guarded == expected_guarded,"shielded_substep_count",where)
        state["phase_complete"][phase] += int(complete)
        if phase == "control" and complete:
            state["tracking"].append(error)
            state["saturated"] += int(abs(request[JOINT]) == .5)
        risk=state["risk"][phase]
        risk["native_endpoint_count"] += 1
        risk["observed_diagnostic_substeps"] += n
        risk["ground_force_peak_n"]=max(risk["ground_force_peak_n"],max(forces,default=0.))
        risk["ground_normal_impulse_ns"] += math.fsum(forces)*.002
        risk["kinetic_energy_peak_j"]=max(risk["kinetic_energy_peak_j"],max(energies,default=0.))
        risk["minimum_contact_distance_m"]=min(risk["minimum_contact_distance_m"],min(distances,default=0.))
        risk["penetration_peak_m"]=max(0.,-risk["minimum_contact_distance_m"])
        risk["guarded_substeps"] += guarded
        risk["outside_any_public_limit_endpoint_count"] += int(any(qj < low or qj > high for qj,(low,high) in zip(after["joint_position"],ranges)))
        for j,(low,high) in enumerate(ranges):
            qj=after["joint_position"][j]
            risk["joint_speed_peak_rad_s"][j]=max(risk["joint_speed_peak_rad_s"][j],abs(after["joint_velocity"][j]))
            risk["joint_public_limit_violation_endpoints"][j] += int(qj < low or qj > high)
            risk["joint_public_limit_margin_endpoints"][j] += int(qj <= low+.03 or qj >= high-.03)
            risk["joint_requested_but_shielded_substeps"][j] += shield[j]
        if phase == "prefix":
            state["prefix"].update(canonical({key:row[key] for key in ("observation_before","observation_after","diagnostics","qpos","qvel")}))
            state["prefix"].update(b"\n")
            state["prefix_rows"] += 1
    except (ValueError,TypeError,KeyError,IndexError,OverflowError) as error:
        checks.check(False,"row_schema_or_arithmetic",{"location":where,"error":str(error)})
    state["invalid"] |= checks.failed != before_failed


def combined_risk(risks):
    out=new_risk()
    maxima=("ground_force_peak_n","kinetic_energy_peak_j","penetration_peak_m")
    arrays=("joint_public_limit_violation_endpoints","joint_public_limit_margin_endpoints","joint_requested_but_shielded_substeps")
    for risk in risks:
        for key in ("native_endpoint_count","guarded_substeps","outside_any_public_limit_endpoint_count","ground_normal_impulse_ns","observed_diagnostic_substeps"):
            out[key] += risk[key]
        for key in maxima:
            out[key]=max(out[key],risk[key])
        out["minimum_contact_distance_m"]=min(out["minimum_contact_distance_m"],risk["minimum_contact_distance_m"])
        for j in range(8):
            out["joint_speed_peak_rad_s"][j]=max(out["joint_speed_peak_rad_s"][j],risk["joint_speed_peak_rad_s"][j])
            for key in arrays:
                out[key][j] += risk[key][j]
    return out


EFFORT_ARCHIVE_KEYS = dict(zip(EFFORT_KEYS,("requested_absolute_nm_s","requested_squared_nm2_s","actual_absolute_nm_s","actual_squared_nm2_s")))


def risk_summary(risk):
    return {"peak_ground_force_n":risk["ground_force_peak_n"],
            "ground_normal_impulse_ns":risk["ground_normal_impulse_ns"],
            "peak_kinetic_energy_j":risk["kinetic_energy_peak_j"],
            "minimum_contact_distance_m":risk["minimum_contact_distance_m"],
            "max_native_speed_rad_s":max(risk["joint_speed_peak_rad_s"]),
            "guarded_substeps":risk["guarded_substeps"],
            "outside_public_limit_endpoint_count":risk["outside_any_public_limit_endpoint_count"]}


def _recover_returned_exception(state,checks,ranges):
    for row in state["exception_rows"]:
        returned=row.get("returned_step_diagnostics")
        if returned is None:
            continue
        index=row.get("control_index")
        if index == state["rows"]-1:
            # A post-write failure retains the last return but is no new cost.
            checks.check(row.get("returned_control_steps") == state["rows"],"exception_duplicate_last_return_count",state["episode"]["trial_id"])
            continue
        checks.check(index == state["rows"],"exception_unstored_return_is_next_transition",state["episode"]["trial_id"])
        reconstructed={key:value for key,value in row.items() if key != "collector_exception"}
        reconstructed.update(diagnostics=returned,observation_after=row["returned_observation_after"],
            environment_terminated=returned["terminated"],environment_stop_reason=returned.get("reason"),
            complete_transition=returned["executed_substeps"] == 10,exception_recovery=True)
        _consume(state,reconstructed,checks,ranges)


def _trial(state,plan,checks,ranges):
    ep=state["episode"]
    where=plan["trial_id"]
    before_failed=checks.failed
    finite_tree(ep)
    checks.check(all(ep.get(k) == v for k,v in plan.items()),"episode_matches_plan",where)
    checks.check(ep.get("status") in ("completed","terminated","exception","blocked"),"recorded_outcome",where)
    budget=ep["phase_budgets"]
    for phase in PHASES:
        b=budget[phase]
        for key in BUDGET_KEYS:
            count(b[key])
        checks.check(b["control_calls_attempted"] >= b["control_steps"] >= state["phase_rows"][phase]
            and b["physics_steps"] >= state["phase_physics"][phase]
            and b["physics_steps"] <= 10*b["control_calls_attempted"]
            and b["control_calls_attempted"] <= (100 if phase == "prefix" else 200),"paid_phase_budget_including_unstored_fault_steps",where+"/"+phase)
    for key in BUDGET_KEYS:
        checks.check(ep[key] == sum(budget[p][key] for p in PHASES),"episode_budget_sum",where+"/"+key)
    if ep["status"] == "blocked":
        checks.check(ep.get("complete") is False and state["rows"] == 0 and not state["exception_rows"]
                     and all(ep[k] == 0 for k in BUDGET_KEYS),"blocked_has_no_unpaid_or_scored_work",where)
        return {**plan,"status":"blocked","eligible":False,"tracking_rmse_rad":None,
                "requested_squared_effort_nm2s":None,"paid_budget":{k:ep[k] for k in BUDGET_KEYS}}
    if ep.get("reset_seed") is not None:
        checks.check(ep["reset_seed"] == RESET_SEEDS[ep["seed"]],"fixed_development_seed_derivation",where)
    elif state["rows"]:
        checks.check(False,"fixed_development_seed_derivation",where)
    if ep.get("environment_fingerprint_before") is not None:
        fingerprint=ep["environment_fingerprint_before"]
        checks.check(isinstance(fingerprint,str) and re.fullmatch(r"[0-9a-f]{64}",fingerprint)
                     and ep.get("environment_fingerprint_after") == fingerprint,"unchanged_environment_parameters",where)
    if state["qref"] is None and ep.get("prefix_end_q_rad") is not None:
        checks.check(state["prefix_rows"] == 100 and state["previous_after"] is not None,"failed_action_reference_from_own_paid_prefix",where)
        if state["prefix_rows"] == 100 and state["previous_after"] is not None:
            q=state["previous_after"]["joint_position"][JOINT]
            low,high=ranges[JOINT]
            direction=1 if high-q >= q-low else -1
            state["qref"],state["direction"]=q,direction
            checks.near(ep["prefix_end_q_rad"],q,"failed_action_unclipped_paid_reference",where)
            expected={"joint_index":JOINT,"joint_position_rad":q,"lower_limit_rad":low,"upper_limit_rad":high,
                "positive_room_rad":high-q,"negative_room_rad":q-low,"direction":direction,
                "rule":"larger distance to the public joint limit; ties choose positive"}
            checks.check(ep.get("selection_record") == expected,"failed_action_public_limit_direction",where)
    checks.check("trace_write_failure" in ep and (ep["trace_write_failure"] is None or isinstance(ep["trace_write_failure"],dict)),"explicit_trace_write_failure_record",where)
    for row in state["exception_rows"]:
        if row.get("control_steps_before") is None or row.get("returned_step_diagnostics") is not None:
            continue
        index=count(row["control_index"])
        phase="prefix" if index < 100 else "control"
        checks.check(index == state["rows"] and row.get("phase") == phase,"unreturned_exception_current_index_phase",where)
        for key in ("seed","candidate","kp","kd"):
            checks.check(row.get(key) == ep[key],"exception_trial_identity",where+"/"+key)
        request=vector(row["requested_torque"],8)
        before=row["observation_before"]
        for key,width in NATIVE.items():
            vector(before[key],width)
        checks.check(state["previous_after"] is None or before == state["previous_after"],"unreturned_exception_exact_native_start",where)
        expected=[0.]*8
        if phase == "control":
            target=state["qref"]+state["direction"]*(.04 if index < 200 else .08)
            raw=ep["kp"]*(target-before["joint_position"][JOINT])-ep["kd"]*before["joint_velocity"][JOINT]
            checks.near(row.get("target_q_rad"),target,"unreturned_exception_fixed_current_target",where)
            checks.near(row.get("raw_pd_torque_nm"),raw,"unreturned_exception_independent_raw_pd",where)
            expected[JOINT]=max(-.5,min(.5,raw))
        else:
            checks.check(row.get("target_q_rad") is None and row.get("raw_pd_torque_nm") is None,"unreturned_prefix_no_target",where)
        checks.check(request == expected,"unreturned_exception_independent_requested_pd",where)
    recovered={p:0 for p in PHASES}
    missing={p:budget[p]["physics_steps"]-state["phase_physics"][p] for p in PHASES}
    for phase in PHASES:
        n=missing[phase]
        if n:
            candidates=[r for r in state["exception_rows"] if r.get("phase") == phase and r.get("returned_step_diagnostics") is None]
            valid=len(candidates) == 1 and n <= 10
            checks.check(valid,"unreturned_paid_effort_has_unique_known_command",where+"/"+phase)
            if valid:
                row=candidates[0]
                request=vector(row["requested_torque"],8)
                checks.check(abs(request[JOINT]) <= .5 and all(x == 0 for j,x in enumerate(request) if j != JOINT),"exception_command_common_permission",where)
                checks.check(row["physics_steps_after"]-row["physics_steps_before"] == n,"exception_paid_physics_delta",where)
                checks.check(row["control_steps_after"]-row["control_steps_before"] == budget[phase]["control_steps"]-state["phase_rows"][phase],"exception_paid_control_delta",where)
                state["phase_effort"][phase][EFFORT_KEYS[0]] += abs(request[JOINT])*n*.002
                state["phase_effort"][phase][EFFORT_KEYS[1]] += request[JOINT]**2*n*.002
                recovered[phase]=n
    returned=sum(state["phase_rows"].values())
    returned_physics=sum(state["phase_physics"].values())
    physics=sum(r["observed_diagnostic_substeps"] for r in state["risk"].values())
    written=returned-sum(r.get("returned_step_diagnostics") is not None and r.get("control_index") == state["rows"]-1 and r.get("trace_rows_written") == state["rows"]-1 for r in state["exception_rows"])
    checks.check(ep.get("returned_control_steps") == returned,"returned_control_count",where)
    checks.check(ep.get("trace_rows_written") == written,"stored_trace_count",where)
    checks.check(ep.get("returned_unstored_control_steps") == returned-written,"returned_unstored_count",where)
    checks.check(ep.get("unreturned_physics_steps") == sum(missing.values()),"unreturned_physics_exposure",where)
    checks.check(ep.get("phase_complete_transition_counts") == state["phase_complete"],"complete_transition_phase_counts",where)
    checks.check(ep.get("partial_interval_target_errors_rad") == state["partial_errors"]
                 and ep.get("partial_interval_target_error_count") == len(state["partial_errors"]),"partial_errors_retained_separately",where)
    tracking=rmse(state["tracking"])
    if tracking is None:
        checks.check(ep.get("tracking_rmse_rad") is None,"empty_tracking_metric",where)
    else:
        checks.near(ep.get("tracking_rmse_rad"),tracking,"independent_tracking_rmse",where)
    checks.check(ep.get("metric_control_step_count") == len(state["tracking"]),"primary_complete_transition_count",where)
    checks.check(ep.get("saturated_control_steps") == state["saturated"],"complete_control_saturation_count",where)
    actual_missing={p:budget[p]["physics_steps"]-state["phase_actual_effort_substeps"][p] for p in PHASES}
    for phase in PHASES:
        for key in EFFORT_KEYS:
            checks.near(ep["phase_effort"][phase][EFFORT_ARCHIVE_KEYS[key]],state["phase_effort"][phase][key],"independent_phase_effort",where+"/"+phase+"/"+key)
    checks.check(ep.get("phase_actual_effort_substeps") == state["phase_actual_effort_substeps"],"actual_effort_observed_substep_count",where)
    checks.check(ep.get("phase_actual_effort_missing_substeps") == actual_missing,"actual_effort_missing_not_zero_filled",where)
    checks.check(ep.get("phase_actual_effort_complete") == {p:actual_missing[p] == 0 for p in PHASES},"actual_phase_effort_scope",where)
    actual_complete=sum(actual_missing.values()) == 0
    checks.check(ep.get("actual_effort_complete") is actual_complete and ep.get("actual_effort_is_lower_bound") is (not actual_complete),"actual_full_effort_scope",where)
    requested=state["phase_effort"]["control"][EFFORT_KEYS[1]]
    checks.near(ep.get("requested_squared_effort_nm2s"),requested,"independent_control_requested_square",where)
    full=combined_risk(state["risk"].values())
    for phase,risk in {"full":full,**state["risk"]}.items():
        for key,value in risk_summary(risk).items():
            if type(value) is int:
                checks.check(ep["phase_risk"][phase][key] == value,"independent_phase_risk_count",where+"/"+phase+"/"+key)
            else:
                checks.near(ep["phase_risk"][phase][key],value,"independent_phase_risk",where+"/"+phase+"/"+key)
    checks.near(ep.get("peak_full_ground_force_n"),full["ground_force_peak_n"],"independent_full_force_peak",where)
    checks.near(ep.get("max_native_control_speed_rad_s"),max(state["risk"]["control"]["joint_speed_peak_rad_s"]),"independent_control_all_joint_speed",where)
    checks.check(ep.get("observed_diagnostic_substeps") == physics,"observed_risk_substeps",where)
    checks.check(ep.get("telemetry_complete_for_paid_substeps") is (physics == ep["physics_steps"]),"telemetry_paid_scope",where)
    checks.check(ep.get("risk_telemetry_complete") is (ep.get("collector_exception") is None and sum(missing.values()) == 0 and physics == ep["physics_steps"]),"risk_scope_has_failure_and_unknown_exposure",where)
    checks.check(ep.get("study_abort") == state["study_abort"],"episode_independent_study_abort",where)
    # Setup failure before reset may have unknown environment state; returned endpoints may not.
    checks.check(ep.get("environment_terminated") == state["environment_terminated"] or (not returned and ep.get("environment_terminated") is None),"episode_environment_stop_preserved",where)
    checks.check(ep.get("environment_stop_reason") == state["environment_stop_reason"],"episode_environment_reason_preserved",where)
    error=ep.get("collector_exception")
    reason=state["environment_stop_reason"] if state["environment_terminated"] else (state["study_abort"] if state["study_abort"] is not None else error)
    checks.check(ep.get("reason") == reason,"environment_then_study_then_exception_reason_precedence",where)
    checks.check(len(state["exception_rows"]) <= 1,"single_failure_no_rerun",where)
    if error is None:
        checks.check(not state["exception_rows"],"no_exception_row_without_failure",where)
    else:
        checks.check(ep["status"] == "exception","exception_status",where)
        if state["exception_rows"]:
            checks.check(state["exception_rows"][0]["collector_exception"] == error,"exception_record_identity",where)
    pd=count(ep["pd_action_calls"]); failed_pd=count(ep["failed_pd_attempts"])
    checks.check(pd >= state["phase_rows"]["control"] and pd <= 200 and failed_pd <= pd,"pd_action_attempts_paid_or_failed",where)
    checks.check(pd == budget["control"]["control_calls_attempted"]+failed_pd,"pd_calls_include_pre_step_failures",where)
    checks.check(type(ep["pd_action_seconds"]) in (int,float) and ep["pd_action_seconds"] >= 0,"pd_action_cpu_cost_available",where)
    complete=(error is None and ep["status"] == "completed" and not state["stopped"]
        and ep["reason"] is None and all(budget[p] == dict(zip(BUDGET_KEYS,(100 if p == "prefix" else 200,100 if p == "prefix" else 200,1000 if p == "prefix" else 2000))) for p in PHASES)
        and returned == written == 300 and physics == 3000 and state["phase_complete"] == {"prefix":100,"control":200}
        and len(state["tracking"]) == 200 and not state["exception_rows"])
    checks.check(ep.get("complete") is complete,"completion_excludes_last_step_stop_and_partial",where)
    checks.check(ep["status"] != "completed" or complete,"completed_outcome_has_complete_trace",where)
    eligible=complete and not state["invalid"] and checks.failed == before_failed
    full["paid_physics_steps"]=ep["physics_steps"]
    full["telemetry_is_lower_bound"]=physics < ep["physics_steps"]
    return {**plan,"status":ep["status"],"eligible":eligible,"tracking_rmse_rad":tracking,
        "requested_squared_effort_nm2s":requested,"phase_effort":state["phase_effort"],
        "requested_effort_recovered_unreturned_substeps":recovered,
        "actual_effort_complete":actual_complete,"actual_effort_is_lower_bound":not actual_complete,
        "phase_actual_effort_missing_substeps":actual_missing,"phase_risk":{"full":full,**state["risk"]},
        "study_abort":state["study_abort"],"environment_terminated":state["environment_terminated"],
        "environment_stop_reason":state["environment_stop_reason"],"partial_interval_target_errors_rad":state["partial_errors"],
        "complete_transition_counts":state["phase_complete"],"prefix_rows":state["prefix_rows"],
        "prefix_sha256":state["prefix"].hexdigest(),"trace_rows":written,"returned_control_steps":returned,
        "observed_physics_steps":physics,"paid_budget":{k:ep[k] for k in BUDGET_KEYS}}


def audit(archive, *, git_root=ROOT):
    wall_started,cpu_started=time.perf_counter(),time.process_time()
    path=Path(archive).resolve()
    checks=Checks()
    result={"path":str(path),"trials":[],"selection":{"selection_success":False,"selected":None}}
    try:
        meta=load_json(path/"metadata.json")
        # Even an unreadable manifest/trace must retain the paid cost claimed by
        # the collector, distinctly labelled rather than replaced with zeros.
        result["reported_budget"]={"origin":"metadata.json; not independently recomputed",
            **{key:meta.get(key) if type(meta.get(key)) is int and meta.get(key) >= 0 else None for key in BUDGET_KEYS}}
        result["budget"]={**result["reported_budget"],"recomputed_from_episode_ledgers":False}
        result["source_commit"]=meta.get("source_commit")
        result["source_sha256"]=meta.get("source_sha256")
        episodes=load_json(path/"episodes.json")
        finite_tree(meta)
        ranges=audit_sources(path,meta,checks,git_root)
        checks.check(meta.get("environment_config") == ENVIRONMENT,"frozen_environment")
        checks.check(meta.get("gains") == [list(g) for g in GAINS],"frozen_gain_grid_order")
        checks.check(meta.get("seeds") == SEEDS and meta.get("split") == "development","frozen_development_seeds")
        checks.check(meta.get("pose") == "supine" and meta.get("joint_index") == JOINT,"frozen_elbow_condition")
        checks.check(meta.get("prefix_steps") == 100 and meta.get("control_steps_per_trial") == 200
                     and meta.get("target_offsets_rad") == [.04,.08],"frozen_time_target_schedule")
        checks.check(meta.get("parameter_updates") == {"body_model":0,"policy":0,"gains":0}
                     and meta.get("model_updates") == 0 and meta.get("teacher_calls") == 0
                     and meta.get("external_demonstration_samples") == 0 and meta.get("gpu") is None,"no_learning_teacher_or_gpu")
        spec=meta.get("study_abort_spec",{})
        checks.check(spec.get("absolute_q_minus_qref_rad") == .12 and spec.get("absolute_velocity_rad_s") == 1.
                     and spec.get("comparison") == ">=","frozen_native_study_thresholds")
        planned=[{"trial_id":f"seed{s}_candidate{i}","seed":s,"candidate":i,"kp":kp,"kd":kd,"maximum_control_steps":300}
                 for s in SEEDS for i,(kp,kd) in enumerate(GAINS)]
        checks.check(meta.get("planned_episodes") == planned and meta.get("planned_episode_count") == len(planned)
                     and meta.get("maximum_control_steps") == 300*len(planned)
                     and meta.get("maximum_physics_steps") == 3000*len(planned),"complete_planned_grid")
        ids=[e["trial_id"] for e in episodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate episode IDs")
        checks.check(ids == [p["trial_id"] for p in planned],"all_planned_outcomes_in_order")
        states={e["trial_id"]:new_state(e) for e in episodes}
        order={p["trial_id"]:i for i,p in enumerate(planned)}
        last=-1
        with gzip.open(path/"trace.jsonl.gz","rt",encoding="utf-8") as stream:
            for line in stream:
                row=json.loads(line)
                tid=row.get("trial_id")
                checks.check(tid in states,"known_trace_trial_id",tid)
                if tid in states:
                    current=order[tid]
                    checks.check(current >= last,"fixed_trace_trial_order",tid)
                    last=current
                    _consume(states[tid],row,checks,ranges)
        for plan in planned:
            state=states.get(plan["trial_id"])
            if state is None:
                result["trials"].append({**plan,"status":"missing","eligible":False,"tracking_rmse_rad":None,"requested_squared_effort_nm2s":None})
                continue
            _recover_returned_exception(state,checks,ranges)
            result["trials"].append(_trial(state,plan,checks,ranges))
        for seed in SEEDS:
            trials=[t for t in result["trials"] if t["seed"] == seed and t.get("prefix_rows") == 100]
            same=len({t["prefix_sha256"] for t in trials}) <= 1
            checks.check(same,"exact_native_physical_prefix_across_candidates",seed)
            if not same:
                for trial in trials:
                    trial["eligible"]=False
        blocked=False
        fatal_index=None
        for i,ep in enumerate(episodes):
            error=ep.get("collector_exception") or {}
            fatal=error.get("type") in ("OSError","IOError","PermissionError","FileNotFoundError","KeyboardInterrupt","SystemExit") or ep.get("exception_trace_write_error") is not None or ep.get("trace_write_failure") is not None
            if fatal:
                fatal_index=i if fatal_index is None else fatal_index
            if ep["status"] == "blocked":
                blocked=True
                checks.check(meta.get("archive_status") in ("failed","interrupted") and meta.get("collector_exception") is not None,"blocked_only_after_fatal_archive",ep["trial_id"])
            else:
                checks.check(not blocked and (fatal_index is None or i == fatal_index),"no_more_trials_after_fatal_or_blocked",ep["trial_id"])
        if fatal_index is not None:
            checks.check(all(e["status"] == "blocked" for e in episodes[fatal_index+1:]),"fatal_blocks_every_remaining_planned_trial")
        for key in BUDGET_KEYS:
            checks.check(meta.get(key) == sum(ep[key] for ep in episodes),"metadata_budget_sum",key)
        for status in ("completed","terminated","exception","blocked"):
            checks.check(meta.get(status+"_trials") == sum(ep["status"] == status for ep in episodes),"metadata_outcome_count",status)
        checks.check(meta.get("all_trials_successful") == all(ep.get("complete") is True for ep in episodes),"metadata_success_summary")
        checks.check(meta.get("complete") is (meta.get("archive_status") == "complete"),"archive_completion_definition")
        checks.check(not meta.get("complete") or not blocked,"complete_archive_has_no_blocked_trials")
        result["selection"]=select_candidates(result["trials"],seeds=SEEDS)
        result["source_commit"]=meta.get("source_commit")
        result["source_sha256"]=meta.get("source_sha256")
        result["source_git_blob_verification_performed"]=git_root is not None
        result["budget"]={k:sum(ep[k] for ep in episodes) for k in BUDGET_KEYS}
        result["budget"]["recomputed_from_episode_ledgers"]=True
        result["budget"].update(simulated_seconds=meta["physics_steps"]*.002,planned_control_calls=300*len(planned),planned_physics_steps=3000*len(planned),model_updates=0,policy_updates=0,gain_updates=0)
        result["phase_budget"]={p:{k:sum(ep["phase_budgets"][p][k] for ep in episodes) for k in BUDGET_KEYS} for p in PHASES}
        result["input_hashes"]={name:file_hash(path/name) for name in ("manifest.json","metadata.json","episodes.json","trace.jsonl.gz","source_snapshot.zip")}
    except (OSError,ValueError,KeyError,IndexError,TypeError,AttributeError,OverflowError,zipfile.BadZipFile) as error:
        checks.check(False,"archive_schema_or_read_error",{"type":type(error).__name__,"message":str(error)})
    result["selection"]["validated_selection"]=result["selection"]["selection_success"] and checks.failed == 0 and git_root is not None
    return {"schema_version":1,"created_at_utc":datetime.now(timezone.utc).isoformat(),
            "purpose":"Independent fixed C4-A left-elbow PD audit; no physical interactions or parameter updates",
            "audit_script_sha256":file_hash(Path(__file__)),"checks":checks.count,"failed":checks.failed,
            "maximum_recomputation_difference":checks.maximum_difference,"violations":checks.violations,
            "analysis_runtime":{"python":sys.version,"platform":platform.platform(),"third_party_dependencies":[],
                "wall_seconds":time.perf_counter()-wall_started,"cpu_seconds":time.process_time()-cpu_started,
                "timing_scope":"audit entry through report construction; excludes module imports and output writing"},
            "execution":{"physical_control_calls":0,"physics_substeps":0,"model_updates":0,"policy_updates":0,"gain_updates":0},
            "archive":result,"claim_boundary":"Offline classical development selection; no unseen method advantage, full-body skill or safety claim"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    try:
        output=validate_output_path(args.output,[args.archive])
    except ValueError as error:
        parser.error(str(error))
    report=audit(args.archive)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8",newline="\n") as stream:
        json.dump(report,stream,indent=2,ensure_ascii=False,allow_nan=False)
        stream.write("\n")
    print(json.dumps({"checks":report["checks"],"failed":report["failed"],"selected":report["archive"]["selection"].get("selected"),"report":str(output)}))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
