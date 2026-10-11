"""One frozen C invocation; never overwrite or retry an existing first run."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-commit',required=True)
args=parser.parse_args()
output=root/'external/guard_exploration_20261011_first'
stdout=Path(str(output)+'_stdout.txt')
execution=Path(str(output)+'_execution.json')
assert all(not p.exists() for p in (output,stdout,execution))
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert commit==args.expected_commit
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True)==''
env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
command=[str(root/'external/cpu_physics_env/Scripts/python.exe'),'-m',
 'developmental_physics.guard_exploration_development','--output',str(output),
 '--protocol','docs/GUARD_EXPLORATION_DEVELOPMENT_PROTOCOL.md']
started=time.perf_counter();code=None;error=None
try:
 with stdout.open('xb') as stream:
  code=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
except BaseException as exc:
 error={'type':type(exc).__name__,'message':str(exc)}
 raise
finally:
 with execution.open('x',encoding='utf-8') as stream:
  json.dump({'source_commit':commit,'command':command,'exit_code':code,'wrapper_exception':error,
   'wrapper_wall_seconds':time.perf_counter()-started,'repeated':False,
   'failed_exit_does_not_imply_zero_paid_cost':True},stream,indent=2);stream.write('\n')
print(execution.read_text(encoding='utf-8'))
raise SystemExit(code)
