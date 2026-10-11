"""Capture one frozen raw/guard learning matrix, including all failed trials."""
import json
import os
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
output = root/'external/guard_pair_20261011_first'
stdout = Path(str(output)+'_stdout.txt')
execution = Path(str(output)+'_execution.json')
assert not output.exists() and not stdout.exists() and not execution.exists()
commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],
                               cwd=root, text=True) == ''
environment = os.environ.copy()
environment['PYTHONPATH'] = str(root/'src')
command = [str(root/'external/cpu_physics_env/Scripts/python.exe'), '-m',
           'developmental_physics.guard_pair_development', '--output', str(output),
           '--protocol', 'docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md']
started = time.perf_counter()
with stdout.open('xb') as stream:
    result = subprocess.run(command, cwd=root, env=environment, stdout=stream,
                            stderr=subprocess.STDOUT)
with execution.open('x', encoding='utf-8') as stream:
    stream.write(json.dumps({'source_commit':commit,'command':command,
        'exit_code':result.returncode,'wrapper_wall_seconds':time.perf_counter()-started,
        'repeated':False,'failed_exit_does_not_imply_zero_physical_cost':True}, indent=2)+'\n')
print(execution.read_text(encoding='utf-8'))
