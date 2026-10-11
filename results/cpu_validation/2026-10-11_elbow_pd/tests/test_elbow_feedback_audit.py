"""Pure synthetic C4-A archives; no simulator/controller import or physical work."""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest

ROOT=next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())
AUDIT_PATH=ROOT/"scripts/audit_elbow_feedback.py"
if not AUDIT_PATH.is_file():
    AUDIT_PATH=Path(__file__).with_name("audit_elbow_feedback.py")
SPEC=importlib.util.spec_from_file_location("c4a_independent_audit",AUDIT_PATH)
A=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)
ALL_GAINS=list(A.GAINS)
ALL_SEEDS=list(A.SEEDS)


def observation(command=0.,q=-.005,v=0.):
    pos=[0.]*8; pos[1]=q
    vel=[0.]*8; vel[1]=v
    torque=[0.,command]+[0.]*6
    return {"joint_position":pos,"joint_velocity":vel,"imu_gyro":[0.]*3,
            "imu_acceleration":[0.,0.,9.81],"actuator_torque":torque,"previous_command":torque}


def risk(steps):
    return {"peak_ground_force_n":1. if steps else 0.,"ground_normal_impulse_ns":steps*.02,
            "peak_kinetic_energy_j":.1 if steps else 0.,"minimum_contact_distance_m":-.001 if steps else 0.,
            "max_native_speed_rad_s":0.,"guarded_substeps":0,"outside_public_limit_endpoint_count":steps}


def grid():
    rows,episodes,planned=[],[],[]
    for seed in A.SEEDS:
        for i,(kp,kd) in enumerate(A.GAINS):
            plan={"trial_id":f"seed{seed}_candidate{i}","seed":seed,"candidate":i,"kp":kp,"kd":kd,"maximum_control_steps":300}
            planned.append(plan)
            before=observation()
            errors=[]; effort=0.; absolute=0.; saturated=0
            for index in range(300):
                phase="prefix" if index < 100 else "control"
                target=None if index < 100 else -.005+(.04 if index < 200 else .08)
                raw=None if target is None else kp*(target+.005)
                command=0. if raw is None else min(.5,raw)
                request=[0.,command]+[0.]*6
                after=observation(command)
                d={"requested_torque":request,"accepted_torque":request,"applied_torque_history":[request]*10,
                   "executed_substeps":10,"substep_ground_normal_forces":[1.]*10,
                   "substep_kinetic_energies":[.1]*10,"substep_minimum_contact_distances":[-.001]*10,
                   "peak_substep_ground_normal_force":1.,"ground_normal_impulse_ns":.02,
                   "peak_substep_kinetic_energy":.1,"minimum_substep_contact_distance":-.001,
                   "time":(index+1)*.02,"step_id":index+1,"physics_steps":(index+1)*10,
                   "guarded_substeps":0,"terminated":False,"reason":None}
                qpos=[0.]*15; qpos[8]=-.005
                rows.append({**{k:plan[k] for k in ("trial_id","seed","candidate","kp","kd")},
                   "control_index":index,"phase":phase,"control_steps_before":index,"control_steps_after":index+1,
                   "physics_steps_before":index*10,"physics_steps_after":(index+1)*10,
                   "requested_torque":request,"raw_pd_torque_nm":raw,"target_q_rad":target,
                   "study_abort":None,"environment_terminated":False,"environment_stop_reason":None,
                   "complete_transition":True,"partial_interval_target_error_rad":None,
                   "observation_before":before,"observation_after":after,"diagnostics":d,"qpos":qpos,"qvel":[0.]*14,"invalid_numeric_fields":[]})
                before=after
                if target is not None:
                    errors.append(-.005-target)
                    effort += command*command*.02
                    absolute += abs(command)*.02
                    saturated += int(command == .5)
            e0=dict(requested_absolute_nm_s=0.,requested_squared_nm2_s=0.,actual_absolute_nm_s=0.,actual_squared_nm2_s=0.)
            e1=dict(requested_absolute_nm_s=absolute,requested_squared_nm2_s=effort,actual_absolute_nm_s=absolute,actual_squared_nm2_s=effort)
            episodes.append({**plan,"status":"completed","reason":None,"collector_exception":None,"complete":True,
                "control_calls_attempted":300,"control_steps":300,"physics_steps":3000,
                "phase_budgets":{"prefix":dict(control_calls_attempted=100,control_steps=100,physics_steps=1000),"control":dict(control_calls_attempted=200,control_steps=200,physics_steps=2000)},
                "reset_seed":A.RESET_SEEDS[seed],"environment_fingerprint_before":"a"*64,"environment_fingerprint_after":"a"*64,
                "prefix_end_q_rad":-.005,"selection_record":{"joint_index":1,"joint_position_rad":-.005,
                    "lower_limit_rad":0.,"upper_limit_rad":2.,"positive_room_rad":2.005,"negative_room_rad":-.005,"direction":1,
                    "rule":"larger distance to the public joint limit; ties choose positive"},
                "tracking_rmse_rad":math.sqrt(math.fsum(x*x for x in errors)/200),"metric_control_step_count":200,
                "partial_interval_target_errors_rad":[],"partial_interval_target_error_count":0,
                "phase_complete_transition_counts":{"prefix":100,"control":200},
                "phase_effort":{"prefix":e0,"control":e1},"requested_squared_effort_nm2s":effort,
                "phase_actual_effort_substeps":{"prefix":1000,"control":2000},
                "phase_actual_effort_complete":{"prefix":True,"control":True},"phase_actual_effort_missing_substeps":{"prefix":0,"control":0},
                "actual_effort_complete":True,"actual_effort_is_lower_bound":False,
                "returned_control_steps":300,"trace_rows_written":300,"returned_unstored_control_steps":0,"unreturned_physics_steps":0,
                "saturated_control_steps":saturated,"phase_risk":{"full":risk(300),"prefix":risk(100),"control":risk(200)},
                "max_native_control_speed_rad_s":0.,"peak_full_ground_force_n":1.,"observed_diagnostic_substeps":3000,
                "telemetry_complete_for_paid_substeps":True,"risk_telemetry_complete":True,
                "pd_action_calls":200,"failed_pd_attempts":0,"pd_action_seconds":.001,
                "study_abort":None,"environment_terminated":False,"environment_stop_reason":None,"trace_write_failure":None})
    n=len(planned)
    meta={"environment_config":deepcopy(A.ENVIRONMENT),"gains":[list(g) for g in A.GAINS],"seeds":A.SEEDS,
        "split":"development","pose":"supine","joint_index":1,"prefix_steps":100,"control_steps_per_trial":200,"target_offsets_rad":[.04,.08],
        "parameter_updates":{"body_model":0,"policy":0,"gains":0},"model_updates":0,"teacher_calls":0,"external_demonstration_samples":0,"gpu":None,
        "study_abort_spec":{"absolute_q_minus_qref_rad":.12,"absolute_velocity_rad_s":1.,"comparison":">="},
        "planned_episodes":planned,"planned_episode_count":n,"maximum_control_steps":300*n,"maximum_physics_steps":3000*n,
        "source_status":"","source_dirty":False,"complete":True,"archive_status":"complete","all_trials_successful":True,
        "control_calls_attempted":300*n,"control_steps":300*n,"physics_steps":3000*n,
        "completed_trials":n,"terminated_trials":0,"exception_trials":0,"blocked_trials":0}
    return meta,episodes,rows


