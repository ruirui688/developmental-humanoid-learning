"""Fifteen thin T saved-output checks; no model imports or science recomputation."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

parser=argparse.ArgumentParser()
parser.add_argument('--raw',required=True)
parser.add_argument('--expected-source-commit',required=True)
parser.add_argument('--expected-script-sha',required=True)
parser.add_argument('--expected-protocol-sha',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
raw,output=Path(args.raw).resolve(),Path(args.output).resolve()
if raw==output or raw.is_relative_to(output) or output.is_relative_to(raw) or output.exists():
    raise SystemExit('new separate first output required; no repeat')
output.mkdir(parents=True)
wall,cpu=time.perf_counter(),time.process_time()
cost=Counter(); reads={}; checks=[]; failure=None; docs={}

def read(name,path=None):
    cost['file_read_attempts']+=1
    data=(raw/name if path is None else path).read_bytes()
    cost['file_reads']+=1; cost['read_bytes']+=len(data)
    reads[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return data

def parse(data):
    cost['json_parses']+=1
    return json.loads(data,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonstandard JSON:'+value)))

def check(number,description,condition):
    checks.append({'group':number,'description':description,'passed':bool(condition)})
    if not condition:
        raise AssertionError(description)

def finite(value):
    return type(value) in (int,float) and math.isfinite(value)

def matrix(value,rows,cols):
    return isinstance(value,list) and len(value)==rows and all(isinstance(row,list) and len(row)==cols and all(finite(v) for v in row) for row in value)

def flags(value):
    return all(value.get(k) is False for k in ('scientific_adoption','c4_scientific_validation','c5_scientific_dependency_released'))

try:
    checker_source=read('checker_source',Path(__file__).resolve())
    manifest=parse(read('manifest.json'))
    for name in ('run.json','parameters.json','metrics.json'):
        docs[name]=parse(read(name))
    predictions=[parse(line) for line in read('predictions.jsonl').splitlines()]
    for name,identity in manifest['files'].items():
        if name not in reads:
            data=read(name)
            if name.endswith('.json'):
                docs[name]=parse(data)
        if reads[name]!={k:identity[k] for k in ('bytes','sha256')}:
            raise AssertionError('raw manifest identity:'+name)
    expected_files={'run.json','parameters.json','metrics.json','predictions.jsonl'}
    expected_files.update(name for p in docs['parameters.json'] for name in p.get('fit',{}).get('checkpoint_files',{}))
    if docs['run.json'].get('failure') is not None:
        expected_files.add('failure.json')
    check(1,'all raw payload and checkpoint identities',set(manifest['files'])==expected_files
        and (docs.get('failure.json')==docs['run.json'] if 'failure.json' in expected_files else 'failure.json' not in docs))
    run,parameters,metrics=docs['run.json'],docs['parameters.json'],docs['metrics.json']
    source=run['source']; source_files=source['files']
    full=run['status']=='completed' or (run.get('failure') or {}).get('type')=='TFitFailed'
    exact_sources={'scripts/develop_guard_trust_position_transition.py':args.expected_script_sha,
        'docs/GUARD_TRUST_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md':args.expected_protocol_sha}
    check(2,'frozen source commit and exact returned T identities',source['commit']==run['requested_source_commit']==args.expected_source_commit
        and len(args.expected_source_commit)==40 and all(c in '0123456789abcdef' for c in args.expected_source_commit)
        and type(source['clean_committed_bytes_verified']) is bool
        and (not full or source['clean_committed_bytes_verified'] is True)
        and all((name in source_files or not full) and (name not in source_files or source_files[name]['sha256']==sha)
            for name,sha in exact_sources.items()))
    check(3,'run/metrics status and unreleased science flags',run['status']==metrics['status']==manifest['status']
        and run['status'] in ('completed','failed') and run['self_check'] is False
        and (run['failure'] is None if run['status']=='completed' else isinstance(run['failure'],dict))
        and flags(run) and flags(metrics) and manifest['scientific_adoption'] is False)
    runtime=run['runtime']
    runtime_returned=any(name in runtime for name in ('device','dtype','torch_num_threads'))
    check(4,'CPU float64 returned runtime; early unavailable legal',not (full or runtime_returned) or (
        runtime.get('device')=='cpu' and runtime.get('dtype')=='float64'
        and runtime.get('torch_cuda') is None and runtime.get('torch_num_threads')==1))
    old_Q,old_S=run.get('frozen_Q_original_cost',{}),run.get('frozen_S_original_cost',{})
    check(5,'Q and failed S historical effort retained',not full or (old_Q.get('fit_returns')==3
        and old_Q.get('fit_scalar_labels_returned')==26400 and old_S.get('fit_attempts')==3
        and old_S.get('fit_failures')==3 and old_S.get('objective_calculation_attempts')==9))
    paid=run['cost']
    check(6,'no new physical/RLS/MPC or baseline refit',all(paid.get(k,0)==0 for k in
        ('physics_calls','physics_substeps','RLS_updates','MPC_calls','Q22_refits','K22_refits','D11_updates')))
    expected_counts={f'seed{s}_{trial}':n for s in (0,1,2) for trial,n in (('calibration_sparse',400),('prediction',100))}
    check(7,'fixed calibration and prediction populations',not full or run['source_active_counts']==expected_counts)
    check(8,'baseline fingerprints unchanged',not full or all(run[f'{name}_fingerprints_before']==run[f'{name}_fingerprints_after']
        and set(run[f'{name}_fingerprints_before'])=={'0','1','2'} for name in ('Q22','K22','D11')))
    param_by_seed={p['seed']:p for p in parameters}
    check(9,'unique seeds and finite frozen 50 by 22 weights',len(param_by_seed)==len(parameters)
        and (not full or set(param_by_seed)=={0,1,2}) and all(matrix(p['frozen_Q_weights50x22'],50,22)
        and p['optimized_heads']==[0,1] and p['frozen_head_indices']==list(range(2,22)) for p in parameters))
    budget_ok=True; accept_ok=True; candidate_ok=True
    for p in parameters:
        fit=p['fit']; events=fit.get('objective_events',[]); accepted=fit.get('accepted_checkpoints',[])
        if not fit:
            budget_ok &= not full
            accept_ok &= not full
            candidate_ok &= (p['available'] is False and 'selected_weights50x22' not in p)
            continue
        budget_ok &= (fit['objective_calls_started']==len(events)<=100
            and fit['budget']['hard_objective_call_limit']==100 and fit['budget']['time_boundary_seconds']==120.
            and [e['objective_id'] for e in events]==list(range(1,len(events)+1)))
        event_by_id={e['objective_id']:e for e in events}
        registered=[c for c in fit.get('checkpoint_evidence',[]) if c.get('registered_accepted_update') is True]
        accept_ok &= (accepted==registered and fit['accepted_updates']==len(accepted)<=30
            and [c['iteration'] for c in accepted]==list(range(1,len(accepted)+1)))
        origin_id=1
        for c in accepted:
            e=event_by_id[c['objective_id']]
            checkpoint=docs.get(c['file'],{})
            accept_ok &= (c['registered_accepted_update'] is True and c['iteration0_evidence_only'] is False
                and c['post_persistence_elapsed_seconds']<120 and e['exit_elapsed_seconds']<120
                and e['status']=='returned' and e['finite'] is True and e['role']=='trial'
                and e['acceptance']=='accepted_and_registered' and e['origin_objective_id']==origin_id
                and finite(c['loss']) and matrix(c['U50x2'],50,2) and matrix(e['gradient50x2'],50,2)
                and finite(e['gradient_l2_norm']) and finite(e['gradient_inf_norm'])
                and c['U50x2']==e['trial_U50x2'] and c['loss']==e['loss']
                and c['gradient_l2_norm']==e['gradient_l2_norm']
                and reads.get(c['file'])==c['file_identity']==fit['checkpoint_files'].get(c['file'])
                and all(checkpoint.get(k)==c[k] for k in ('iteration','objective_id','U50x2','loss',
                    'gradient_l2_norm','parameter_sha256','iteration0_evidence_only')))
            origin_id=c['objective_id']
        if fit.get('selected_snapshot') is not None:
            accept_ok &= (len(accepted)>=1 and fit['selected_snapshot']==accepted[-1]['U50x2'])
        if fit.get('fit_failed') is True:
            candidate_ok &= (fit.get('selected_snapshot') is None and p['available'] is False)
            evidence=fit.get('accepted_snapshot_retained_as_evidence_only')
            accept_ok &= (evidence==accepted[-1]['U50x2'] if accepted else evidence is None)
        if fit.get('status')=='failed':
            candidate_ok &= fit.get('fit_failed') is True
        if p['available']:
            selected=p['selected_weights50x22']; frozen=p['frozen_Q_weights50x22']
            candidate_ok &= (fit['fit_failed'] is False and fit['optimizer_failed'] is False and not fit.get('failure')
                and fit['status'] in ('returned','budget_exhausted')
                and (fit['budget_exhausted'] is True if fit['status']=='budget_exhausted' else fit['optimizer_converged'] is True)
                and len(accepted)>=1 and matrix(selected,50,22)
                and fit['selected_snapshot']==accepted[-1]['U50x2']
                and [r[:2] for r in selected]==fit['selected_snapshot']
                and [r[2:] for r in selected]==[r[2:] for r in frozen])
        else:
            pending_unpublished=(not full and fit.get('fit_failed') is False
                and fit.get('status') in ('returned','budget_exhausted') and len(accepted)>=1)
            candidate_ok &= ('selected_weights50x22' not in p
                and (fit.get('selected_snapshot') is None or pending_unpublished))
    check(10,'hard objective and per-seed time specification',budget_ok)
    check(11,'registered accepted sequence and deadline bindings',accept_ok)
    check(12,'finite final candidate, frozen other heads, unavailable isolation',candidate_ok)
    keys=Counter((r['seed'],r['predictor'],r['horizon'],r['origin']) for r in predictions)
    expected={(s,m,h,o) for s in (0,1,2) for m in ('T22','Q22','K22','D11') for h in (1,2,5,15) for o in range(101-h)}
    pred_ok=(all(n==1 for n in keys.values()) and (set(keys)==expected if full else set(keys)<=expected))
    for r in predictions:
        if r['predictor']=='T22' and not param_by_seed.get(r['seed'],{}).get('available',False):
            pred_ok &= (r['available'] is False and r.get('scored',False) is False
                and (r.get('reason')=='fit_failed_no_T_candidate' or r.get('reason','').startswith('window_unavailable:')))
        if r['available']:
            if full or r.get('scored') is True:
                pred_ok &= (r.get('scored') is True and all(finite(v) for v in r['terminal_errors_x22'].values()))
            else:
                pred_ok &= r.get('scored') is False
        else:
            pred_ok &= r.get('scored',False) is False
    check(13,'fixed planned prediction population without subset ranking',pred_ok)
    groups=metrics.get('groups',[])
    group_keys=Counter((g['seed'],g['predictor'],g['horizon'],g['channel_index']) for g in groups)
    expected_groups={(s,m,h,ch) for s in (0,1,2) for m in ('T22','Q22','K22','D11')
        for h in (1,2,5,15) for ch in (range(22) if m!='D11' else (0,1,8,9))}
    group_ok=all(n==1 for n in group_keys.values()) and (set(group_keys)==expected_groups if full else set(group_keys)<=expected_groups)
    counts=Counter((r['seed'],r['predictor'],r['horizon']) for r in predictions)
    usable=Counter((r['seed'],r['predictor'],r['horizon']) for r in predictions if r['available'])
    for g in groups:
        key=(g['seed'],g['predictor'],g['horizon'])
        group_ok &= (g['record_count']==counts[key] and g['usable_count']==usable[key]
            and g['unavailable_count']==counts[key]-usable[key] and g['fixed_origin_count']==101-g['horizon']
            and g['partial_subset_method_ranking'] is False)
    check(14,'saved channel counts match availability; no metrics recalculation',group_ok)
    gate=metrics.get('development_gate'); gate_ok=not full if gate is None else (
        flags(gate) and gate['Q22_descriptive_only'] is True and set(gate['comparisons'])=={'T22_vs_K22','T22_vs_D11'}
        and all(flags(v) and v['candidate_predictor']=='T22' and v['baseline_predictor']==b for b,v in
            (('K22',gate['comparisons']['T22_vs_K22']),('D11',gate['comparisons']['T22_vs_D11'])))
        and metrics['development_gate_passed']==run['development_gate_passed']==gate['passed'])
    check(15,'saved dual gate values and science flags; no gate recalculation',gate_ok)
except Exception as exc:
    failure={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
cost.update(wall_seconds=time.perf_counter()-wall,cpu_seconds=time.process_time()-cpu,
    model_restorations=0,scientific_metric_recalculations=0,scientific_gate_recalculations=0)
report={'checks':checks,'status':'completed' if failure is None else 'failed','failure':failure,
    'inputs':reads,'cost':dict(cost),'expected_source_commit':args.expected_source_commit,
    'evidence_consistency_only':True,'scientific_adoption':False}
(output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
if 'checker_source' in locals():
    (output/'checker.py').write_bytes(checker_source)
print(json.dumps({'status':report['status'],'checks':len(checks),'cost':dict(cost),
    'failure':None if failure is None else {'type':failure['type'],'message':failure['message']}}))
raise SystemExit(bool(failure))
