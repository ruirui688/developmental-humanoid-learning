"""Read audited C2-B summary only; retain one measured extraction, no physical/model calls."""
import base64
import hashlib
import json
import math
from pathlib import Path
import time

INPUT = Path('external/local_dose_20261011_development_summary.json')
OUTPUT = Path('external/c2b_review_extracted_tables_01.json')
MODELS = ['old_linear4_mpc', 'old_hinge5_mpc', 'new_linear4_mpc', 'new_hinge5_mpc', 'nominal_mpc']
PREDICTORS = MODELS+['persistence']
ANCHOR = 'old_hinge5_mpc'


def mean(values):
    if len(values) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        return None
    return sum(values)/3


def main():
    wall, cpu = time.perf_counter(), time.process_time()
    if OUTPUT.exists():
        raise ValueError('Refusing overwrite.')
    source = Path(__file__).read_bytes()
    data_bytes = INPUT.read_bytes()
    data_hash = hashlib.sha256(data_bytes).hexdigest()
    data = json.loads(data_bytes)
    if data['split'] != 'development' or [s['seed'] for s in data['audited_seed_details']] != [0, 1, 2]:
        raise ValueError('Only audited development 0/1/2.')
    seeds = data['audited_seed_details']
    predictions = {}
    for kind in ('prediction_low', 'prediction_full'):
        predictions[kind] = {}
        for field in ('velocity_prediction_rmse', 'position_prediction_rmse'):
            predictions[kind][field] = {}
            for predictor in PREDICTORS:
                values = [s['evaluations'][kind][field][predictor] if s['evaluations'][kind]['eligible'] else None for s in seeds]
                predictions[kind][field][predictor] = {'per_seed': values, 'raw_mean': mean(values)}
    controls, coverage, efforts, risk, fifty = {}, {}, {}, {}, {}
    for model in MODELS:
        rows = [s['evaluations'][model] for s in seeds]
        tracking = [r['tracking_rmse_rad'] if r['eligible'] else None for r in rows]
        effort = {k: [r['control_effort'][k] if r['eligible'] and r['actual_effort_complete'] else None for r in rows]
                  for k in ('actual_absolute_nm_s', 'actual_squared_nm2_s')}
        controls[model] = {'tracking_per_seed': tracking, 'tracking_raw_mean': mean(tracking),
                           'actual_control_effort': {k: {'per_seed': v, 'raw_mean': mean(v)} for k, v in effort.items()}}
        coverage[model] = [r.get('state_coverage') for r in rows]
        risk[model] = [{phase: r['phase_risk'][phase] for phase in ('prefix', 'control')} |
                       {'full': r['full_risk'], 'telemetry_complete': r['risk_telemetry_complete'],
                        'missing_risk_substeps': r['missing_risk_substeps']} for r in rows]
    for kind in ('calibration_old', 'calibration_new', 'prediction_low', 'prediction_full'):
        efforts[kind] = [{p: r['evaluations'][kind]['phase_effort'][p] for p in ('prefix', 'calibration', 'prediction')}
                        for r in seeds]
    for kind in ('prediction_low', 'prediction_full', *MODELS):
        rows = [s['evaluations'][kind] for s in seeds]
        selected = [next(x for x in r['free_rollouts'] if x['horizon_control_steps'] == 50) for r in rows]
        fifty[kind] = {'per_seed': selected, 'predictor_raw_means': {}}
        for predictor in PREDICTORS:
            metrics = {}
            for key in ('terminal_position_rmse_rad', 'terminal_velocity_rmse_rad_s', 'path_position_rmse_rad', 'path_velocity_rmse_rad_s'):
                values = [s['predictors'][predictor][key] for s in selected]
                metrics[key] = {'per_seed': values, 'raw_mean': mean(values)}
            fifty[kind]['predictor_raw_means'][predictor] = metrics
    root_mean = controls[ANCHOR]['tracking_raw_mean']
    for model in MODELS:
        value = controls[model]['tracking_raw_mean']
        controls[model]['tracking_mean_change_from_anchor'] = value/root_mean-1 if root_mean and value is not None else None
        for key, row in controls[model]['actual_control_effort'].items():
            anchor = controls[ANCHOR]['actual_control_effort'][key]['raw_mean']
            row['relative_change_from_anchor'] = row['raw_mean']/anchor-1 if anchor and row['raw_mean'] is not None else None
    result = {'source_commit': data['source_commit'], 'input_summary_sha256': data_hash,
              'source_script_sha256': hashlib.sha256(source).hexdigest(),
              'source_script_bytes_base64': base64.b64encode(source).decode('ascii'),
              'controls': controls, 'common_predictions': predictions, 'coverage': coverage,
              'phase_efforts': efforts, 'controller_risk': risk, 'horizon_50': fifty,
              'adoption_gate': data['independent_development_selection'],
              'budget': data['formal_collection_budget'],
              'semantics': 'Three raw per-seed arithmetic means, no significance; common prediction paired inputs, controller trajectories differ. All full/prefix/control risk per seed retained. No simulator, model prediction, fitting or heldout read.',
              'execution': {'physical_simulation_calls': 0, 'model_prediction_calls': 0,
                            'real_parameter_updates': 0, 'new_environment_interactions': 0}}
    if hashlib.sha256(INPUT.read_bytes()).hexdigest() != data_hash:
        raise ValueError('Summary input changed.')
    result['execution'].update(wall_seconds=time.perf_counter()-wall, cpu_seconds=time.process_time()-cpu,
                               timing_scope='main through extraction/source bytes/input unchanged check; excludes import and JSON writing')
    with OUTPUT.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(OUTPUT), 'source_sha256': result['source_script_sha256'],
                      'input_summary_sha256': data_hash, 'execution': result['execution']}))


if __name__ == '__main__':
    main()
