"""Eight thin V saved-output checks, with no model or metric recomputation."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

parser=argparse.ArgumentParser()
parser.add_argument('--raw',type=Path,required=True)
parser.add_argument('--expected-source-commit',required=True)
parser.add_argument('--expected-script-sha',required=True)
parser.add_argument('--expected-protocol-sha',required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if args.output.exists():
    raise SystemExit('first V contract output exists; no repeat')
args.output.mkdir(parents=True)
wall,cpu=time.perf_counter(),time.process_time()
cost=Counter(); checks=[]; reads={}; failure=None
def read(name):
    path=args.raw/name
    cost['file_read_attempts']+=1
    data=path.read_bytes(); cost['file_reads']+=1; cost['read_bytes']+=len(data)
    reads[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return data
def parse(name):
    value=json.loads(read(name)); cost['json_parses']+=1
    return value
def check(number,label,condition):
    checks.append({'group':number,'description':label,'passed':bool(condition)})
def finite(value):
    return type(value) in (int,float) and math.isfinite(value)
def vector(value,n):
    return isinstance(value,list) and len(value)==n and all(finite(x) for x in value)
def flags(value):
    return all(value.get(k) is False for k in ('scientific_adoption','c4_scientific_validation','c5_scientific_dependency_released'))
predictors=('Q22_saved_self','U22_saved_self','Q22_oracle18','U22_oracle18')
controlled=(0,1,8,9)
oracle=tuple(i for i in range(22) if i not in controlled)
try:
    run=parse('run.json'); metrics=parse('metrics.json'); parameters=parse('parameters.json')
    manifest=parse('manifest.json')
    source=run.get('source') or {}; full=run.get('status')=='completed'
    expected_sources={'scripts/diagnose_guard_oracle_tail.py':args.expected_script_sha,
                      'docs/GUARD_ORACLE_TAIL_DIAGNOSTIC_PROTOCOL.md':args.expected_protocol_sha}
    source_ok=(source.get('commit')==args.expected_source_commit
               and source.get('clean_committed_bytes_verified') is True
               and all(source.get('files',{}).get(k,{}).get('sha256')==v for k,v in expected_sources.items()))
    check(1,'frozen source identities or explicitly failed early source',source_ok or
          (not full and run.get('failure') is not None and not source.get('clean_committed_bytes_verified')))
    c=run.get('cost',{})
    zero_keys=('physics_calls','physics_substeps','RLS_updates','MPC_calls','fit_attempts',
               'objective_calculation_attempts','gradient_calculation_attempts','saved_self_forward_calls',
               'saved_self_error_recalculations','saved_self_metric_recalculations',
               'K22_restorations','D11_restorations')
    check(2,'no learning/physics/old self recomputation and scientific flags false',
          flags(run) and flags(metrics) and all(c.get(k)==0 for k in zero_keys))
    frozen_ok=(isinstance(parameters,list) and len(parameters)<=3 and
               len({p['seed'] for p in parameters})==len(parameters) and
               all(p['seed'] in (0,1,2) and p.get('refit') is False and p.get('actual_updates')==0 for p in parameters)
               and (not full or {p['seed'] for p in parameters}=={0,1,2}))
    for p in parameters:
        for m in ('Q22','U22'):
            before,after=p.get(m+'_fingerprint_before'),p.get(m+'_fingerprint_after')
            if before is not None:
                frozen_ok &= (isinstance(before,str) and len(before)==64 and all(x in '0123456789abcdef' for x in before)
                              and (after==before or (not full and after is None and run.get('failure') is not None)))
            else:
                frozen_ok &= after is None and (p.get('available') is False or not full)
        if full and p.get('available') is True:
            frozen_ok &= all(p.get(m+'_fingerprint_before') is not None for m in ('Q22','U22'))
    if not full:
        frozen_ok &= run.get('failure') is not None
    check(3,'only frozen Q/U identities restored',frozen_ok)
    compressed=read('predictions.jsonl.gz'); lines=gzip.decompress(compressed).splitlines()
    cost['decompressed_bytes']=sum(len(x)+1 for x in lines)
    records=[json.loads(line) for line in lines]; cost['json_parses']+=len(records)
    expected={(s,m,h,o) for s in (0,1,2) for m in predictors for h in (1,2,5,15) for o in range(101-h)}
    by_id={(r['seed'],r['predictor'],r['horizon'],r['origin']):r for r in records}
    payload_bindings=all(manifest.get('files',{}).get(k)==v for k,v in reads.items() if k!='manifest.json')
    check(4,'saved payload bindings and fixed identities with no duplicate or dropped completed-run rows',
          payload_bindings and flags(manifest) and manifest.get('status')==run.get('status') and
          len(by_id)==len(records) and set(by_id)<=expected and (not full or set(by_id)==expected))
    availability_ok=True; path_ok=True; h1_ok=True
    for key,r in by_id.items():
        if r.get('available'):
            availability_ok &= (r.get('scored') is True and vector(r.get('controlled_terminal4'),4)
                                and vector(r.get('actual_controlled4'),4))
            errors=r.get('terminal_errors_x22')
            availability_ok &= (isinstance(errors,dict) and set(errors)=={str(i) for i in controlled}
                                and all(finite(v) for v in errors.values()))
        else:
            availability_ok &= r.get('scored') is False
        if key[1].endswith('_saved_self'):
            availability_ok &= not r.get('available') or r.get('transcribed_without_forward_or_error_recalculation') is True
            continue
        path=r.get('predicted_preoverwrite_path_x22',[])
        history=r.get('history_inputs',[])
        replacements=r.get('oracle_replacements',[])
        path_ok &= (isinstance(path,list) and isinstance(history,list) and isinstance(replacements,list)
                    and len(path)<=key[2] and len(history)<=key[2]
                    and len(path)<=len(history)<=len(path)+1 and len(replacements)<=min(len(path),key[2]-1)
                    and all(vector(x,22) for x in path))
        for i,event in enumerate(history):
            before=event.get('current_x22_before'); previous=event.get('previous_v2_before')
            path_ok &= (isinstance(event,dict) and event.get('step_index')==i
                        and vector(before,22) and vector(previous,2)
                        and event.get('request_transition_id')==r.get('requested_transition_ids',[])[i])
            if i==0:
                path_ok &= before==r.get('initial_x22') and previous==r.get('previous_v2')
            else:
                prior=history[i-1].get('current_x22_before',[])
                path_ok &= previous==prior[8:10]
                path_ok &= i-1<len(replacements) and before==replacements[i-1].get('hybrid_x22_after')
            if i<len(path):
                original=event.get('frozen_full22_step') or {}
                path_ok &= (original.get('available') is True and original.get('terminal_x22')==path[i]
                            and event.get('previous_v2_after')==before[8:10]
                            and original.get('terminal_previous_v2')==before[8:10])
        if r.get('available'):
            path_ok &= (len(path)==key[2] and len(history)==key[2] and len(replacements)==key[2]-1
                        and r.get('terminal_x22')==path[-1] and vector(r.get('terminal_previous_v2'),2)
                        and r.get('terminal_previous_v2')==history[-1].get('current_x22_before',[])[8:10]
                        and r.get('controlled_terminal4')==[path[-1][j] for j in controlled]
                        and r.get('terminal18_overwritten') is False and r.get('terminal18_scored') is False)
        for i,replacement in enumerate(replacements):
            pre=path[i] if i<len(path) else None
            hybrid=replacement.get('hybrid_x22_after')
            label=replacement.get('oracle_native18')
            path_ok &= (i<key[2]-1 and vector(pre,22) and vector(hybrid,22) and vector(label,18)
                        and tuple(replacement.get('oracle_indices',[]))==oracle
                        and replacement.get('endpoint_transition_id')==r.get('requested_transition_ids',[])[i]
                        and replacement.get('source_predictor')=='U22' and replacement.get('source_horizon')==1
                        and replacement.get('seed')==key[0] and replacement.get('trial_id')==r.get('trial_id')
                        and replacement.get('origin')==key[3]+i and replacement.get('step_index')==i)
            if vector(pre,22) and vector(hybrid,22) and vector(label,18):
                path_ok &= (all(hybrid[j]==pre[j] for j in controlled)
                            and [hybrid[j] for j in oracle]==label)
        if key[2]==1 and r.get('available'):
            saved=by_id.get((key[0],key[1].replace('_oracle18','_saved_self'),1,key[3]),{})
            h1_ok &= (saved.get('available') is True and r['controlled_terminal4']==saved['controlled_terminal4']
                      and r['terminal_errors_x22']==saved['terminal_errors_x22'])
    check(5,'controlled-only scoring, fixed unavailable rows and transcribed self',availability_ok)
    check(6,'finite full22 before nonterminal tail replacement and predicted history',path_ok)
    h1=run.get('H1_identity') or {}
    h1_available=sum(r.get('available') is True for key,r in by_id.items() if key[2]==1 and key[1].endswith('_oracle18'))
    h1_unavailable=sum(r.get('available') is not True for key,r in by_id.items() if key[2]==1 and key[1].endswith('_oracle18'))
    check(7,'H1 controlled identity and complete identity ledger',h1_ok and
          (not full or (h1.get('requested_pair_records')==600
                        and h1.get('compared_pair_records')==h1_available
                        and h1.get('unavailable_pair_records')==h1_unavailable
                        and h1_available+h1_unavailable==600
                        and h1.get('exact_pair_records')==h1_available
                        and h1.get('all_requested_exact')==(h1_available==600))))
    groups=metrics.get('groups',[])
    group_ids={(g['seed'],g['predictor'],g['horizon'],g['channel_index']) for g in groups}
    expected_groups={(s,m,h,channel) for s in (0,1,2) for m in predictors for h in (1,2,5,15)
                     for channel in controlled}
    rule=metrics.get('diagnostic_rule') or {}
    check(8,'all controlled groups and descriptive-only fixed source rule',
          len(group_ids)==len(groups) and group_ids<=expected_groups
          and (not full or (group_ids==expected_groups and set(rule.get('by_source',{}))=={'Q22','U22'}
                           and flags(rule) and all(flags(v) for v in rule['by_source'].values())
                           and rule.get('all_192_fixed_groups_full')==all(g.get('full_fixed_count') is True for g in groups))))
except Exception as exc:
    failure={'type':type(exc).__name__,'message':str(exc)}
own=Path(__file__).read_bytes(); cost['file_reads']+=1; cost['read_bytes']+=len(own)
(args.output/'checker.py').write_bytes(own)
cost.update(model_restorations=0,scientific_metric_recalculations=0,scientific_gate_recalculations=0)
cost['wall_seconds']=time.perf_counter()-wall; cost['cpu_seconds']=time.process_time()-cpu
report={'checks':checks,'status':'completed' if failure is None else 'failed','failure':failure,
        'failed_checks':sum(not x['passed'] for x in checks),'reads':reads,'cost':dict(cost)}
(args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('checks','reads')}))
raise SystemExit(bool(failure or report['failed_checks'] or len(checks)!=8))
