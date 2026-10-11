"""Keep the first U synthetic or frozen data invocation; never retry."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

parser=argparse.ArgumentParser()
parser.add_argument('--self-check',action='store_true')
args=parser.parse_args()
repo=Path(__file__).resolve().parents[1]
label='c4_u_selfcheck_01' if args.self_check else 'c4_u_bounded_position_01'
output=repo/'external'/label
if output.exists():
    raise SystemExit('first U output exists; preserve it, no repeat')
output.mkdir()
sources={}
if args.self_check:
    for name in ('scripts/develop_guard_bounded_lbfgs_position_transition.py','docs/GUARD_BOUNDED_LBFGS_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md'):
        raw=(repo/name).read_bytes()
        dest=output/'checked_source'/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(raw)
        sources[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
argv=['D:/Python3.10/python.exe','scripts/develop_guard_bounded_lbfgs_position_transition.py','--repo',str(repo),'--output',str(output/'raw')]
if args.self_check:
    commit=None
    argv.append('--self-check')
else:
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=repo,capture_output=True,text=True,check=True).stdout.strip()
    argv+=['--source-commit',commit]
started=time.time(); wall=time.perf_counter()
proc=subprocess.run(argv,cwd=repo,capture_output=True,check=False)
elapsed=time.perf_counter()-wall
(output/'stdout').write_bytes(proc.stdout)
(output/'stderr').write_bytes(proc.stderr)
record={'argv':argv,'source_commit':commit,'returncode':proc.returncode,
  'started_unix':started,'ended_unix':time.time(),'wall_seconds':elapsed,
  'checked_sources':sources,'source_snapshot_reads':len(sources),
  'source_snapshot_read_bytes':sum(x['bytes'] for x in sources.values()),
  'stdout_bytes':len(proc.stdout),'stderr_bytes':len(proc.stderr),
  'subprocess_invocations':1,'automatic_retry':False}
(output/'execution.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
if args.self_check:
    print(proc.stdout.decode('utf-8',errors='replace'))
    print(proc.stderr.decode('utf-8',errors='replace'))
raise SystemExit(proc.returncode)
