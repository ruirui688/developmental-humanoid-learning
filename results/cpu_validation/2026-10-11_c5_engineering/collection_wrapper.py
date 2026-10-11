import json
import os
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
prefix=root/'external/c5_engineering_20261011_first'
assert not prefix.exists()
execution=Path(str(prefix)+'_execution.json')
stdout=Path(str(prefix)+'_stdout.txt')
assert not execution.exists() and not stdout.exists()
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True)==''
env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
command=[str(root/'external/cpu_physics_env/Scripts/python.exe'),'-m',
         'developmental_physics.c5_engineering','--project-root',str(root),'--output',str(prefix)]
start=time.perf_counter()
with stdout.open('xb') as stream:
    result=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
record={'command':command,'source_commit':commit,'exit_code':result.returncode,
        'wrapper_wall_seconds':time.perf_counter()-start,
        'repeated':False,'wrapper_does_not_infer_zero_cost_from_failed_exit':True}
execution.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record))
