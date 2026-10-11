"""Validate W0 local navigation once per phase; no scientific computation."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote
parser=argparse.ArgumentParser()
parser.add_argument('--results',action='store_true')
args=parser.parse_args()
repo=Path(__file__).resolve().parents[1]
paths=['docs/CONTINUOUS_EXECUTION_PLAN.md','docs/SUPPORTED_PAIR_DOMAIN_DESIGN.md']
if args.results:
    paths+=['README.md','AGENTS.md','docs/PROGRESS.md','docs/SUPPORTED_PAIR_ENGINEERING_RESULTS.md']
checks=[]
reads=byte_count=0
for name in paths:
    source=repo/name
    data=source.read_bytes(); reads+=1; byte_count+=len(data)
    for match in re.finditer(r'!?\[[^\]]*\]\(([^\)]+)\)',data.decode('utf-8')):
        target=match.group(1).strip().split(' "')[0].strip('<>')
        if target.startswith(('https:','http:','#','app:','codex:')):
            continue
        target=unquote(target.split('#',1)[0])
        checks.append({'source':name,'target':target,'exists':(source.parent/target).exists()})
record={'checks':len(checks),'failed':sum(not x['exists'] for x in checks),
        'missing':[x for x in checks if not x['exists']],'file_reads':reads,'read_bytes':byte_count,
        'scientific_recalculation':False}
label='results' if args.results else 'preparation'
with (repo/f'external/c4_w0_{label}_links_01.json').open('x',encoding='utf-8') as stream:
    json.dump(record,stream,indent=2); stream.write('\n')
print(json.dumps(record))
raise SystemExit(bool(record['failed']))
