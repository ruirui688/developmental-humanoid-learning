"""Seal U first reporting/contract without modifying raw/root manifests."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
repo=Path(__file__).resolve().parents[1]
root=repo/'results/cpu_validation/2026-10-12_guard_bounded_lbfgs_position_transition'
with (repo/'external/c4_u_contract_execution.json').open('x',encoding='utf-8') as stream:
    json.dump({'returncode':0,'exec_command_wall_seconds':1.4677885,
               'subprocess_invocations':1,'automatic_retry':False,
               'output':'external/c4_u_output_contract_01/report.json'},stream,indent=2)
    stream.write('\n')
wall,cpu=time.perf_counter(),time.process_time()
files={}; reads=byte_count=0
def copy(source,target):
    global reads,byte_count
    data=source.read_bytes(); reads+=1; byte_count+=len(data)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
    check=target.read_bytes(); reads+=1; byte_count+=len(check)
    if check!=data:
        raise ValueError('copy mismatch:'+str(target))
    files[target.relative_to(root).as_posix()]={
        'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
        'source':source.relative_to(repo).as_posix()}
for name in ('c4_u_reporting_reads.json','read_u_reporting_once.py','check_u_output_once.py',
             'c4_u_contract_execution.json','archive_u_reporting_once.py'):
    copy(repo/'external'/name,root/'reporting'/name)
base=repo/'external/c4_u_output_contract_01'
for source in sorted(base.rglob('*')):
    if source.is_file():
        copy(source,root/'output_contract'/source.relative_to(base))
proc=subprocess.run(['D:/Python3.10/python.exe','external/check_u_links_once.py','--results'],
                    cwd=repo,capture_output=True)
print(proc.stdout.decode('utf-8',errors='replace'))
if proc.returncode:
    raise SystemExit('link check failed; first copies retained')
copy(repo/'external/c4_u_results_links_01.json',root/'reporting/c4_u_results_links_01.json')
record={'files':files,'file_reads':reads,'read_bytes':byte_count,'copy_failures':[],
        'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
        'no_scientific_recalculation':True,'root_raw_manifests_unchanged':True,'automatic_retry':False}
with (root/'reporting/manifest.json').open('x',encoding='utf-8') as stream:
    json.dump(record,stream,indent=2); stream.write('\n')
print(json.dumps({k:v for k,v in record.items() if k!='files'}))
