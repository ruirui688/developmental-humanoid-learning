"""Read saved failed controls once; no model calls, fit, audit or simulator."""
import gzip
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
source = root/'external/guard_pair_20261011_first'
output = root/'external/guard_pair_20261011_failure_diagnostic_01'
output.mkdir(exist_ok=False)
wall, cpu = time.perf_counter(), time.process_time()
trace_bytes = (source/'trace.jsonl.gz').read_bytes()
rows = []
for line in gzip.decompress(trace_bytes).splitlines():
    item = json.loads(line)
    if item['phase'] != 'control' or item['kind'] not in ('learned_raw', 'learned_guard'):
        continue
    forecast = item['predicted_next_qv'][item['kind']]
    rows.append({'seed': item['seed'], 'kind': item['kind'],
        'source_transition_id': item['shared_transition_id'],
        'requested_nm': item['requested_torque'][:2],
        'begin_q': item['observation_before']['joint_position'][:2],
        'begin_v': item['observation_before']['joint_velocity'][:2],
        'saved_prediction_next_v': forecast[1],
        'measured_next_v': item['observation_after']['joint_velocity'][:2],
        'saved_selected_horizon_last_v': item['planner_decision']['predicted_v'][-1],
        'study_abort': item.get('study_abort'),
        'executed_substeps': item['diagnostics']['executed_substeps']})
result = {'scope': 'Extracted saved failed control decisions; descriptive diagnosis only.',
    'trace_sha256': hashlib.sha256(trace_bytes).hexdigest(),
    'trace_read_passes': 1, 'new_physics': 0, 'new_model_updates': 0,
    'new_predictions': 0, 'audit_executions': 0, 'rows': rows,
    'claim_boundary': 'No counterfactual actions or new gate; pulse calibration and sustained control differ.',
    'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu}
(output/'saved_failed_controls.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
(output/'tool_source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'output': str(output), 'rows': len(rows), 'new_predictions': 0,
    'new_physics': 0, 'wall_seconds': result['wall_seconds']}))
