"""Read completed Z2 saved summaries once, without recalculating metrics."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
stage = repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_control'
out = repo / 'external/c4_z2_report_input.json'
if out.exists():
    raise FileExistsError(out)
began, cpu = time.perf_counter(), time.process_time()
saved, pins = {}, {}
for name in ['raw/run.json', 'raw/metrics.json', 'raw/models.json', 'execution.json', 'manifest.json']:
    data = (stage / name).read_bytes()
    saved[name] = json.loads(data)
    pins[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
record = {'saved': saved, 'source_files': pins, 'reads': len(pins), 'read_bytes': sum(p['bytes'] for p in pins.values()), 'wall_seconds': time.perf_counter()-began, 'cpu_seconds': time.process_time()-cpu, 'metric_recalculations': 0, 'model_fit_physics_calls': 0}
with out.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
run = saved['raw/run.json']
print(json.dumps({'status': run['status'], 'failure': run['failure'], 'cost': run['cost'], 'metrics': saved['raw/metrics.json'], 'seeds': [{'seed': row['seed'], 'tracking': row['tracking_scores'], 'control_completeness': {name: {'complete': t['complete'], 'stop': t['stop'], 'failure': t['failure']} for name,t in row['controls'].items()}} for row in run['seed_results']], 'outer_wall': saved['execution.json']['wall_seconds']}))
