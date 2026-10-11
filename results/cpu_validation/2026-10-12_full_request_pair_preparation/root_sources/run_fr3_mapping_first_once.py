"""First reviewed FR3 mapping fixture, preserving all first output."""
from pathlib import Path
import hashlib
import json
import subprocess
import time

root=Path(__file__).resolve().parents[1]
fixture=root/'external/fr3_candidate/check_full_request_mapping_once.py'
assert hashlib.sha256(fixture.read_bytes()).hexdigest()=='6b08cc4e180c033d39a9a8f4ebaaf16f6c1bda51d306263594eed254e2d1b45a'
capture=root/'external/fr3_first_mapping_contract'
assert not capture.exists(), 'first fixture capture exists; do not rerun'
capture.mkdir()
command=[str(root/'external/cpu_physics_env/Scripts/python.exe'),str(fixture),'--repo',str(root),
    '--controller-source',str(root/'external/fr3_candidate/full_request_pair_mpc.py'),
    '--counted-adapter-source',str(root/'external/fr3_candidate/full_request_pair_development.py'),
    '--output',str(capture/'contract.json')]
start=time.perf_counter()
with (capture/'stdout.log').open('xb') as stdout,(capture/'stderr.log').open('xb') as stderr:
    process=subprocess.run(command,cwd=root,stdout=stdout,stderr=stderr,check=False)
receipt={'first_attempt':True,'automatic_retry':False,'command':command,
    'exit_code':process.returncode,'wall_seconds':time.perf_counter()-start}
(capture/'first_execution_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt))
print((capture/'stdout.log').read_text(encoding='utf-8'))
raise SystemExit(process.returncode)