def rehash(path):
    (path/"manifest.json").write_text(json.dumps({p.name:A.file_hash(p) for p in path.iterdir() if p.name != "manifest.json"}),encoding="utf-8")


def write(path,records,sources):
    meta,episodes,rows=records
    path.mkdir()
    for name,data in (("metadata.json",meta),("episodes.json",episodes)):
        (path/name).write_text(json.dumps(data),encoding="utf-8")
    with gzip.open(path/"trace.jsonl.gz","wt",encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row)+"\n")
    with zipfile.ZipFile(path/"source_snapshot.zip","w") as source:
        for name,blob in sources.items():source.writestr(name,blob)
    rehash(path)


@pytest.fixture(scope="module")
def source_git(tmp_path_factory):
    root=tmp_path_factory.mktemp("elbow_git")
    xml='<mujoco><compiler angle="radian"/><worldbody><body>'+''.join(f'<joint name="{name}" range="{0 if i == 1 else -1} 2"/>' for i,name in enumerate(A.JOINTS))+'</body></worldbody></mujoco>'
    sources={name:xml.encode() if name == A.ASSET else b"Synthetic C4-A source\n" for name in A.REQUIRED_SOURCES}
    for name,blob in sources.items():
        path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(blob)
    for command in (["git","init"],["git","config","core.autocrlf","false"],["git","add","."],["git","-c","user.name=Synthetic Audit","-c","user.email=audit@example.invalid","commit","-m","Synthetic"]):
        subprocess.run(command,cwd=root,check=True,capture_output=True)
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    return sources,root,commit


@pytest.fixture
def recipe(monkeypatch,source_git):
    monkeypatch.setattr(A,"SEEDS",[0])
    monkeypatch.setattr(A,"GAINS",ALL_GAINS[:2])
    records=grid()
    sources,root,commit=source_git
    records[0].update(source_commit=commit,source_sha256={k:hashlib.sha256(v).hexdigest() for k,v in sources.items()},
        protocol={"path":A.PROTOCOL,"sha256":hashlib.sha256(sources[A.PROTOCOL]).hexdigest()})
    return records,sources,root


def report(tmp_path,recipe):
    records,sources,root=recipe
    folder=tmp_path/"archive"
    write(folder,records,sources)
    return A.audit(folder,git_root=root)


