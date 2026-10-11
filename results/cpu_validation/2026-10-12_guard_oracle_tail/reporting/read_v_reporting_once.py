"""Read V saved report inputs once, without model or metric recomputation."""
import hashlib
import json
from pathlib import Path
import time
repo=Path(__file__).resolve().parents[1]
root=repo/'results/cpu_validation/2026-10-12_guard_oracle_tail'
receipt=repo/'external/c4_v_reporting_reads.json'
if receipt.exists():
    raise SystemExit('first V report read exists; no repeat')
wall,cpu=time.perf_counter(),time.process_time(); docs={}; reads=[]
for name in ('raw/run.json','raw/metrics.json','raw/parameters.json','manifest.json','execution.json'):
    data=(root/name).read_bytes(); docs[name]=json.loads(data)
    reads.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
record={'reads':reads,'file_reads':5,'read_bytes':sum(r['bytes'] for r in reads),'json_parses':5,
        'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
        'scientific_recalculation':False}
with receipt.open('x',encoding='utf-8') as stream:
    json.dump(record,stream,indent=2); stream.write('\n')
summary={'run':docs['raw/run.json'],'metrics':docs['raw/metrics.json'],
         'parameters':docs['raw/parameters.json'],
         'archive':{k:v for k,v in docs['manifest.json'].items() if k!='files'},
         'execution':docs['execution.json'],'report_reads':record}
with (repo/'external/c4_v_reporting_summary.json').open('x',encoding='utf-8') as stream:
    json.dump(summary,stream,indent=2); stream.write('\n')
run=summary['run']
print(json.dumps({'status':run.get('status'),'failure':run.get('failure'),
                 'rule':summary['metrics'].get('diagnostic_rule'),
                 'cost':{k:v for k,v in run.get('cost',{}).items() if
                         any(part in k for part in ('wall_seconds','cpu_seconds','oracle','fit_','physics','RLS'))},
                 'report_reads':record}))
