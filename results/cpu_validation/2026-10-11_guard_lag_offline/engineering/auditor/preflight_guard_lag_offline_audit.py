"""Only final schema AST alignment and the newly edited failed-RLS ledger branch."""
from collections import Counter
from contextlib import redirect_stdout
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'pyproject.toml').is_file())
SOURCE=HERE/'audit_guard_lag_offline.py'
RUNNER=ROOT/'external/c4_lag_offline_staging/guard_lag_offline_development.py'
def literals(path):
    tree=ast.parse(path.read_text(encoding='utf-8'));result={}
    for node in tree.body:
        if isinstance(node,ast.Assign):
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            for target in node.targets:
                if isinstance(target,ast.Name):result[target.id]=value
    return result

def main():
    attempt=1
    while (HERE/f'final_preflight_{attempt:03d}.json').exists():attempt+=1
    prefix=HERE/f'final_preflight_{attempt:03d}';source=SOURCE.read_bytes();script=Path(__file__).read_bytes()
    (HERE/f'final_preflight_{attempt:03d}_auditor.py').write_bytes(source)
    (HERE/f'final_preflight_{attempt:03d}_checks.py').write_bytes(script)
    checks=[];wall,cpu=time.perf_counter(),time.process_time()
    left,right=literals(SOURCE),literals(RUNNER)
    for key in ('COST_KEYS','PREDICTORS','HORIZONS','TRIAL_KINDS'):
        checks.append({'name':'exact_runner_schema_'+key,'passed':left[key]==right[key]})
    spec=importlib.util.spec_from_file_location('_final_lag_audit',SOURCE)
    a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
    q,v,pv,u,label=[0.,0.],[1e308,0.],[1e308,0.],[0.,0.],[1e308,0.]
    ranges=[[-2.,2.],[-2.,2.]];state=a.initial_state(ranges);items=[]
    for i in range(400):
        row={'trial_id':'synthetic_failure','seed':0,'kind':'calibration_sparse','step_index':100+i,'shared_transition_id':f'synthetic_failure:{100+i}',
            'observation_after':{'joint_position':q,'joint_velocity':label}}
        items.append({'row':row,'q':q,'v':v,'u':u,'previous_v':pv,'history_transition_ids':[f'synthetic_failure:{98+i}',f'synthetic_failure:{99+i}']})
    delta={'offline_vector_update_attempts':1,'offline_vector_update_failures':1,'rls_model_feature_pair_attempts':2,
        'rls_model_feature_pair_successes':2,'rls_internal_pair_attempts':1,'rls_internal_pair_successes':1,
        'rls_internal_scalar_attempts':2,'rls_internal_scalar_successes':2,'rls_scalar_proposal_attempts':1}
    row=items[0]['row'];saved={'record_type':'lag_calibration_update','trial_id':row['trial_id'],'seed':0,'kind':'calibration_sparse',
        'transition_id':row['shared_transition_id'],'step_index':100,'input':{'q':q,'v':v,'u':u,'previous_v':pv,'next_v_label':label},
        'history_transition_ids':items[0]['history_transition_ids'],'update':None,'failure':{'type':'artificial_nonfinite_RLS'},
        'committed_vector_updates':0,'fingerprint_after':a.digest(a.parameter_record([0.,0.],state,True)),
        'snapshot_at_fixed_count':None,'cost_delta':delta}
    audit=a.Checks();before=Counter(a.MATH_COST)
    replayed,snapshots,cost,completed,failure=a.replay_calibration(items,[saved],[0.,0.],ranges,audit,'artificial_failure')
    checks.append({'name':'failed_RLS_ledger_and_atomic_retention','passed':audit.failed==0 and cost==Counter(delta) and replayed['count']==0 and not completed and failure is not None,
        'audit_checks':audit.count,'audit_failed':audit.failed,'violations':audit.violations})
    checks.append({'name':'new_failure_branch_has_one_scalar_proposal_no_commits','passed':(a.MATH_COST-before)['lag_scalar_rls_proposal_attempts']==1 and (a.MATH_COST-before)['lag_scalar_rls_proposal_successes']==0})
    report={'checks':len(checks),'failed':sum(not x['passed'] for x in checks),'results':checks,
        'source_sha256':hashlib.sha256(source).hexdigest(),'runner_sha256':hashlib.sha256(RUNNER.read_bytes()).hexdigest(),
        'script_sha256':hashlib.sha256(script).hexdigest(),'independent_artificial_math':dict(a.MATH_COST),
        'formal_additions':{'real_raw_reads':0,'physical_calls':0,'online_helper_imports':0,'old_model_refits':0,'real_calibration_updates':0},
        'timing':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu},'artificial_only':True}
    prefix.with_suffix('.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    prefix.with_suffix('.log').write_text(json.dumps(report,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(report,allow_nan=False));return 0 if report['failed']==0 else 1
if __name__=='__main__':raise SystemExit(main())
