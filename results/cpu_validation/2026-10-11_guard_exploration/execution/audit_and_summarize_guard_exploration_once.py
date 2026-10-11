"""First independent C audit, then one thin saved-verdict summary."""
from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).resolve().parents[1]
raw = root/'external/guard_exploration_20261011_first'
audit = root/'external/guard_exploration_20261011_first_audit.json'
audit_stdout = root/'external/guard_exploration_20261011_first_audit_stdout.txt'
summary = root/'external/guard_exploration_20261011_summary_01'
summary_stdout = root/'external/guard_exploration_20261011_summary_01_stdout.txt'
record_path = root/'external/guard_exploration_20261011_postprocess_execution.json'
assert all(not p.exists() for p in (audit,audit_stdout,summary,summary_stdout,record_path))

env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
commands = [
 ['D:/Python3.10/python.exe','scripts/audit_guard_exploration_development.py',
  '--input',str(raw),'--output',str(audit)],
 ['D:/Python3.10/python.exe','external/c4_guard_exploration_summary_staging/summarize_guard_exploration_once.py',
  '--input',str(raw),'--audit',str(audit),'--output',str(summary),
  '--expected-auditor-sha256','962a928b5d643ed2a3d4da20da2940a9a4e17932818c859beb204f11bf59ffa3'],
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
  'A_B_audit_reexecutions':0},stream,indent=2);stream.write('\n')
print(record_path.read_text(encoding='utf-8'))
print((summary_stdout if summary_stdout.exists() else audit_stdout).read_text(encoding='utf-8'))
raise SystemExit(records[-1]['exit_code'])