def test_complete_elbow_grid_native_negative_qref_and_all_risks(recipe,tmp_path):
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    assert out["archive"]["selection"]["validated_selection"]
    trial=out["archive"]["trials"][0]
    assert trial["eligible"] and trial["tracking_rmse_rad"] == pytest.approx(math.sqrt((.04**2+.08**2)/2))
    assert trial["phase_risk"]["full"]["joint_public_limit_violation_endpoints"][1] == 300
    assert trial["phase_risk"]["prefix"]["ground_normal_impulse_ns"] == pytest.approx(2.)
    assert trial["phase_risk"]["control"]["ground_normal_impulse_ns"] == pytest.approx(4.)
    assert out["analysis_runtime"]["third_party_dependencies"] == []


@pytest.mark.parametrize("mutation,label",[("joint","frozen_elbow_condition"),("target","fixed_task_target"),("command","independent_requested_pd_vector"),("stop","independent_native_study_abort"),("metric","independent_tracking_rmse"),("actual","independent_phase_effort"),("prefix","exact_native_physical_prefix_across_candidates"),("counter","returned_step_paid_counter"),("seed","fixed_development_seed_derivation"),("source","source_git_blob_bytes"),("manifest","manifest_hash"),("phase_risk","independent_phase_risk"),("complete","complete_transition_from_actual_substeps")])
def test_tamper_never_validates_selection(recipe,tmp_path,mutation,label):
    records,sources,root=recipe
    meta,eps,rows=records
    if mutation == "joint":meta["joint_index"]=0
    elif mutation == "target":rows[100]["target_q_rad"] = .04
    elif mutation == "command":rows[100]["requested_torque"]=[.1]+[0.]*7
    elif mutation == "stop":rows[100]["study_abort"]={"type":"StudyAbort"}
    elif mutation == "metric":eps[0]["tracking_rmse_rad"]=0.
    elif mutation == "actual":eps[0]["phase_effort"]["control"]["actual_squared_nm2_s"]=0.
    elif mutation == "prefix":rows[0]["qpos"][0]=.01
    elif mutation == "counter":rows[100]["physics_steps_before"]=0
    elif mutation == "seed":eps[0]["reset_seed"]=1
    elif mutation == "source":
        sources=deepcopy(sources); sources["pyproject.toml"] += b"tamper"
        meta["source_sha256"]["pyproject.toml"]=hashlib.sha256(sources["pyproject.toml"]).hexdigest()
    elif mutation == "phase_risk":eps[0]["phase_risk"]["prefix"]["peak_kinetic_energy_j"]=0.
    elif mutation == "complete":rows[100]["complete_transition"]=False
    folder=tmp_path/"archive"; write(folder,records,sources)
    if mutation == "manifest":(folder/"metadata.json").write_text(json.dumps(meta)+"\n",encoding="utf-8")
    out=A.audit(folder,git_root=root)
    assert out["failed"] > 0
    assert any(v["check"] == label for v in out["violations"]),out["violations"]
    assert not out["archive"]["selection"]["validated_selection"]


def scan_trial(recipe,stop_index,*,q=None,v=None,partial=False,env=False):
    records,_,_=recipe
    e=records[1][0]
    rows=deepcopy(records[2][:stop_index+1])
    terminal=rows[-1]
    terminal["observation_after"]=observation(terminal["requested_torque"][1],q=-.005 if q is None else q,v=0. if v is None else v)
    terminal["qpos"][8]=terminal["observation_after"]["joint_position"][1]
    terminal["qvel"][7]=terminal["observation_after"]["joint_velocity"][1]
    if stop_index >= 100:
        terminal["study_abort"]=A.study_abort(terminal["observation_after"]["joint_position"][1],terminal["observation_after"]["joint_velocity"][1],-.005,index=stop_index)
    if env or partial:
        terminal["environment_terminated"]=terminal["diagnostics"]["terminated"]=True
        terminal["environment_stop_reason"]=terminal["diagnostics"]["reason"]="joint_speed_limit"
    if partial:
        d=terminal["diagnostics"]
        d["executed_substeps"]=3
        for key in ("applied_torque_history","substep_ground_normal_forces","substep_kinetic_energies","substep_minimum_contact_distances"):d[key]=d[key][:3]
        d["ground_normal_impulse_ns"]=.006
        d["physics_steps"]=terminal["physics_steps_after"]=stop_index*10+3
        d["time"]=d["physics_steps"]*.002
        terminal["complete_transition"]=False
        terminal["partial_interval_target_error_rad"]=terminal["observation_after"]["joint_position"][1]-terminal["target_q_rad"]
    e["status"]="terminated" if stop_index >= 100 else "completed"
    state=A.new_state(e); checks=A.Checks()
    ranges=[[-1.,2.] for _ in range(8)]; ranges[1]=[0.,2.]
    for row in rows:A._consume(state,row,checks,ranges)
    return state,checks,terminal


