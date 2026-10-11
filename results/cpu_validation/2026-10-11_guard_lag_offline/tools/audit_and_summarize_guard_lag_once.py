"""First independent D audit followed by one saved-metric description."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-auditor-sha256',required=True)
args=parser.parse_args()
raw=root/'external/guard_lag_offline_20261011_first'
audit=root/'external/guard_lag_offline_20261011_first_audit.json'
audit_stdout=root/'external/guard_lag_offline_20261011_first_audit_stdout.txt'
summary=root/'external/guard_lag_offline_20261011_summary_01'
summary_stdout=root/'external/guard_lag_offline_20261011_summary_01_stdout.txt'
record=root/'external/guard_lag_offline_20261011_postprocess_execution.json'
assert all(not p.exists() for p in (audit,audit_stdout,summary,summary_stdout,record))
commands=[
 ['D:/Python3.10/python.exe','scripts/audit_guard_lag_offline.py','--input',str(raw),
  '--source-root',str(root/'results/cpu_validation/2026-10-11_guard_exploration'),'--output',str(audit)],
 ['D:/Python3.10/python.exe','external/summarize_guard_lag_saved_once.py','--input',str(raw),
  '--audit',str(audit),'--expected-auditor-sha256',args.expected_auditor_sha256,'--output',str(summary)],
]
env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
results=[]
for command,stdout in zip(commands,(audit_stdout,summary_stdout)):
    started=time.perf_counter()
    with stdout.open('xb') as stream:
        done=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
    results.append({'command':command,'stdout':str(stdout),'exit_code':done.returncode,
        'wrapper_wall_seconds':time.perf_counter()-started,'repeated':False})
    if done.returncode:
        break
with record.open('x',encoding='utf-8',newline='\n') as stream:
    json.dump({'executions':results,'new_physics_calls':0,'online_helper_calls':0,'model_updates':0,
        'prior_C_audit_reexecutions':0},stream,indent=2);stream.write('\n')
print(record.read_text(encoding='utf-8'))
print((summary_stdout if summary_stdout.exists() else audit_stdout).read_text(encoding='utf-8'))
raise SystemExit(results[-1]['exit_code'])
