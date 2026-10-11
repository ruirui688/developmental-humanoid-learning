"""Derive report input from saved Z1 summaries only; no metrics recalculation."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
stage = repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_prediction'
out = repo / 'external/c4_z1_report_input.json'
if out.exists():
    raise FileExistsError(out)
started, cpu = time.perf_counter(), time.process_time()
names = ['raw/run.json', 'raw/metrics.json', 'raw/models.json', 'execution.json', 'manifest.json']
records, files = {}, {}
for name in names:
    data = (stage / name).read_bytes()
    records[name] = json.loads(data)
    files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
result = {'saved': records, 'sources': files, 'reporting_reads': len(names), 'reporting_read_bytes': sum(pin['bytes'] for pin in files.values()), 'JSON_parses': len(names), 'metric_recalculations': 0, 'model_fit_physics_calls': 0, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu}
with out.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
run, metrics = records['raw/run.json'], records['raw/metrics.json']
print(json.dumps({'status': run.get('status'), 'failure': run.get('failure'), 'cost': run.get('cost'), 'metrics': metrics, 'seed_results': run.get('seed_results'), 'outer_wall': records['execution.json']['wall_seconds'], 'archive': records['manifest.json']['cost_before_manifest_write']}))
