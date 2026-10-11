"""Seal S reporting and first contract; preserve raw/root manifests."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

repo=Path(__file__).resolve().parents[1]
root=repo/'results/cpu_validation/2026-10-12_guard_multistep_position_transition'
wall,cpu=time.perf_counter(),time.process_time()
payloads={}; reads=byte_count=0
def copy(source,target):
    global reads,byte_count
    data=source.read_bytes(); reads+=1; byte_count+=len(data)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
    check=target.read_bytes(); reads+=1; byte_count+=len(check)
    if check!=data:
        raise ValueError('copy mismatch:'+str(target))
    payloads[target.relative_to(root).as_posix()]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
      'source':source.relative_to(repo).as_posix()}

if (root/'reporting/manifest.json').exists():
    raise SystemExit('first reporting seal exists; no overwrite')
for name in ('c4_s_reporting_reads.json','read_s_reporting_once.py','check_s_output_once.py','c4_s_contract_execution.json','archive_s_reporting_once.py'):
    copy(repo/'external'/name,root/'reporting'/name)
contract=repo/'external/c4_s_output_contract_01'
if not contract.is_dir():
    raise SystemExit('missing first output contract')
for source in sorted(contract.rglob('*')):
    if source.is_file():
        copy(source,root/'output_contract'/source.relative_to(contract))
proc=subprocess.run(['D:/Python3.10/python.exe','external/check_s_links_once.py','--results'],cwd=repo,capture_output=True)
print(proc.stdout.decode('utf-8',errors='replace'))
if proc.returncode:
    raise SystemExit('link check failed; first copies retained')
copy(repo/'external/c4_s_results_links_01.json',root/'reporting/c4_s_results_links_01.json')
record={'payloads':payloads,'file_reads':reads,'read_bytes':byte_count,'copy_failures':[],
  'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
  'no_scientific_recalculation':True,'root_raw_manifests_unchanged':True}
(root/'reporting/manifest.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='payloads'}))
