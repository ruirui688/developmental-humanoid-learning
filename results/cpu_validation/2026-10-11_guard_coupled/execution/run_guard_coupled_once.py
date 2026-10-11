"""Capture the first frozen B trial matrix once, retaining every failure."""
import json
import os
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
output = root/'external/guard_coupled_20261011_first'
stdout = Path(str(output)+'_stdout.txt')
execution = Path(str(output)+'_execution.json')
assert not output.exists() and not stdout.exists() and not execution.exists()
commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert commit == 'f68c485e383b071ebe534465d3c17f65e5600a62'
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True) == ''
environment = os.environ.copy()
environment['PYTHONPATH'] = str(root/'src')
command = [str(root/'external/cpu_physics_env/Scripts/python.exe'),'-m',
 'developmental_physics.guard_coupled_development','--output',str(output),
 '--protocol','docs/GUARD_COUPLED_DEVELOPMENT_PROTOCOL.md']
started = time.perf_counter()
with stdout.open('xb') as stream:
    result = subprocess.run(command,cwd=root,env=environment,stdout=stream,stderr=subprocess.STDOUT)
with execution.open('x',encoding='utf-8') as stream:
    json.dump({'source_commit':commit,'command':command,'exit_code':result.returncode,
        'wrapper_wall_seconds':time.perf_counter()-started,'repeated':False,
        'failed_exit_does_not_imply_zero_paid_cost':True},stream,indent=2);stream.write('\n')
print(execution.read_text(encoding='utf-8'))
raise SystemExit(result.returncode)
