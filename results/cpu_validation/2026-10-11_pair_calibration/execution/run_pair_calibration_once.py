"""Capture exactly one frozen six-trial call; do not retry any return code."""
import json
import os
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
prefix=root/'external/pair_calibration_20261011_first'
stdout=Path(str(prefix)+'_stdout.txt')
execution=Path(str(prefix)+'_execution.json')
assert not prefix.exists() and not stdout.exists() and not execution.exists()
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True)==''
environment=os.environ.copy();environment['PYTHONPATH']=str(root/'src')
command=[str(root/'external/cpu_physics_env/Scripts/python.exe'),'-m',
         'developmental_physics.pair_calibration_development','--output',str(prefix),
         '--protocol','docs/PAIR_CALIBRATION_DEVELOPMENT_PROTOCOL.md']
wall=time.perf_counter()
with stdout.open('xb') as stream:
    result=subprocess.run(command,cwd=root,env=environment,stdout=stream,stderr=subprocess.STDOUT)
execution.write_text(json.dumps({'source_commit':commit,'command':command,'exit_code':result.returncode,
    'wrapper_wall_seconds':time.perf_counter()-wall,'repeated':False,
    'failed_exit_does_not_imply_zero_physical_cost':True},indent=2)+'\n',encoding='utf-8')
print(execution.read_text())
