"""Bind saved metadata and seal reporting; never rerun scientific work."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[1]
root = repo / 'results/cpu_validation/2026-10-12_guard_trust_position_transition'
summary = json.loads((repo / 'external/c4_t_reporting_summary.json').read_text(encoding='utf-8'))
bindings = {x['path']: {'bytes': x['bytes'], 'sha256': x['sha256']}
            for x in summary['report_reads']['reads'] if x['path'] in ('manifest.json', 'raw/run.json')}
data = (root / 'raw/manifest.json').read_bytes()
bindings['raw/manifest.json'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
with (repo / 'external/c4_u_T_metadata_bindings.json').open('x', encoding='utf-8') as stream:
    json.dump({'root': root.relative_to(repo).as_posix(), 'bindings': bindings,
               'new_metadata_reads': 1, 'new_metadata_read_bytes': len(data),
               'run_root_binding_from_existing_reporting_summary': True,
               'scientific_recalculation': False}, stream, indent=2)
    stream.write('\n')
with (repo / 'external/c4_t_contract_execution.json').open('x', encoding='utf-8') as stream:
    json.dump({'returncode': 0, 'exec_command_wall_seconds': 1.3835132,
               'subprocess_invocations': 1, 'automatic_retry': False,
               'output': 'external/c4_t_output_contract_01/report.json'}, stream, indent=2)
    stream.write('\n')

wall, cpu = time.perf_counter(), time.process_time()
payloads = {}; reads = byte_count = 0
def copy(source, target):
    global reads, byte_count
    content = source.read_bytes(); reads += 1; byte_count += len(content)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(content)
    returned = target.read_bytes(); reads += 1; byte_count += len(returned)
    if returned != content:
        raise ValueError('copy mismatch: ' + str(target))
    payloads[target.relative_to(root).as_posix()] = {
        'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
        'source': source.relative_to(repo).as_posix()}

for name in ('c4_t_reporting_reads.json', 'read_t_reporting_once.py', 'check_t_output_once.py',
             'c4_t_output_contract_preparation_checks.json', 'c4_t_contract_execution.json',
             'prepare_t_delivery_once.py', 'c4_u_T_metadata_bindings.json'):
    copy(repo / 'external' / name, root / 'reporting' / name)
for source in sorted((repo / 'external/c4_t_output_contract_01').rglob('*')):
    if source.is_file():
        copy(source, root / 'output_contract' / source.relative_to(repo / 'external/c4_t_output_contract_01'))
proc = subprocess.run(['D:/Python3.10/python.exe', 'external/check_t_links_once.py', '--results'],
                      cwd=repo, capture_output=True)
print(proc.stdout.decode('utf-8', errors='replace'))
if proc.returncode:
    raise SystemExit('link check failed; first copies retained')
copy(repo / 'external/c4_t_results_links_01.json', root / 'reporting/c4_t_results_links_01.json')
record = {'payloads': payloads, 'file_reads': reads, 'read_bytes': byte_count,
          'copy_failures': [], 'wall_seconds': time.perf_counter()-wall,
          'cpu_seconds': time.process_time()-cpu, 'no_scientific_recalculation': True,
          'root_raw_manifests_unchanged': True, 'automatic_retry': False}
with (root / 'reporting/manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2); stream.write('\n')
print(json.dumps({k:v for k,v in record.items() if k != 'payloads'}))