@pytest.mark.parametrize("kind",["q","v","both"])
def test_native_equality_stop_preserves_independent_env_flag_and_full_terminal(recipe,kind):
    state,checks,row=scan_trial(recipe,100,q=.115 if kind in ("q","both") else None,v=1. if kind in ("v","both") else None)
    assert checks.failed == 0,checks.violations
    assert state["study_abort"] is not None and not state["environment_terminated"]
    assert len(state["tracking"]) == 1 and state["phase_complete"]["control"] == 1
    assert state["stopped"] and row["study_abort"]["feedback_action"] is None


def test_partial_excluded_primary_but_actual_cost_error_and_both_stops_retained(recipe):
    state,checks,row=scan_trial(recipe,100,v=1.,partial=True)
    assert checks.failed == 0,checks.violations
    assert not state["tracking"] and state["partial_errors"] == [row["partial_interval_target_error_rad"]]
    assert state["study_abort"] and state["environment_terminated"]
    assert state["phase_physics"]["control"] == 3
    assert state["phase_effort"]["control"][A.EFFORT_KEYS[1]] == pytest.approx(.16**2*.006)
    assert state["phase_effort"]["control"][A.EFFORT_KEYS[3]] == pytest.approx(.16**2*.006)


def test_prefix_has_no_research_abort_but_all_eight_joint_risk_is_measured(recipe):
    state,checks,row=scan_trial(recipe,5,v=1.)
    assert checks.failed == 0,checks.violations
    assert state["study_abort"] is None and not state["stopped"]
    assert state["risk"]["prefix"]["joint_speed_peak_rad_s"][1] == 1.


def test_no_transition_may_follow_independent_native_stop(recipe):
    state,checks,row=scan_trial(recipe,100,v=1.)
    nextrow=deepcopy(recipe[0][2][101]); nextrow["observation_before"]=row["observation_after"]
    A._consume(state,nextrow,checks,[[-1.,2.],[0.,2.]]+[[-1.,2.]]*6)
    assert any(x["check"] == "no_transition_after_study_or_environment_stop" for x in checks.violations)


def test_last_full_planned_step_stop_keeps_metrics_but_not_complete(recipe):
    state,checks,row=scan_trial(recipe,299,v=1.)
    assert checks.failed == 0,checks.violations
    assert state["rows"] == 300 and len(state["tracking"]) == 200 and state["stopped"]


@pytest.mark.parametrize("case",["request_effort","tiny_raw_difference","no_complete"])
def test_exact_three_seed_selection_no_truncated_candidate(case):
    trials=[]
    original=A.GAINS; A.GAINS=ALL_GAINS
    try:
        for seed in ALL_SEEDS:
            for i,(kp,kd) in enumerate(A.GAINS):
                trials.append({"trial_id":f"seed{seed}_candidate{i}","seed":seed,"candidate":i,"eligible":i < 2,
                    "tracking_rmse_rad":.1,"requested_squared_effort_nm2s":1. if i == 1 else 2.,"actual_squared_effort_nm2s":0. if i == 0 else 10.})
        if case == "tiny_raw_difference":
            for trial in trials:
                if trial["candidate"] == 0:trial["tracking_rmse_rad"] -= 1e-15
        if case == "no_complete":
            for trial in trials:trial["eligible"]=False
        selected=A.select_candidates(trials,seeds=ALL_SEEDS)
        if case == "no_complete":assert not selected["selection_success"] and selected["selected"] is None
        else:assert selected["selected"]["candidate"] == (0 if case == "tiny_raw_difference" else 1)
    finally:A.GAINS=original


def test_output_never_overwrites_or_writes_into_input_archive(tmp_path):
    archive=tmp_path/"input"; archive.mkdir()
    with pytest.raises(ValueError):A.validate_output_path(archive/"audit.json",[archive])
    existing=tmp_path/"existing.json"; existing.write_text("preserve")
    with pytest.raises(ValueError):A.validate_output_path(existing,[archive])
    assert existing.read_text() == "preserve"


def test_module_has_standard_library_only():
    assert "numpy" not in A.__dict__ and "mujoco" not in A.__dict__
def replace_first(records,episode,firstrows,*,fatal=False):
    meta,episodes,rows=records
    episodes[0]=episode
    rows[:]=firstrows+[r for r in rows if r["trial_id"] != episode["trial_id"]]
    if fatal:
        plan={k:episodes[1][k] for k in ("trial_id","seed","candidate","kp","kd","maximum_control_steps")}
        episodes[1]={**plan,"status":"blocked","reason":{"type":"ArchiveAborted"},"complete":False,
                     "control_calls_attempted":0,"control_steps":0,"physics_steps":0,
                     "phase_budgets":{p:dict(control_calls_attempted=0,control_steps=0,physics_steps=0) for p in A.PHASES}}
        rows[:]=firstrows
        meta.update(complete=False,archive_status="failed",collector_exception=episode["collector_exception"])
    meta["all_trials_successful"]=all(e["complete"] for e in episodes)
    for status in ("completed","terminated","exception","blocked"):
        meta[status+"_trials"]=sum(e["status"] == status for e in episodes)
    for key in A.BUDGET_KEYS:meta[key]=sum(e[key] for e in episodes)


