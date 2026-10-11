"""Single standard-library extraction of the already completed C2-C review."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

wall, cpu = time.perf_counter(), time.process_time()
root = Path(__file__).resolve().parent.parent
input_path = root/'external/local_coverage_20261011_development_summary.json'
output_path = root/'external/c2c_review_tables_01.json'
if output_path.exists():
    raise SystemExit('Refusing repeated extraction or overwrite.')
blob = input_path.read_bytes()
summary = json.loads(blob)
if hashlib.sha256(blob).hexdigest() != 'f6658949cbcecbc1f425db77c11f41d64aaa861b3a919ef87d3f91242c000163':
    raise SystemExit('Summary input changed.')
seeds = []
audited = {s['seed']: s for s in summary['audited_seed_details']}
for s in summary['raw_recomputed_seed_details']:
    evaluations = {}
    for kind, ev in s['evaluations'].items():
        evaluations[kind] = {k: ev[k] for k in ('completed', 'eligible', 'status', 'study_aborted',
            'environment_terminated', 'tracking_rmse_rad', 'position_prediction_rmse', 'velocity_prediction_rmse',
            'control_effort', 'actual_effort_complete', 'phase_effort', 'paid_budget')}
        evaluations[kind]['state_coverage'] = ev.get('state_coverage')
        evaluations[kind]['audited_risk_and_multistep'] = {k: audited[s['seed']]['evaluations'][kind][k]
            for k in ('full_risk', 'phase_risk', 'control_risk', 'missing_risk_substeps', 'risk_telemetry_complete',
                'phase_risk_missing_substeps', 'free_rollouts', 'conditional_metrics')}
    seeds.append({'seed': s['seed'], 'calibration_support': s['calibration_support'],
        'models': s['models'], 'evaluations': evaluations})
source = Path(__file__).read_bytes()
report = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'input_path': str(input_path), 'input_sha256': hashlib.sha256(blob).hexdigest(),
    'extraction_source_sha256': hashlib.sha256(source).hexdigest(),
    'extraction_source_bytes_base64': base64.b64encode(source).decode('ascii'),
    'checks': summary['checks'], 'failed': summary['failed'],
    'independent_adoption_gate': summary['independent_adoption_gate'],
    'raw_three_seed_means': summary['raw_three_seed_means'],
    'budget': summary['independently_recomputed_budget'], 'phase_budget': summary['independently_recomputed_phase_budget'],
    'statuses': summary['statuses'], 'stops': summary['stops'], 'seeds': seeds,
    'physical_simulation_calls': 0, 'model_prediction_calls': 0, 'rls_replay_calls': 0,
    'real_parameter_updates': 0, 'new_environment_interactions': 0,
    'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
    'timing_scope': 'extraction entry through input/source reads and assembly; excludes imports and JSON writing'}
with output_path.open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write('\n')
compact = {
    'output_path': str(output_path), 'output_sha256': hashlib.sha256(output_path.read_bytes()).hexdigest(),
    'source_sha256': report['extraction_source_sha256'], 'wall_seconds': report['wall_seconds'],
    'cpu_seconds': report['cpu_seconds'], 'gate': report['independent_adoption_gate'],
    'means': report['raw_three_seed_means'],
    'calibration_support': [{'seed': s['seed'], 'support': s['calibration_support']} for s in seeds],
    'control_risk': [{ 'seed': s['seed'], 'trials': {k: s['evaluations'][k]['audited_risk_and_multistep']['control_risk']
        for k in ('short_mpc', 'reordered_mpc', 'nominal_mpc')}} for s in seeds],
    'calibration_effort': [{'seed': s['seed'], 'trials': {k: s['evaluations'][k]['phase_effort']['calibration']['independent_effort']
        for k in ('calibration_short', 'calibration_reordered')}} for s in seeds],
    'prediction_per_seed': [{'seed': s['seed'], 'trials': {k: {field: s['evaluations'][k][field]
        for field in ('position_prediction_rmse', 'velocity_prediction_rmse')}
        for k in ('prediction_low', 'prediction_full')}} for s in seeds],
}
print(json.dumps(compact, ensure_ascii=False))
