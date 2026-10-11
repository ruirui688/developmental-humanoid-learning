"""Read first W0 saved reporting inputs, preserving exact identities."""
import hashlib
import json
from pathlib import Path
import time
repo=Path(__file__).resolve().parents[1]
root=repo/'results/cpu_validation/2026-10-12_supported_pair_engineering'
receipt=repo/'external/c4_w0_reporting_reads.json'
if receipt.exists():
    raise SystemExit('first W0 report receipt exists; no repeat')
wall,cpu=time.perf_counter(),time.process_time()
docs={}; reads=[]
for name in ('raw/run.json','raw/metrics.json','raw/manifest.json','manifest.json','execution.json'):
    data=(root/name).read_bytes(); docs[name]=json.loads(data)
    reads.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
record={'reads':reads,'file_reads':5,'read_bytes':sum(x['bytes'] for x in reads),'json_parses':5,
        'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
        'scientific_recalculation':False}
with receipt.open('x',encoding='utf-8') as stream:
    json.dump(record,stream,indent=2); stream.write('\n')
summary={'run':docs['raw/run.json'],'metrics':docs['raw/metrics.json'],
         'archive':{k:v for k,v in docs['manifest.json'].items() if k!='files'},
         'raw_manifest':docs['raw/manifest.json'],'execution':docs['execution.json'],'report_reads':record}
with (repo/'external/c4_w0_reporting_summary.json').open('x',encoding='utf-8') as stream:
    json.dump(summary,stream,indent=2); stream.write('\n')
print(json.dumps({'status':summary['run'].get('status'),
                  'qualification':{k:v for k,v in summary['metrics'].items() if k!='qualifying_contact_events'},
                  'qualifying_contact_events':len(summary['metrics'].get('qualifying_contact_events',[])),
                  'cost':summary['run'].get('cost'),'effort':summary['run'].get('actual_effort'),
                  'stop':summary['run'].get('stop'),'failure':summary['run'].get('failure'),
                  'report_reads':record}))