def truncated_episode(recipe,*,partial=False,exception=None,returned=True,missing_history=False,trace_failure=False):
    records,_,_=recipe
    ep=deepcopy(records[1][0])
    terminal=deepcopy(records[2][100])
    request=terminal["requested_torque"]
    n=3 if partial or not returned else 10
    d=terminal["diagnostics"]
    if partial:
        d["executed_substeps"]=3
        for key in ("applied_torque_history","substep_ground_normal_forces","substep_kinetic_energies","substep_minimum_contact_distances"):d[key]=d[key][:3]
        d["ground_normal_impulse_ns"]=.006
        d["physics_steps"]=terminal["physics_steps_after"]=1003
        d["time"]=2.006
        d["terminated"]=terminal["environment_terminated"]=True
        d["reason"]=terminal["environment_stop_reason"]="joint_speed_limit"
        terminal["complete_transition"]=False
        terminal["partial_interval_target_error_rad"]=-.04
    if returned and not missing_history:
        terminal["observation_after"]["joint_velocity"][1]=1.
        terminal["qvel"][7]=1.
        terminal["study_abort"]=A.study_abort(-.005,1.,-.005,index=100)
    paid=1000+n
    complete=returned and not partial and not missing_history
    metric=int(complete)
    act=n if returned and not missing_history else 0
    healthy=returned and not missing_history
    controlrisk=risk(1) if healthy else risk(0)
    if healthy:
        controlrisk["ground_normal_impulse_ns"]=n*.002
        controlrisk["max_native_speed_rad_s"]=1.
    fullrisk=deepcopy(risk(100))
    if healthy:
        fullrisk["ground_normal_impulse_ns"] += n*.002
        fullrisk["max_native_speed_rad_s"]=1.
        fullrisk["outside_public_limit_endpoint_count"] += 1
    error=None if exception is None else {"type":exception,"message":"synthetic failure"}
    ep.update(status="exception" if error else "terminated",complete=False,collector_exception=error,
        reason=terminal["environment_stop_reason"] if partial else (terminal["study_abort"] if terminal["study_abort"] else error),
        study_abort=terminal["study_abort"],environment_terminated=partial,environment_stop_reason="joint_speed_limit" if partial else None,
        control_calls_attempted=101,control_steps=101 if returned else 100,physics_steps=paid,
        phase_budgets={"prefix":dict(control_calls_attempted=100,control_steps=100,physics_steps=1000),
                       "control":dict(control_calls_attempted=1,control_steps=int(returned),physics_steps=n)},
        metric_control_step_count=metric,tracking_rmse_rad=.04 if metric else None,
        phase_complete_transition_counts={"prefix":100,"control":int(complete)},
        partial_interval_target_errors_rad=[-.04] if partial else [],partial_interval_target_error_count=int(partial),
        phase_effort={"prefix":dict(requested_absolute_nm_s=0.,requested_squared_nm2_s=0.,actual_absolute_nm_s=0.,actual_squared_nm2_s=0.),
                      "control":dict(requested_absolute_nm_s=.16*n*.002,requested_squared_nm2_s=.16**2*n*.002,actual_absolute_nm_s=.16*act*.002,actual_squared_nm2_s=.16**2*act*.002)},
        requested_squared_effort_nm2s=.16**2*n*.002,
        phase_actual_effort_substeps={"prefix":1000,"control":act},
        phase_actual_effort_missing_substeps={"prefix":0,"control":n-act},
        phase_actual_effort_complete={"prefix":True,"control":n == act},actual_effort_complete=n == act,actual_effort_is_lower_bound=n != act,
        returned_control_steps=100+int(returned),trace_rows_written=100 if error else 101,
        returned_unstored_control_steps=int(returned) if error else 0,unreturned_physics_steps=0 if returned else n,
        saturated_control_steps=0,phase_risk={"full":fullrisk,"prefix":risk(100),"control":controlrisk},
        max_native_control_speed_rad_s=1. if healthy else 0.,peak_full_ground_force_n=1.,
        observed_diagnostic_substeps=1000+(n if healthy else 0),telemetry_complete_for_paid_substeps=healthy,
        risk_telemetry_complete=healthy and error is None,pd_action_calls=1,failed_pd_attempts=0,
        trace_write_failure=error if trace_failure else None)
    prefix=deepcopy(records[2][:100])
    if error is None:
        return ep,prefix+[terminal]
    ex={**terminal,"collector_exception":error,"returned_step_diagnostics":d if returned else None,
        "returned_observation_after":terminal["observation_after"] if returned else None,
        "returned_control_steps":100+int(returned),"trace_rows_written":100,
        "unreturned_physics_steps":0 if returned else n}
    if missing_history:
        ex["returned_step_diagnostics"]=deepcopy(d)
        ex["returned_step_diagnostics"].pop("applied_torque_history")
    if not returned:
        ex["control_steps_after"]=100
        ex["physics_steps_after"]=1003
        ex["diagnostics"]={"step_id":100,"physics_steps":1003,"time":2.006}
    return ep,prefix+[ex]


