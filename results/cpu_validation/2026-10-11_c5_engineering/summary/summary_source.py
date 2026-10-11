"""One read-only C5 summary: existing raw/audit facts, no collector or learning.

Preparing/importing this file never reads the expected experiment directory.
Only an explicitly invoked main reads the user-specified raw/audit once.
"""
from collections import Counter
from datetime import datetime,timezone
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time

KINDS=('base_identity','wrapper_identity','gain_half','armature_double')
BUDGET_KEYS=('control_calls_attempted','control_steps','known_physics_substeps_lower_bound',
             'unknown_original_step_attempts','returned_endpoints')
INVARIANTS=('qpos','qvel','ctrl','last_command','time','step_id','physics_steps')


def sha(value): return hashlib.sha256(value).hexdigest()


def effort(value):
    if not isinstance(value,list) or len(value)!=8:
        raise ValueError('eight native joint effort records required')
    result=[]
    for row in value:
        record={}
        for key in ('absolute_nm_s','squared_nm2_s'):
            number=row[key]
            if type(number) not in (int,float) or not math.isfinite(number) or number<0:
                raise ValueError('finite nonnegative effort required')
            record[key]=number
        result.append(record)
    return result


def build_summary(metadata,outcomes,events,audit):
    """Pure arithmetic over supplied records; no filesystem/simulator access."""
    violations=[];checks=0
    def check(condition,label):
        nonlocal checks
        checks+=1
        if not condition: violations.append(label)
    def close(left,right):
        return all(abs(a[key]-b[key])<=1e-12 for a,b in zip(left,right)
                   for key in ('absolute_nm_s','squared_nm2_s'))
    check([o['kind'] for o in outcomes]==list(KINDS),'fixed_trial_order')
    if len(outcomes)!=4: raise ValueError('all four planned outcomes required, including blocked')
    totals={key:0 for key in BUDGET_KEYS};trial_summaries=[]
    requested=[{'absolute_nm_s':0.,'squared_nm2_s':0.} for _ in range(8)]
    actual=[{'absolute_nm_s':0.,'squared_nm2_s':0.} for _ in range(8)]
    lower=False;force_lower=False
    archive=audit.get('archive')
    for outcome in outcomes:
        budget={key:outcome[key] for key in BUDGET_KEYS}
        if any(type(number) is not int or number<0 for number in budget.values()):
            raise ValueError('nonnegative integer recorded budgets required')
        for key,number in budget.items(): totals[key]+=number
        status=outcome['status'];check(status in ('completed','terminated','exception','blocked'),'status:'+outcome['kind'])
        if status=='blocked': check(all(number==0 for number in budget.values()),'blocked_zero_cost:'+outcome['kind'])
        req=effort(outcome.get('known_requested_effort_by_joint',[{'absolute_nm_s':0.,'squared_nm2_s':0.}]*8))
        act=effort(outcome.get('known_actual_force_effort_by_joint',[{'absolute_nm_s':0.,'squared_nm2_s':0.}]*8))
        for i in range(8):
            for key in requested[i]: requested[i][key]+=req[i][key];actual[i][key]+=act[i][key]
        if archive is not None and outcome['kind'] in archive.get('effort',{}):
            independent=archive['effort'][outcome['kind']]
            check(close(req,effort(independent['requested'])),'audit_requested_effort:'+outcome['kind'])
            check(close(act,effort(independent['actual'])),'audit_actual_effort:'+outcome['kind'])
        trial_lower=bool(outcome.get('actual_budget_is_lower_bound',False) or budget['unknown_original_step_attempts'])
        actual_lower=bool(outcome.get('actual_force_effort_is_lower_bound',False)
            or outcome.get('known_actual_force_substeps',0)!=budget['known_physics_substeps_lower_bound']
            or budget['unknown_original_step_attempts'])
        lower|=trial_lower;force_lower|=actual_lower
        trial_summaries.append({'kind':outcome['kind'],'status':status,'budget':budget,
            'actual_budget_is_lower_bound':trial_lower,'actual_force_effort_is_lower_bound':actual_lower,
            'known_actual_force_substeps':outcome.get('known_actual_force_substeps',0),
            'known_requested_effort_by_joint':req,'known_actual_force_effort_by_joint':act,
            'study_abort':outcome.get('study_abort'),'environment_terminated':outcome.get('environment_terminated'),
            'stop_step_index':outcome.get('stop_step_index'),'exception':outcome.get('exception'),
            'blocked_by':outcome.get('blocked_by'),'reference_q_rad':outcome.get('reference_q_rad')})
    totals['model_parameter_updates']=0
    check(metadata['actual_budget']==totals,'metadata_total_budget')
    counts=dict(Counter(o['status'] for o in outcomes));check(metadata['outcome_counts']==counts,'metadata_outcome_counts')
    for key in ('model_parameter_updates','policy_updates','teacher_calls'):
        check(metadata[key]==0,'zero_'+key)
    complete=all(o['status']=='completed' for o in outcomes)
    check(metadata['all_four_complete']==complete,'metadata_complete_matrix')
    identity=metadata['identity_check']
    if archive is not None:
        check(archive['budget']==totals,'audit_total_budget')
        check(archive['outcome_counts']==counts,'audit_outcome_counts')
        check(archive['all_four_complete']==complete,'audit_complete_matrix')
        check(identity['validated_identity']==bool(archive['identity_rows_complete'] and archive['identity_match']),'audit_identity')
    event_summaries=[]
    for event in events:
        before,after=event.get('before_live',{}),event.get('after_live',{})
        change=event.get('mass_matrix_change') or {}
        invariants={key:before.get(key)==after.get(key) for key in INVARIANTS if key in before and key in after}
        check(event['kind'] in KINDS,'event_kind')
        check(event['step_boundary']==100,'event_boundary')
        if event['status'] in ('applied','not_applicable'):
            check(len(invariants)==len(INVARIANTS) and all(invariants.values()),'event_persistent_state:'+event['kind'])
        event_summaries.append({'kind':event['kind'],'status':event['status'],'step_boundary':event['step_boundary'],
            'persistent_state_invariants':invariants,'before_ctrl_nm':before.get('ctrl'),'after_ctrl_nm':after.get('ctrl'),
            'before_armature':before.get('armature'),'after_armature':after.get('armature'),
            'plant_fingerprint_changed':before.get('plant_fingerprint')!=after.get('plant_fingerprint'),
            'base_fingerprint_changed':before.get('base_fingerprint')!=after.get('base_fingerprint'),
            'mass_matrix_change':change,'error':event.get('error')})
    if complete: check([e['kind'] for e in events]==list(KINDS),'complete_event_inventory')
    independent_pass=bool(audit['engineering_pass'])
    if independent_pass:
        check(audit['failed']==0 and not audit['synthetic_fixture'],'engineering_audit_scope')
        check(complete and bool(identity['validated_identity']),'engineering_complete_identity')
    check(audit['learning_or_adaptation_validated'] is False,'audit_has_no_adaptation_evidence')
    return {'scope':'C5 fixed engineering event/instrumentation check; zero learning',
        'summary_consistency':{'checks':checks,'failed':len(violations),'violations':violations},
        'planned_budget':{'control_calls':480,'physics_substeps':4800,'model_parameter_updates':0},
        'actual_budget':totals,'actual_budget_is_lower_bound':lower,
        'actual_force_effort_is_lower_bound':force_lower,'outcome_counts':counts,'all_four_complete':complete,
        'trials':trial_summaries,'parameter_events':event_summaries,'identity':identity,
        'effort_totals_by_native_joint':{'known_requested':requested,'known_actual_force':actual},
        'audit':{'checks':audit['checks'],'failed':audit['failed'],'engineering_pass':independent_pass,
            'audit_script_sha256':audit.get('audit_script_sha256'),'synthetic_fixture':audit['synthetic_fixture']},
        'engineering_pass_from_independent_audit':independent_pass,
        'engineering_report_consistent':not violations,
        'model_parameter_updates':0,'policy_updates':0,'teacher_calls':0,
        'learning_or_adaptation_validated':False,'causal_algorithm_advantage_validated':False,
        'source_binding':metadata.get('source_binding'),'raw_source_sha256':metadata.get('source_sha256'),
        'collector_execution':{'wall_seconds':metadata.get('wall_seconds'),'cpu_seconds':metadata.get('cpu_seconds')},
        'audit_execution':audit.get('execution'),
        'interpretation':'Mechanical gain/armature changes and accounting alone are not adaptation, skill learning or algorithm advantage.'}


