"""Independently verify only newly produced Z1 endpoint RMSE; no model calls."""
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
raw = repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_prediction/raw'
out = repo / 'external/c4_z1_new_metrics_check.json'
if out.exists():
    raise FileExistsError(out)
began, cpu = time.perf_counter(), time.process_time()
blob = (raw / 'predictions.jsonl.gz').read_bytes()
run_bytes = (raw / 'run.json').read_bytes()
run = json.loads(run_bytes)
uncompressed = gzip.decompress(blob)
groups = defaultdict(lambda: {'q': [[], []], 'v': [[], []]})
population = defaultdict(int)
for line in uncompressed.splitlines():
    row = json.loads(line)
    assert row['available'] is True
    key = (row['seed'], row['horizon'], row['model'])
    population[key] += 1
    for signal in ('q', 'v'):
        path = row['predicted_'+signal+'_path']
        assert len(path) == row['horizon']
        actual = row['actual_endpoint_'+signal+'2']
        for axis in range(2):
            error = path[-1][axis]-actual[axis]
            assert math.isfinite(error)
            groups[key][signal][axis].append(error*error)
checks = []
for seed_row in run['seed_results']:
    score = seed_row['prediction_scores']
    for h, horizon in score['horizons'].items():
        for model, metrics in horizon['models'].items():
            key = (seed_row['seed'], int(h), model)
            assert population[key] == horizon['planned_origin_count'] == metrics['observed_origin_count']
            for signal, field in [('q', 'q_rmse_axis_rad'), ('v', 'v_rmse_axis_rad_s')]:
                computed = [math.sqrt(math.fsum(errors)/len(errors)) for errors in groups[key][signal]]
                saved = metrics[field]
                assert all(math.isclose(c, s, rel_tol=1e-12, abs_tol=1e-15) for c, s in zip(computed, saved))
                checks.append({'seed': key[0], 'horizon': key[1], 'model': model, 'signal': signal, 'computed_axis': computed, 'saved_axis': saved, 'passed': True})
record = {'status': 'passed', 'new_Z1_RMSE_vectors_checked': len(checks), 'prediction_records': sum(population.values()), 'checks': checks, 'source_files': {'predictions.jsonl.gz': {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}, 'run.json': {'bytes': len(run_bytes), 'sha256': hashlib.sha256(run_bytes).hexdigest()}}, 'reads': 2, 'read_bytes': len(blob)+len(run_bytes), 'decompressed_prediction_bytes': len(uncompressed), 'wall_seconds': time.perf_counter()-began, 'cpu_seconds': time.process_time()-cpu, 'model_fit_physics_calls': 0, 'old_metrics_recomputed': False, 'automatic_retry': False}
with out.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
print(json.dumps({k: v for k, v in record.items() if k not in ('checks', 'source_files')}))