@pytest.mark.parametrize("partial",[False,True])
def test_archived_stop_scores_only_full_transition_and_keeps_both_reasons(recipe,tmp_path,partial):
    ep,rows=truncated_episode(recipe,partial=partial)
    replace_first(recipe[0],ep,rows)
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    trial=out["archive"]["trials"][0]
    assert not trial["eligible"] and trial["study_abort"] and trial["environment_terminated"] is partial
    assert (trial["tracking_rmse_rad"] is None) is partial
    assert out["archive"]["selection"]["selected"]["candidate"] == 1


@pytest.mark.parametrize("error",["RuntimeError","OSError","KeyboardInterrupt"])
def test_unreturned_paid_substeps_charge_request_keep_actual_lower_bound_and_fatal_block(recipe,tmp_path,error):
    ep,rows=truncated_episode(recipe,exception=error,returned=False)
    replace_first(recipe[0],ep,rows,fatal=error != "RuntimeError")
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    trial=out["archive"]["trials"][0]
    assert trial["paid_budget"]["physics_steps"] == 1003 and trial["observed_physics_steps"] == 1000
    assert trial["actual_effort_is_lower_bound"] and trial["phase_actual_effort_missing_substeps"]["control"] == 3
    assert trial["requested_squared_effort_nm2s"] == pytest.approx(.16**2*.006)
    assert trial["phase_effort"]["control"][A.EFFORT_KEYS[3]] == 0.
    if error != "RuntimeError":assert not out["archive"]["selection"]["selection_success"]


@pytest.mark.parametrize("partial",[False,True])
def test_returned_missing_history_preserves_cost_and_partial_error_without_zero_telemetry(recipe,tmp_path,partial):
    ep,rows=truncated_episode(recipe,exception="KeyError",returned=True,missing_history=True,partial=partial)
    replace_first(recipe[0],ep,rows)
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    trial=out["archive"]["trials"][0]
    assert trial["actual_effort_is_lower_bound"] and trial["phase_actual_effort_missing_substeps"]["control"] == (3 if partial else 10)
    assert trial["tracking_rmse_rad"] is None
    assert trial["partial_interval_target_errors_rad"] == ([-.04] if partial else [])
    assert trial["returned_control_steps"] == 101 and trial["trace_rows"] == 100


def test_healthy_returned_but_unstored_trace_failure_is_recovered_and_fatal(recipe,tmp_path):
    ep,rows=truncated_episode(recipe,exception="ValueError",trace_failure=True)
    replace_first(recipe[0],ep,rows,fatal=True)
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    trial=out["archive"]["trials"][0]
    assert not trial["eligible"] and trial["actual_effort_complete"]
    assert trial["tracking_rmse_rad"] == .04 and trial["trace_rows"] == 100 and trial["returned_control_steps"] == 101
    assert trial["observed_physics_steps"] == 1010


def test_full_planned_27trial_archive_and_entry_timer(monkeypatch,source_git,tmp_path):
    monkeypatch.setattr(A,"SEEDS",ALL_SEEDS); monkeypatch.setattr(A,"GAINS",ALL_GAINS)
    records=grid(); sources,root,commit=source_git
    records[0].update(source_commit=commit,source_sha256={k:hashlib.sha256(v).hexdigest() for k,v in sources.items()},protocol={"path":A.PROTOCOL,"sha256":hashlib.sha256(sources[A.PROTOCOL]).hexdigest()})
    out=report(tmp_path,(records,sources,root))
    assert out["failed"] == 0,out["violations"]
    assert len(out["archive"]["trials"]) == 27 and out["archive"]["budget"]["physics_steps"] == 81000
    assert out["archive"]["phase_budget"]["prefix"]["physics_steps"] == 27000
    assert out["archive"]["phase_budget"]["control"]["physics_steps"] == 54000
    assert out["archive"]["source_sha256"] == records[0]["source_sha256"]
    assert out["execution"] == {"physical_control_calls":0,"physics_substeps":0,"model_updates":0,"policy_updates":0,"gain_updates":0}
    for key in ("wall_seconds","cpu_seconds"):assert isinstance(out["analysis_runtime"][key],float) and out["analysis_runtime"][key] >= 0
