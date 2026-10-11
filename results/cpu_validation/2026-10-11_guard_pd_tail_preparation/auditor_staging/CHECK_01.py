"""First necessary G audit-tail math/accounting/interface fixture only."""
from pathlib import Path
from collections import Counter
import ast
import copy
import hashlib
import importlib.util
import json
import math
import sys
import time

ROOT=Path(__file__).parent
OUTPUT=ROOT/'CHECK_01.json'
if OUTPUT.exists():raise RuntimeError('preserve first fixture result; do not rerun')
started_wall,started_cpu=time.perf_counter(),time.process_time()
source=ROOT/'audit_guard_pd_tail_control.py'
source_blob=source.read_bytes()
baseline_blob=(ROOT/'audit_guard_lag_control.baseline.original.py').read_bytes()
spec=importlib.util.spec_from_file_location('_G_first_independent_tail_fixture',source)
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
original_predict=a.lag.predict11
before_math=Counter(a.lag.MATH_COST)
before_counts=Counter(a.COUNTS)
checks=[]
fake_calls=[]
fake_predict_calls=0

def assert_check(condition,label,actual=None):
    checks.append({'label':label,'passed':bool(condition),'actual':actual if not condition else None})

def close(left,right):
    return abs(left-right)<=1e-12

def fake_predict(theta,ranges,qref,q,v,u,pv):
    global fake_predict_calls
    fake_predict_calls+=1
    fake_calls.append({'q':list(q),'v':list(v),'u':list(u),'pv':list(pv)})
    return [q[i]+.001*u[i] for i in range(2)],[.5*v[i]+.02*u[i] for i in range(2)]

