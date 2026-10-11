"""One bounded offline D execution from an explicit clean source commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-commit',required=True)
args=parser.parse_args()
base=root/'external/guard_lag_offline_20261011_first'
freeze=Path(str(base)+'_runtime_source_freeze.json')
context=Path(str(base)+'_context.json')
stdout=Path(str(base)+'_stdout.txt')
execution=Path(str(base)+'_execution.json')
assert all(not p.exists() for p in (base,freeze,context,stdout,execution))
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert commit==args.expected_commit
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True)==''
paths=(
 'src/developmental_physics/guard_lag_offline_development.py',
 'src/developmental_physics/guard_lag_pair_model.py',
 'src/developmental_physics/guard_coupled_pair_model.py',
 'src/developmental_physics/guard_pair_model.py',
 'src/developmental_physics/local_pair_model.py',
 'src/developmental_physics/local_model.py',
 'src/developmental_physics/__init__.py',
 'scripts/audit_guard_lag_offline.py',
 'scripts/audit_guard_coupled_development.py',
 'scripts/audit_guard_pair_development.py',
 'scripts/audit_pair_frozen.py',
 'scripts/audit_local_frozen.py',
 'docs/GUARD_LAG_OFFLINE_DEVELOPMENT_PROTOCOL.md',
 'pyproject.toml',
)
hashes={}
for name in paths:
 data=(root/name).read_bytes()
 assert data==subprocess.check_output(['git','show',f'{commit}:{name}'],cwd=root),name
 hashes[name]=hashlib.sha256(data).hexdigest()
for path,record in (
 (freeze,{'source_commit':commit,'source_sha256':hashes}),
 (context,{'verified_source_commit':commit,'verified_clean_worktree':True,
           'verified_source_git_blob_count':len(paths),'source_verification':'wrapper compares original working bytes to explicit clean HEAD'}),
):
 with path.open('x',encoding='utf-8') as stream:
  json.dump(record,stream,indent=2);stream.write('\n')

command=['D:/Python3.10/python.exe','-m','developmental_physics.guard_lag_offline_development',
 '--output',str(base),'--source-root',str(root/'results/cpu_validation/2026-10-11_guard_exploration'),
 '--protocol','docs/GUARD_LAG_OFFLINE_DEVELOPMENT_PROTOCOL.md','--source-freeze',str(freeze),
 '--execution-context',str(context)]
env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
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
   'new_physical_calls':0,'cost_warning':'Failed exit can still contain paid offline mathematics or updates.'},stream,indent=2)
  stream.write('\n')
print(execution.read_text(encoding='utf-8'))
raise SystemExit(code)
