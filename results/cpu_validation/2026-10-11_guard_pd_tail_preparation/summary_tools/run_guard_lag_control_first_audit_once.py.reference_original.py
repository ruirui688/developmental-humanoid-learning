"""One independent E first audit with outer timing and original stdout."""
import json
from pathlib import Path
import subprocess
import time
root=Path(__file__).resolve().parents[1]
target=root/'external/guard_lag_control_20261011_first_audit.json'
execution=root/'external/guard_lag_control_20261011_first_audit_execution.json'
stdout=root/'external/guard_lag_control_20261011_first_audit_stdout.txt'
assert not any(p.exists() for p in (target,execution,stdout))
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert commit=='dda82b1854d80483d0b16e0532bc414906e6a402'
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True)==''
command=['D:/Python3.10/python.exe','scripts/audit_guard_lag_control.py','--input','external/guard_lag_control_20261011_first','--output',str(target)]
wall=time.perf_counter();code=error=None
try:
    with stdout.open('xb') as stream:
        code=subprocess.run(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT).returncode
except BaseException as exc:
    error={'type':type(exc).__name__,'message':str(exc)}
    raise
finally:
    with execution.open('x',encoding='utf-8') as f:
        json.dump({'source_commit':commit,'command':command,'exit_code':code,'wrapper_exception':error,
            'wrapper_wall_seconds':time.perf_counter()-wall,'repeated':False,
            'new_physics':0,'new_model_updates':0,'old_audit_reexecutions':0},f,indent=2);f.write('\n')
print(execution.read_text(encoding='utf-8'))
raise SystemExit(code)