def test_pd_request_failure_before_step_keeps_old_paid_prefix_distinct(recipe,tmp_path):
    ep,rows=truncated_episode(recipe,exception="ValueError",returned=False)
    e=ep["collector_exception"]
    ep.update(control_calls_attempted=100,control_steps=100,physics_steps=1000,
        phase_budgets={"prefix":dict(control_calls_attempted=100,control_steps=100,physics_steps=1000),"control":dict(control_calls_attempted=0,control_steps=0,physics_steps=0)},
        phase_actual_effort_substeps={"prefix":1000,"control":0},phase_actual_effort_missing_substeps={"prefix":0,"control":0},
        phase_actual_effort_complete={"prefix":True,"control":True},actual_effort_complete=True,actual_effort_is_lower_bound=False,
        unreturned_physics_steps=0,telemetry_complete_for_paid_substeps=True,pd_action_calls=1,failed_pd_attempts=1,
        requested_squared_effort_nm2s=0.)
    ep["phase_effort"]["control"]={k:0. for k in ep["phase_effort"]["control"]}
    row=rows[-1]
    row.update(control_steps_before=None,physics_steps_before=None,control_steps_after=100,physics_steps_after=1000,
        requested_torque=[0.]*8,raw_pd_torque_nm=None,unreturned_physics_steps=0,
        diagnostics={"step_id":100,"physics_steps":1000,"time":2.})
    replace_first(recipe[0],ep,rows)
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    trial=out["archive"]["trials"][0]
    assert trial["paid_budget"]["control_calls_attempted"] == 100 and trial["actual_effort_complete"]
    assert trial["requested_squared_effort_nm2s"] == 0. and trial["tracking_rmse_rad"] is None


def test_last_planned_full_terminal_study_stop_is_archived_ineligible(recipe,tmp_path):
    records,_,_=recipe
    ep=records[1][0]; row=records[2][299]
    row["observation_after"]["joint_velocity"][1]=row["qvel"][7]=1.
    verdict=A.study_abort(-.005,1.,-.005,index=299)
    row["study_abort"]=ep["study_abort"]=verdict
    ep.update(status="terminated",complete=False,reason=verdict)
    ep["phase_risk"]["full"]["max_native_speed_rad_s"]=ep["phase_risk"]["control"]["max_native_speed_rad_s"]=ep["max_native_control_speed_rad_s"]=1.
    records[0].update(all_trials_successful=False,terminated_trials=1,completed_trials=1)
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    trial=out["archive"]["trials"][0]
    assert not trial["eligible"] and trial["complete_transition_counts"]["control"] == 200
    assert out["archive"]["selection"]["selected"]["candidate"] == 1


def test_any_trace_write_failure_requires_all_remaining_blocked(recipe,tmp_path):
    ep,rows=truncated_episode(recipe,exception="ValueError",trace_failure=True)
    replace_first(recipe[0],ep,rows)
    recipe[0][0].update(complete=False,archive_status="failed",collector_exception=ep["collector_exception"])
    out=report(tmp_path,recipe)
    assert out["failed"] > 0
    assert any(v["check"] == "fatal_blocks_every_remaining_planned_trial" for v in out["violations"])
    assert not out["archive"]["selection"]["validated_selection"]


@pytest.mark.parametrize("file",["manifest.json","trace.jsonl.gz","episodes.json"])
def test_unreadable_input_retains_reported_paid_budget_as_unrecomputed(recipe,tmp_path,file):
    records,sources,root=recipe
    folder=tmp_path/"archive"; write(folder,records,sources)
    (folder/file).write_bytes(b"synthetic corrupt bytes")
    out=A.audit(folder,git_root=root)
    assert out["failed"] > 0
    assert out["archive"]["reported_budget"]["physics_steps"] == 6000
    assert out["archive"]["budget"]["physics_steps"] == 6000
    assert out["archive"]["budget"]["recomputed_from_episode_ledgers"] is False
    assert out["archive"]["source_sha256"] == records[0]["source_sha256"]
    assert not out["archive"]["selection"]["validated_selection"]


def test_missing_real_transitive_dependency_cannot_be_hidden_by_rehash(recipe,tmp_path):
    records,sources,root=recipe
    sources=deepcopy(sources)
    name="src/developmental_physics/local_model.py"
    del sources[name]; del records[0]["source_sha256"][name]
    out=report(tmp_path,(records,sources,root))
    assert out["failed"] > 0
    assert any(v["check"] == "required_source_files" for v in out["violations"])


