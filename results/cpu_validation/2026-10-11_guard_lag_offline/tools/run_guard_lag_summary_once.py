"""One saved D summary after disclosed read-unit reconciliation."""
import json
from pathlib import Path
import subprocess
import time

root=Path(__file__).resolve().parents[1]
output=root/'external/guard_lag_offline_20261011_summary_01'
stdout=root/'external/guard_lag_offline_20261011_summary_01_stdout.txt'
record=root/'external/guard_lag_offline_20261011_summary_execution.json'
assert not output.exists() and not stdout.exists() and not record.exists()
command=['D:/Python3.10/python.exe','external/summarize_guard_lag_saved_once.py',
 '--input','external/guard_lag_offline_20261011_first','--audit','external/guard_lag_offline_20261011_first_audit.json',
 '--expected-auditor-sha256','bede59d0984edddf6d7384b6d11c0beddae711dfcc616571f4bfd9ee8ce3211b',
 '--read-accounting-reconciliation','external/c4_lag_read_accounting_reconciliation/first_reconciliation.json',
 '--expected-reconciliation-tool-sha256','59fb967f51b50c5ba9f42ded7bea2a68ec958b76e85f0653cdd85740493ac420',
 '--output',str(output)]
started=time.perf_counter()
with stdout.open('xb') as stream:
    done=subprocess.run(command,cwd=root,stdout=stream,stderr=subprocess.STDOUT)
with record.open('x',encoding='utf-8',newline='\n') as stream:
    json.dump({'command':command,'exit_code':done.returncode,'wrapper_wall_seconds':time.perf_counter()-started,
        'repeated':False,'model_calls':0,'physics_calls':0,'audit_reexecutions':0},stream,indent=2);stream.write('\n')
print(stdout.read_text(encoding='utf-8'))
raise SystemExit(done.returncode)
