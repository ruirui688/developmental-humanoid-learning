"""First FR3 stage execution with complete first stdout/stderr; no retry."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=('prediction','control'), required=True)
parser.add_argument('--source-commit', required=True)
args = parser.parse_args()
assert len(args.source_commit) == 40 and all(x in '0123456789abcdef' for x in args.source_commit)
capture = root/('external/fr3_'+args.stage+'_first')
assert not capture.exists(), 'first stage capture exists; do not rerun'
capture.mkdir()
command = [str(root/'external/cpu_physics_env/Scripts/python.exe'), '-u',
    'scripts/develop_full_request_pair.py', '--stage', args.stage, '--repo', str(root),
    '--output', str(capture/'raw'), '--source-commit', args.source_commit]
start_wall, start_cpu = time.perf_counter(), time.process_time()
with (capture/'stdout.log').open('xb') as stdout, (capture/'stderr.log').open('xb') as stderr:
    process = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False)
pins = {}
for name in ('stdout.log','stderr.log'):
    data = (capture/name).read_bytes()
    pins[name] = {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
receipt = {'first_attempt':True,'automatic_retry':False,'command':command,
    'source_commit':args.source_commit,'exit_code':process.returncode,
    'wall_seconds':time.perf_counter()-start_wall,
    'launcher_cpu_seconds_excludes_child':time.process_time()-start_cpu,'files':pins}
(capture/'first_execution_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
raise SystemExit(process.returncode)