def test_shield_history_cost_and_all_joint_speed_are_independently_measured(recipe):
    e=deepcopy(recipe[0][1][0]); e["status"]="terminated"
    rows=deepcopy(recipe[0][2][:101]); row=rows[-1]
    row["observation_after"]["joint_velocity"][7]=row["qvel"][13]=3.
    row["diagnostics"]["applied_torque_history"]=[list(values) for values in row["diagnostics"]["applied_torque_history"]]
    row["diagnostics"]["applied_torque_history"][0][1]=0.
    row["diagnostics"]["guarded_substeps"]=1
    state=A.new_state(e); checks=A.Checks()
    for entry in rows:A._consume(state,entry,checks,[[-1.,2.],[0.,2.]]+[[-1.,2.]]*6)
    assert checks.failed == 0,checks.violations
    assert state["study_abort"] is None
    assert state["risk"]["control"]["joint_speed_peak_rad_s"][7] == 3.
    assert state["risk"]["control"]["joint_requested_but_shielded_substeps"][1] == 1
    assert state["phase_effort"]["control"][A.EFFORT_KEYS[3]] == pytest.approx(.16**2*.018)


def test_missing_trial_remains_explicit_and_disqualifies_candidate(recipe,tmp_path):
    records,sources,root=recipe
    records[1].pop(0)
    records[2][:]=[r for r in records[2] if r["trial_id"] != "seed0_candidate0"]
    out=report(tmp_path,recipe)
    assert out["failed"] > 0
    assert out["archive"]["trials"][0]["status"] == "missing" and not out["archive"]["trials"][0]["eligible"]
    assert not out["archive"]["selection"]["validated_selection"]


def test_unreturned_failed_step_still_requires_the_fixed_pd_request(recipe,tmp_path):
    ep,rows=truncated_episode(recipe,exception="RuntimeError",returned=False)
    rows[-1]["requested_torque"][1]=.3
    ep["phase_effort"]["control"].update(requested_absolute_nm_s=.3*.006,requested_squared_nm2_s=.3**2*.006)
    ep["requested_squared_effort_nm2s"]=.3**2*.006
    replace_first(recipe[0],ep,rows)
    out=report(tmp_path,recipe)
    assert out["failed"] > 0
    assert any(v["check"] == "unreturned_exception_independent_requested_pd" for v in out["violations"])
    assert not out["archive"]["selection"]["validated_selection"]


def test_first_prefix_step_failure_preserves_missing_telemetry_without_invented_previous_sample(recipe,tmp_path):
    records,_,_=recipe
    ep=deepcopy(records[1][0])
    error={"type":"RuntimeError","message":"synthetic first prefix substep failure"}
    zero=dict(requested_absolute_nm_s=0.,requested_squared_nm2_s=0.,actual_absolute_nm_s=0.,actual_squared_nm2_s=0.)
    ep.update(status="exception",complete=False,reason=error,collector_exception=error,
        control_calls_attempted=1,control_steps=0,physics_steps=3,
        phase_budgets={"prefix":dict(control_calls_attempted=1,control_steps=0,physics_steps=3),"control":dict(control_calls_attempted=0,control_steps=0,physics_steps=0)},
        prefix_end_q_rad=None,selection_record=None,metric_control_step_count=0,tracking_rmse_rad=None,
        phase_complete_transition_counts={"prefix":0,"control":0},
        phase_effort={"prefix":zero,"control":zero},requested_squared_effort_nm2s=0.,
        phase_actual_effort_substeps={"prefix":0,"control":0},phase_actual_effort_complete={"prefix":False,"control":True},
        phase_actual_effort_missing_substeps={"prefix":3,"control":0},actual_effort_complete=False,actual_effort_is_lower_bound=True,
        returned_control_steps=0,trace_rows_written=0,returned_unstored_control_steps=0,unreturned_physics_steps=3,
        saturated_control_steps=0,phase_risk={p:risk(0) for p in ("full","prefix","control")},
        peak_full_ground_force_n=0.,observed_diagnostic_substeps=0,telemetry_complete_for_paid_substeps=False,risk_telemetry_complete=False,
        pd_action_calls=0,failed_pd_attempts=0,pd_action_seconds=0.)
    row={k:ep[k] for k in ("trial_id","seed","candidate","kp","kd")}
    row.update(collector_exception=error,control_index=0,phase="prefix",requested_torque=[0.]*8,raw_pd_torque_nm=None,target_q_rad=None,
        observation_before=observation(),control_steps_before=0,control_steps_after=0,physics_steps_before=0,physics_steps_after=3,
        returned_step_diagnostics=None,returned_observation_after=None,returned_control_steps=0,trace_rows_written=0,unreturned_physics_steps=3)
    replace_first(records,ep,[row])
    out=report(tmp_path,recipe)
    assert out["failed"] == 0,out["violations"]
    trial=out["archive"]["trials"][0]
    assert trial["paid_budget"]["physics_steps"] == 3 and trial["observed_physics_steps"] == 0
    assert trial["actual_effort_is_lower_bound"] and trial["phase_actual_effort_missing_substeps"]["prefix"] == 3