def read_once(raw,audit_path):
    """Called only after explicit execution authorization; no retry or polling."""
    manifest_bytes=(raw/'manifest.json').read_bytes();manifest=json.loads(manifest_bytes)
    if any(Path(name).name!=name for name in manifest): raise ValueError('flat raw manifest names required')
    expected=set(manifest)|{'manifest.json'}
    if {p.name for p in raw.iterdir() if p.is_file()}!=expected:
        raise ValueError('raw inventory differs from manifest; preserve failure, do not repair')
    data={'manifest.json':manifest_bytes}
    for name,expected_sha in manifest.items():
        value=(raw/name).read_bytes();data[name]=value
        if sha(value)!=expected_sha: raise ValueError('raw manifest hash mismatch: '+name)
    audit_bytes=audit_path.read_bytes()
    parsed=[json.loads(data[name]) for name in ('metadata_final.json','trial_outcomes.json','parameter_events.json')]
    return (*parsed,json.loads(audit_bytes),{name:sha(value) for name,value in data.items()},sha(audit_bytes))


def write_once(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False);stream.write('\n')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True);parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);raw=args.raw.resolve();audit_path=args.audit.resolve();output=args.output.resolve()
    if output.is_relative_to(raw): parser.error('Use a new summary directory outside immutable raw')
    output.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).read_bytes()
    with (output/'summary_source.py').open('xb') as stream: stream.write(source)
    source_sha=sha(source);wall,cpu=time.perf_counter(),time.process_time()
    write_once(output/'attempt.json',{'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'raw':str(raw),'audit':str(audit_path),'summary_source_sha256':source_sha,
        'scope':'One explicit readonly summary invocation, no collector/physics/Git/model updates'})
    status=1;result=None;failure=None
    try:
        metadata,outcomes,events,audit,input_hashes,audit_sha=read_once(raw,audit_path)
        result=build_summary(metadata,outcomes,events,audit)
        result.update(input_raw_sha256=input_hashes,input_audit_sha256=audit_sha,summary_source_sha256=source_sha)
        write_once(output/'summary.json',result)
        status=1 if result['summary_consistency']['failed'] else 0
    except BaseException as exc:
        failure={'type':type(exc).__name__,'message':str(exc)}
        write_once(output/'failure.json',{'error':failure,'no_retry':True,'summary_source_sha256':source_sha})
    execution={'exit_code':status,'failure':failure,'wall_seconds':time.perf_counter()-wall,
        'same_process_cpu_seconds':time.process_time()-cpu,'summary_source_sha256':source_sha,
        'physical_calls':0,'model_parameter_updates':0,'collector_imports':0,'real_git_calls':0,
        'audit_reruns':0,'input_collection_reads_attempted':1}
    write_once(output/'execution.json',execution)
    printed=json.dumps({'execution':execution,'actual_budget':None if result is None else result['actual_budget'],
        'engineering_pass_from_independent_audit':None if result is None else result['engineering_pass_from_independent_audit']},ensure_ascii=False)
    with (output/'stdout.txt').open('x',encoding='utf-8') as stream: stream.write(printed+'\n')
    print(printed);return status


if __name__=='__main__': raise SystemExit(main())
