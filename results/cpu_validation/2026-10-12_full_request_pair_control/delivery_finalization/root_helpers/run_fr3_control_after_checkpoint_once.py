"""First physical B attempt after preserving a zero-physics source rejection."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--source-commit',required=True)
args=parser.parse_args()
assert len(args.source_commit)==40 and all(x in '0123456789abcdef' for x in args.source_commit)
previous=json.loads((root/'external/fr3_control_first/raw/run.json').read_bytes())
assert previous['failure']['phase']=='source_validation'
assert previous['cost']['control_call_attempts']==previous['cost']['confirmed_physics_substeps']==0
assert (root/'results/cpu_validation/2026-10-12_full_request_pair_prediction/control_source_failure/preservation_manifest.json').is_file()
capture=root/'external/fr3_control_physical_first'
assert not capture.exists(),'first physical capture exists; do not rerun'
capture.mkdir()
command=[str(root/'external/cpu_physics_env/Scripts/python.exe'),'-u','scripts/develop_full_request_pair.py',
 '--stage','control','--repo',str(root),'--output',str(capture/'raw'),'--source-commit',args.source_commit]
start=time.perf_counter()
with (capture/'stdout.log').open('xb') as stdout,(capture/'stderr.log').open('xb') as stderr:
 process=subprocess.run(command,cwd=root,stdout=stdout,stderr=stderr,check=False)
pins={}
for name in ('stdout.log','stderr.log'):
 data=(capture/name).read_bytes();pins[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
receipt={'first_physical_attempt':True,'first_invocation':False,'previous_invocation_source_failure_preserved':True,
 'previous_physical_interactions':0,'automatic_retry':False,'command':command,'source_commit':args.source_commit,
 'exit_code':process.returncode,'wall_seconds':time.perf_counter()-start,'files':pins}
(capture/'first_execution_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
raise SystemExit(process.returncode)
