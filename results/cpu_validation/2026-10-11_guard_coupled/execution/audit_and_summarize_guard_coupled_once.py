"""First independent B audit, then one thin saved-verdict summary."""
from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).resolve().parents[1]
raw = root/'external/guard_coupled_20261011_first'
audit = root/'external/guard_coupled_20261011_first_audit.json'
audit_stdout = root/'external/guard_coupled_20261011_first_audit_stdout.txt'
summary = root/'external/guard_coupled_20261011_summary_01'
summary_stdout = root/'external/guard_coupled_20261011_summary_01_stdout.txt'
record_path = root/'external/guard_coupled_20261011_postprocess_execution.json'
assert all(not p.exists() for p in (audit,audit_stdout,summary,summary_stdout,record_path))
env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
commands = [
 [str(Path('D:/Python3.10/python.exe')),'scripts/audit_guard_coupled_development.py',
  '--input',str(raw),'--output',str(audit)],
 [str(Path('D:/Python3.10/python.exe')),'external/c4_guard_coupled_summary_staging/summarize_guard_coupled_once.py',
  '--input',str(raw),'--audit',str(audit),'--output',str(summary),
  '--expected-auditor-sha256','c77a1c2a5cfeed08774dab20a6ef5d4e4833264621e37832b3888001182cc10a'],
]
records=[]
for command,stdout in zip(commands,(audit_stdout,summary_stdout)):
 started=time.perf_counter()
 with stdout.open('xb') as stream:
  done=subprocess.run(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
 records.append({'command':command,'stdout':str(stdout),'exit_code':done.returncode,
  'wrapper_wall_seconds':time.perf_counter()-started,'repeated':False})
 if done.returncode:break
with record_path.open('x',encoding='utf-8') as stream:
 json.dump({'executions':records,'new_physical_calls':0,'online_model_updates':0,
  'A_audit_reexecutions':0},stream,indent=2);stream.write('\n')
print(record_path.read_text(encoding='utf-8'))
print((summary_stdout if summary_stdout.exists() else audit_stdout).read_text(encoding='utf-8'))
raise SystemExit(records[-1]['exit_code'])
