"""One-time original-byte I result archive; no scoring rerun."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
out = root / 'results/cpu_validation/2026-10-11_guard_native_residual'
out.mkdir(parents=True, exist_ok=False)
started, cpu = time.perf_counter(), time.process_time()
files, reads, size = {}, 0, 0
def copy(source, relative):
    global reads, size
    data = source.read_bytes()
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 2
    size += len(data)+len(saved)
    assert data == saved, relative
    files[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'copy_verified': True}
for name in ('manifest.json', 'run.json', 'description.json', 'adjacent_pairs.jsonl'):
    copy(root / 'external/c4_i_native_residual_01' / name, 'raw/' + name)
for name in ('check_i_saved_output_once.py', 'c4_i_output_check_01.json'):
    copy(root / 'external' / name, 'output_contract/' + name)
for suffix in ('stdout', 'stderr', 'execution.json'):
    copy(root / 'external' / ('c4_i_native_residual_01.' + suffix), 'first_process/' + suffix)
copy(Path(__file__), 'archive_i_saved_once.py')
record = {'schema_version': 1, 'files': files,
          'cost': {'binary_reads': reads, 'input_bytes': size, 'copy_checks': len(files), 'copy_failures': 0,
                   'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu},
          'scope': 'original bytes only; no I rerun, score/gate statistic, source H/G audit, model or physics'}
(out / 'manifest.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'I_raw_manifest_sha256': files['raw/manifest.json']['sha256'], 'cost': record['cost'], 'payloads': len(files), 'payload_bytes': sum(x['bytes'] for x in files.values())}))
