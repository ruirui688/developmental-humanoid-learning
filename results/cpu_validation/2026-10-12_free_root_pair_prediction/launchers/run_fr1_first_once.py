"""Capture one frozen FR1 process; no retry. Stdlib only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[1]
out = repo / 'external/fr1_first_execution'
out.mkdir(exist_ok=False)
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=repo).strip()
python = repo / 'external/cpu_physics_env/Scripts/python.exe'
command = [str(python), '-u', 'scripts/develop_free_root_pair.py', '--stage', 'prediction',
           '--repo', str(repo), '--output', str(out/'raw'), '--source-commit', commit]
env = dict(os.environ, PYTHONPATH=str(repo/'src'))
start_wall, start_cpu = time.perf_counter(), time.process_time()
with (out/'stdout.log').open('xb') as stdout, (out/'stderr.log').open('xb') as stderr:
    process = subprocess.Popen(command, cwd=repo, env=env, stdout=stdout, stderr=stderr)
    print(json.dumps({'first_FR1_started': True, 'source_commit': commit, 'pid': process.pid}), flush=True)
    returned = process.wait()
receipt = {'first_attempt': True, 'automatic_retry': False, 'command': command,
           'source_commit': commit, 'exit_code': returned,
           'wall_seconds': time.perf_counter()-start_wall,
           'launcher_cpu_seconds_excludes_child': time.process_time()-start_cpu,
           'files': {}}
for name in ('stdout.log', 'stderr.log'):
    data = (out/name).read_bytes()
    receipt['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
with (out/'first_execution_receipt.json').open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps(receipt, ensure_ascii=False), flush=True)
raise SystemExit(returned)
