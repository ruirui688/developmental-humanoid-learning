"""Transcribe saved S results once; do not recompute science."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
root = repo / 'results/cpu_validation/2026-10-12_guard_multistep_position_transition'
output = repo / 'external/c4_s_reporting_reads.json'
if output.exists():
    raise SystemExit('first read record exists; no repeat')
wall, cpu = time.perf_counter(), time.process_time()
docs, reads = {}, []
for name in ('raw/run.json', 'raw/metrics.json', 'raw/parameters.json', 'manifest.json', 'execution.json'):
    raw = (root/name).read_bytes()
    docs[name] = json.loads(raw)
    reads.append({'path': name, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()})
record = {'reads': reads, 'file_reads':len(reads), 'read_bytes':sum(x['bytes'] for x in reads),
          'json_parses':len(reads), 'wall_seconds':time.perf_counter()-wall,
          'cpu_seconds':time.process_time()-cpu, 'scientific_recalculation':False}
output.write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
run, metrics = docs['raw/run.json'], docs['raw/metrics.json']
fits = []
for param in docs['raw/parameters.json']:
    fit = param.get('fit', {})
    fits.append({'seed':param['seed'], 'available':param.get('available'),
      'fit':{k:v for k,v in fit.items() if k not in ('initial_UQ50x2','objective_events','accepted_checkpoints','selected_snapshot','accepted_snapshot_retained_as_evidence_only')},
      'events':[{k:v for k,v in e.items() if k not in ('trial_U50x2','gradient50x2','partial_transfer')} for e in fit.get('objective_events',[])],
      'accepted':[{k:v for k,v in e.items() if k not in ('U50x2','paid_cost_at_acceptance')} for e in fit.get('accepted_checkpoints',[])]})
summary = {'run':run,'gate':metrics.get('development_gate'),'fits':fits,
           'archive':{k:v for k,v in docs['manifest.json'].items() if k!='files'},
           'execution':docs['execution.json'],'report_reads':record}
(repo/'external/c4_s_reporting_summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
print(json.dumps(summary))
