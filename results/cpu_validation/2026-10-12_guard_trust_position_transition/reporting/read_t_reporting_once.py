"""Read first saved T result once and transcribe a compact report input."""
import hashlib
import json
from pathlib import Path
import time

repo=Path(__file__).resolve().parents[1]
root=repo/'results/cpu_validation/2026-10-12_guard_trust_position_transition'
receipt=repo/'external/c4_t_reporting_reads.json'
if receipt.exists():
    raise SystemExit('first report read exists; no repeat')
wall,cpu=time.perf_counter(),time.process_time(); docs={}; reads=[]
for name in ('raw/run.json','raw/metrics.json','raw/parameters.json','manifest.json','execution.json'):
    data=(root/name).read_bytes(); docs[name]=json.loads(data)
    reads.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
record={'reads':reads,'file_reads':len(reads),'read_bytes':sum(r['bytes'] for r in reads),
    'json_parses':len(reads),'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
    'scientific_recalculation':False}
receipt.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
fits=[]
event_keys=('objective_id','role','status','loss','gradient_l2_norm','gradient_inf_norm','entry_elapsed_seconds',
    'exit_elapsed_seconds','iteration','trial_index','alpha','source_objective_id','Armijo_bound','acceptance',
    'rejection_reason','failure','outside_time_boundary','horizon_mean_square_losses')
checkpoint_keys=('iteration','objective_id','entry_elapsed_seconds','post_persistence_elapsed_seconds',
    'loss','gradient_l2_norm','registered_accepted_update','outside_time_boundary')
for p in docs['raw/parameters.json']:
    f=p.get('fit',{}); events=f.get('objective_events',[])
    fits.append({'seed':p['seed'],'available':p.get('available'),
        'fit':{k:v for k,v in f.items() if k not in ('initial_UQ50x2','objective_events','accepted_checkpoints',
            'checkpoint_evidence','checkpoint_files','selected_snapshot','accepted_snapshot_retained_as_evidence_only','initial_checkpoint')},
        'events':[{k:e[k] for k in event_keys if k in e} for e in events],
        'accepted':[{k:c[k] for k in checkpoint_keys if k in c} for c in f.get('accepted_checkpoints',[])]})
run,metrics=docs['raw/run.json'],docs['raw/metrics.json']
summary={'run':run,'gate':metrics.get('development_gate'),'groups':metrics.get('groups',[]),'fits':fits,
    'archive':{k:v for k,v in docs['manifest.json'].items() if k!='files'},
    'execution':docs['execution.json'],'report_reads':record}
(repo/'external/c4_t_reporting_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
compact_fits=[]
for f in fits:
    events=f['events']; accepted=f['accepted']
    compact_fits.append({'seed':f['seed'],'available':f['available'],'fit':f['fit'],
        'initial_event':events[:1],'last_accepted':accepted[-1:],'last_event':events[-1:]})
gate=summary['gate']
print(json.dumps({'status':run['status'],'cost':run['cost'],'failure':run.get('failure'),
    'gate':None if gate is None else {k:v for k,v in gate.items() if k!='comparisons'},
    'gate_checks':None if gate is None else {name:[{k:v for k,v in c.items() if k!='seed_records'} for c in g['checks']]
        for name,g in gate['comparisons'].items()},'fits':compact_fits,'report_reads':record}))
