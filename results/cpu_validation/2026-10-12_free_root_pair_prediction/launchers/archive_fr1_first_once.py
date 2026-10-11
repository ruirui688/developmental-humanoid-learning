"""Archive the first new FR1 outputs once. No model, replay or physics."""
from pathlib import Path
import hashlib
import json
import time

root = Path(__file__).resolve().parents[1]
source = root/'external/fr1_first_execution'
dest = root/'results/cpu_validation/2026-10-12_free_root_pair_prediction'
assert (source/'first_execution_receipt.json').is_file(), 'first process still active'
assert not dest.exists(), 'first archival destination already exists'
dest.mkdir()
start_wall, start_cpu = time.perf_counter(), time.process_time()
pins, reads, read_bytes_count, writes, cache = {}, 0, 0, 0, {}
def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()
def write(relative, data):
    global writes
    path = dest/relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    writes += 1
    pins[relative] = pin(data)
def read(path):
    global reads, read_bytes_count
    data = path.read_bytes()
    reads += 1
    read_bytes_count += len(data)
    return data
for path in sorted(source.rglob('*')):
    if path.is_file():
        relative = path.relative_to(source).as_posix()
        data = read(path)
        write(relative, data)
        if relative in ('raw/run.json', 'raw/metrics.json', 'raw/manifest.json', 'first_execution_receipt.json'):
            cache[relative] = json.loads(data)
for name in ('run_fr1_first_once.py', 'archive_fr1_first_once.py'):
    write('launchers/'+name, read(root/'external'/name))
for name, expected in cache['raw/manifest.json']['files'].items():
    assert pins['raw/'+name] == expected, name
run, metrics = cache['raw/run.json'], cache['raw/metrics.json']
write('report_inputs.json', encoded({
    'experiment_id': run['experiment_id'], 'source': run['source'], 'status': run['status'],
    'runtime': run['runtime'], 'cost': run['cost'], 'failure': run['failure'],
    'unattempted_seeds': run['unattempted_seeds'], 'seed_results': run['seed_results'],
    'metrics': metrics, 'first_execution': cache['first_execution_receipt.json'],
    'raw_verified_for_copy_only': True, 'models_or_physics_or_metrics_recomputed': 0,
}))
copy = {'source': str(source), 'destination': str(dest), 'first_archive': True,
    'reads': reads, 'bytes_read': read_bytes_count, 'writes_before_receipt': writes,
    'raw_copy_pins_match_first_manifest': True, 'first_source_commit': run['source']['commit'],
    'wall_seconds_before_receipt': time.perf_counter()-start_wall,
    'cpu_seconds_before_receipt': time.process_time()-start_cpu,
    'model_or_fit_or_physics_or_old_science': 0}
write('archive_receipt.json', encoded(copy))
write('manifest.json', encoded({'stage': 'FR1_first_prediction_archive', 'status': run['status'],
    'files_before_top_manifest': pins.copy(), 'scientific_adoption': False,
    'continuous_goal_stays_active': True}))
print(json.dumps({'first_FR1_archive_complete': True, 'status': run['status'],
    'fr1_prediction_gate_passed': metrics.get('fr1_prediction_gate_passed'),
    'cost': run['cost'], 'copy': copy}, ensure_ascii=False))
