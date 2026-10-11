"""Finite K output contract, without refitting or recomputing scientific metrics."""
import hashlib
import json
from pathlib import Path
import time
root=Path(__file__).resolve().parents[1]
out=root/'external/c4_k_native_transition_01'
report=root/'external/c4_k_output_check_01.json'
assert not report.exists()
started,cpu=time.perf_counter(),time.process_time()
reads,size,checks=0,0,[]
def read(path):
    global reads,size
    data=path.read_bytes(); reads+=1; size+=len(data); return data
def check(name,condition): checks.append({'name':name,'passed':bool(condition)})
manifest=json.loads(read(out/'manifest.json')); docs={}
for name,binding in manifest['files'].items():
    data=read(out/name)
    check('bytes_and_sha_'+name,len(data)==binding['bytes'] and hashlib.sha256(data).hexdigest()==binding['sha256'])
    if name.endswith('.json'): docs[name]=json.loads(data)
    elif name=='predictions.jsonl': check('all_fixed_prediction_records',len(data.splitlines())==3429)
run,metrics=docs['run.json'],docs['metrics.json']; cost=run['cost']
check('complete_source_inputs',run['status']=='completed' and len(run['inputs'])==6 and run['source']['clean_committed_bytes_verified'])
check('D_restorations_and_immutability',cost['D11_restoration_attempts']==cost['D11_restoration_returns']==3 and run['D11_fingerprints_before']==run['D11_fingerprints_after'])
check('fixed_fit_budget',cost['fit_scalar_labels']<=26400 and cost['fit_shared_29x29_22rhs_solve_attempts']<=3 and cost['fit_shared_29x29_22rhs_solve_returns']<=cost['fit_shared_29x29_22rhs_solve_attempts'] and cost['transition_scalar_coefficients_fitted']<=1914)
check('fixed_rollout_budgets',all(cost[k]<=6204 for k in ('cold22_transition_attempts','learned22_transition_attempts','D11_pair_prediction_attempts')) and cost['D11_scalar_prediction_attempts']<=12408)
check('all_channel_groups_retained',len(metrics['groups'])==576)
check('all_source_trial_counts',all(run['source_active_counts'][f'seed{s}_{k}']==n for s in (0,1,2) for k,n in (('calibration_sparse',400),('prediction',100))))
check('no_physics_or_base_updates',all(cost[k]==0 for k in ('physics_calls','physics_substeps','MPC_calls','RLS_updates','D11_updates')))
check('scientific_dependencies_closed',all(metrics[k] is False for k in ('scientific_adoption','c4_scientific_validation','c5_scientific_dependency_released')) and metrics['development_gate']['D_old_gate_reinterpreted'] is False)
record={'scope':'output byte identity and reported budget/count/dependency declarations only; model, metrics and gate not recomputed','first_attempt':True,'checks':checks,'failures':sum(not r['passed'] for r in checks),'cost':{'binary_reads':reads,'input_bytes':size,'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu},'actual_C_D_payload_reads':0,'fits':0,'model_calls':0,'physics':0}
report.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