try:
    a.lag.predict11=fake_predict
    arguments=(None,[[-2.,2.],[-2.,2.]],[0.,0.],[.01,-.01],[.1,-.2],[.02,-.03],[.012,-.008],[.125,-.125])
    item=a.candidate_math(*arguments,[.125,-.125])
    requests=item['trajectory_requested_torque']
    assert_check(item['candidate_record']['feasible'] and len(requests)==15,'new_tail_candidate_complete_H15')
    assert_check(requests[0]==[.125,-.125] and close(requests[1][0],.12) and requests[1][1]==.5,'new_tail_uses_first_predicted_state_and_fixed_axis_gains')
    assert_check(any(request!=requests[0] for request in requests[1:]),'new_tail_is_not_constant_first_request')
    assert_check(all(fake_calls[h]['pv']==fake_calls[h-1]['v'] for h in range(1,15)) and fake_calls[0]['pv']==arguments[5],'new_tail_advances_each_candidates_own_old_current_velocity')
    cost=sum(.00002*(requests[0][i]-arguments[7][i])**2 for i in range(2))
    cost+=sum((item['predicted_q'][h][i]-arguments[6][i])**2+.002*item['predicted_v'][h][i]**2+.00002*requests[h][i]**2 for h in range(15) for i in range(2))
    wrong_constant_effort=cost-sum(.00002*requests[h][i]**2 for h in range(15) for i in range(2))+15*sum(.00002*u*u for u in requests[0])
    wrong_every_stage_change=cost+sum(.00002*(requests[h][i]-requests[h-1][i])**2 for h in range(1,15) for i in range(2))
    assert_check(close(item['candidate_record']['cost'],cost) and not close(cost,wrong_constant_effort),'new_tail_stage_effort_uses_each_request')
    assert_check(not close(cost,wrong_every_stage_change),'new_tail_change_cost_first_request_only')
    fake_calls.clear()
    decision=a.replay_mpc(*arguments)
    assert_check(len(decision['candidate_records'])==81 and decision['pair_prediction_attempts']==1215 and decision['scalar_prediction_attempts']==2430,'new_tail_all_81_candidates_and_paid_H15_predictions')
    assert_check(all(fake_calls[15*k]['pv']==arguments[5] and fake_calls[15*k]['q']==arguments[3] for k in range(81)),'new_tail_independent_candidate_initial_histories')
    assert_check(len(decision['trajectory_requested_torque'])==15 and decision['trajectory_requested_torque'][0]==decision['torque'],'new_tail_selected_trajectory_requests_interface')
    checks_object=a.Checks()
    altered=copy.deepcopy(decision);altered['trajectory_requested_torque'][1][0]+=.001
    checks_object.compare(altered,decision,'fixture/new_selected_request_tamper')
    assert_check(checks_object.failed>0,'new_tail_saved_request_tamper_detected')
    row={'step_index':100,'shared_transition_id':'fixture:100','planner_decision':decision,'planner_input':{}}
    feechecks=a.Checks()
    paid=a.paid_tail_requests('cold11',[row],[copy.deepcopy(row)],feechecks,'fixture')
    assert_check(feechecks.failed==0 and paid=={'known_first_candidate_evaluations':81,'known_tail_vector_evaluations':1134,'counts_complete':True,'counts_is_lower_bound':False,'unknown_failed_planner_calls':0},'new_tail_complete_decision_paid_count_and_duplicate_notice')
    failed={'step_index':101,'shared_transition_id':'fixture:101','planner_decision':None,'planner_input':{}}
    lower=a.paid_tail_requests('cold11',[row],[failed],a.Checks(),'fixture')
    assert_check(lower['known_tail_vector_evaluations']==1134 and not lower['counts_complete'] and lower['counts_is_lower_bound'] and lower['unknown_failed_planner_calls']==1,'new_tail_unrecorded_planner_work_is_unknown_lower_bound')
    broken=copy.deepcopy(row);broken['planner_decision']['candidate_records'].pop()
    malformed_checks=a.Checks();malformed=a.paid_tail_requests('cold11',[broken],[],malformed_checks,'fixture')
    assert_check(malformed_checks.failed>0 and not malformed['counts_complete'] and malformed['counts_is_lower_bound'],'new_tail_incomplete_81_record_coverage_not_exact_paid_count')
    def rejected_predict(theta,ranges,qref,q,v,u,pv):
        global fake_predict_calls
        fake_predict_calls+=1
        fake_calls.append({'rejection':True})
        return [.2,.2],[0.,0.]
    a.lag.predict11=rejected_predict
    rejected=a.replay_mpc(*arguments)
    assert_check(rejected['fallback'] and rejected['trajectory_requested_torque']==[] and rejected['pair_prediction_attempts']==81,'new_tail_rejected_first_endpoints_paid_empty_fallback_trajectory')
    rejected_row={'step_index':100,'shared_transition_id':'rejected:100','planner_decision':rejected,'planner_input':{}}
    rejected_paid=a.paid_tail_requests('cold11',[rejected_row],[],a.Checks(),'fixture')
    assert_check(rejected_paid['known_first_candidate_evaluations']==81 and rejected_paid['known_tail_vector_evaluations']==0,'new_tail_no_tail_started_after_first_endpoint_rejection')
    metadata={'planner_variant':'first_free_fixed_pd_tail','tail_policy':copy.deepcopy(a.TAIL_METADATA),
        'maximum_tail_request_vector_evaluations':1360800,'maximum_first_request_candidate_evaluations':97200,
        'tail_request_accounting':copy.deepcopy(a.TAIL_ACCOUNTING_METADATA)}
    mchecks=a.Checks();a.verify_tail_metadata(metadata,mchecks)
    assert_check(mchecks.failed==0,'new_tail_metadata_fixed_gains_caps_and_accounting_contract')
    metadata['tail_policy']['kd'][1]=5.
    badchecks=a.Checks();a.verify_tail_metadata(metadata,badchecks)
    assert_check(badchecks.failed>0,'new_tail_changed_gain_metadata_rejected')
    try:a.audit(Path('never_read_fake_archive'))
    except RuntimeError:formal_closed=True
    else:formal_closed=False
    assert_check(formal_closed,'new_G_formal_archive_entry_disabled_without_read')
    old_tree=ast.parse(baseline_blob);new_tree=ast.parse(source_blob)
    old_functions={node.name:ast.dump(node,include_attributes=False) for node in old_tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    new_functions={node.name:ast.dump(node,include_attributes=False) for node in new_tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    retained=('physical_base','state_from_snapshot','bind_d_states','native_history','verify_reference','prediction_math','development_comparison','validate_failed_planning')
    for name in retained:
        assert_check(old_functions[name]==new_functions[name],'retained_E_source_AST_only:'+name)
    assert_check(not any(name.startswith('developmental_physics') for name in sys.modules),'new_G_fixture_no_online_model_planner_runner_import')
except BaseException as exc:
    checks.append({'label':'fixture_unhandled_exception','passed':False,'actual':{'type':type(exc).__name__,'message':str(exc)}})
finally:
    a.lag.predict11=original_predict
    result={'schema_version':1,'scope':'necessary new G audit-tail math/accounting/interface fixtures once; no old E/tail fixture rerun',
        'source_sha256':hashlib.sha256(source_blob).hexdigest(),'source_bytes':len(source_blob),
        'baseline_sha256':hashlib.sha256(baseline_blob).hexdigest(),'baseline_bytes':len(baseline_blob),
        'checks':checks,'passed':sum(item['passed'] for item in checks),'failed':sum(not item['passed'] for item in checks),
        'manual_fake_predict_calls':fake_predict_calls,'independent_G_fixture_replay_counts':dict(a.COUNTS-before_counts),
        'original_independent_model_math_cost_delta':dict(a.lag.MATH_COST-before_math),
        'explicit_source_read_opens':2,'explicit_source_read_bytes':len(source_blob)+len(baseline_blob),
        'source_module_imports':'Python import and original independent support loading are nonzero source-only work, excluded from explicit two-file content read count',
        'wall_seconds':time.perf_counter()-started_wall,'cpu_seconds':time.process_time()-started_cpu,
        'timing_scope':'entry through fixture and report assembly; excludes final CHECK JSON serialization/write',
        'new_physical_calls':0,'actual_E_C_D_F_data_reads':0,'online_model_predict_calls':0,'fit_or_update_calls':0,
        'scientific_adoption':{'evaluated':False,'passed':False},'formal_audit_enabled':a.FORMAL_AUDIT_ENABLED}
    OUTPUT.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'failed':result['failed'],'wall_seconds':result['wall_seconds'],'counts':result['independent_G_fixture_replay_counts'],'manual_fake_predict_calls':result['manual_fake_predict_calls'],'original_math_delta':result['original_independent_model_math_cost_delta']}))
raise SystemExit(bool(result['failed']))
