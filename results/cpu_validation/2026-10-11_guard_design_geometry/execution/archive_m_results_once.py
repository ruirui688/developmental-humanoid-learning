"""Preserve first M diagnostic outputs and execution/check source bytes."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
source = root/'external/c4_m_design_geometry_01'
out = root/'results/cpu_validation/2026-10-11_guard_design_geometry'
out.mkdir(parents=True, exist_ok=False)
started, cpu = time.perf_counter(), time.process_time()
files, reads, size = {}, 0, 0

def copy(path, relative):
    global reads, size
    data = path.read_bytes()
    target = out/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 2
    size += len(data)+len(saved)
    assert data == saved
    files[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'copy_verified': True}

for path in sorted(source.iterdir()):
    if path.is_file():
        copy(path, 'raw/'+path.name)
for name in ('c4_m_design_geometry_01.stdout', 'c4_m_design_geometry_01.stderr', 'c4_m_design_geometry_01.execution.json',
             'run_m_design_geometry_once.py', 'check_m_output_once.py', 'c4_m_output_check_01.json', 'archive_m_results_once.py'):
    copy(root/'external'/name, ('output_contract/' if 'check' in name else 'execution/')+name)
record = {'schema_version': 1, 'files': files, 'raw_manifest_sha256': files['raw/manifest.json']['sha256'],
          'cost': {'binary_reads': reads, 'input_bytes': size, 'copy_checks': len(files), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'SVD_calls': 0, 'offline_estimates': 0, 'physics': 0}
(out/'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'payloads': len(files), 'raw_manifest_sha256': record['raw_manifest_sha256'], 'cost': record['cost']}))
