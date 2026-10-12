"""Copy and bind first IV3 saved payload; no trace decode or scientific recomputation."""
from pathlib import Path
import hashlib
import json
import shutil
import time
import zipfile

root = Path(__file__).resolve().parents[1]
source = root/'external/iv3_near_reference_first/raw'
destination = root/'results/cpu_validation/2026-10-12_near_reference_identification'
destination.mkdir(exist_ok=False)
raw = destination/'raw'
raw.mkdir()
wall = time.perf_counter()
payload = {}
for path in sorted(source.iterdir()):
    if path.is_file():
        data = path.read_bytes()
        target = raw/path.name
        target.write_bytes(data)
        copied = target.read_bytes()
        assert data == copied, path.name
        payload['raw/'+path.name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
run = json.loads((raw/'run.json').read_bytes())
metrics = json.loads((raw/'metrics.json').read_bytes())
models = json.loads((raw/'models.json').read_bytes())
moments = json.loads((raw/'moments.json').read_bytes())
complete = run['status'] == 'completed'
checks = []
def check(name, value):
    checks.append({'name': name, 'passed': bool(value)})
check('first_frozen_source_and_status', run['experiment_id'] == 'IV3' and run['source']['clean_committed_bytes_verified'] and run['status'] in ['completed','stopped','failed'])
check('saved_metrics_match_run', metrics == run['metrics'])
check('three_declared_trials_and_fits', len(run['trials']) == 3 and len(run['fits']) == 3)
check('full_planned_1443_unique_prediction_slots', len(run['complete_prediction_population']) == 1443 and len({(r['seed'],r['horizon'],r['origin_active_index']) for r in run['complete_prediction_population']}) == 1443)
check('actual_physics_budget_or_complete_counts', run['cost'].get('total_control_attempts',0) <= 9000 and run['cost'].get('confirmed_physics_substeps',0) <= 9000 and (not complete or (run['cost']['total_control_attempts'] == 9000 and run['cost']['confirmed_physics_substeps'] == 9000)))
check('new_labels_and_state_fits_or_partial', run['new_unique_training_scalar_labels'] <= 12000 and (not complete or (run['new_unique_training_scalar_labels'] == 12000 and run['cost']['state_fit_returns'] == 3 and run['cost']['state_fitted_coefficient_scalar_outputs'] == 30)))
check('new_prediction_budget_or_complete', run['cost'].get('pair_prediction_returns',0) <= 62340 and run['cost'].get('scalar_velocity_head_returns',0) <= 124680 and (not complete or (run['cost']['pair_prediction_returns'] == 62340 and run['cost']['scalar_velocity_head_returns'] == 124680)))
check('complete_trial_fit_and_prediction_if_completed', not complete or (run['first_failure'] is None and all(r['status']=='completed' and r['contact_qualification']['passed'] for r in run['trials']) and all(r['available'] and r['status']=='completed' for r in run['fits']) and all(r['available'] and r['status']=='completed' for r in run['complete_prediction_population'])))
check('all_three_full_rank5_if_completed', not complete or all(moments[str(s)]['samples'] == 2000 and moments[str(s)]['fit']['rank'] == 5 for s in [8101,8102,8103]))
check('old_models_frozen_and_new_action8_identity', all(item['parameter_fingerprint'] == item['fingerprint_before_prediction'] for group in models.values() for item in group.values()) and all('IV3' not in g or all(g['IV3']['coefficients'][a][4:8] == g['IV1']['coefficients'][a][4:8] for a in range(2)) for g in models.values()))
check('no_evaluation_fit_reuse_RLS_or_old_math', all(run[k] == 0 for k in ['reused_training_labels','evaluation_fit_label_uses','bias_calibration_label_uses','new_evaluation_physics','old_model_prediction_calls','old_fit_or_gate_recomputations','RLS_updates']))
check('seen_development_only', run['seen_evaluation_development_only'] is True and run['heldout_validation'] is False)
check('science_and_controller_flags_remain_false', all(run[k] is False for k in ['scientific_adoption','old_free_root_C4_validation','c4_scientific_validation','c4_contact_scientific_validation','c5_scientific_dependency_released','control_candidate_opened']))
with zipfile.ZipFile(raw/'source.zip') as archive:
    check('source_zip_exact_closure', set(archive.namelist()) == set(run['source']['files']))
    for name, identity in run['source']['files'].items():
        data = archive.read(name)
        check('source_zip_identity:'+name, {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()} == identity)
result = {'status':'passed' if all(r['passed'] for r in checks) else 'failed', 'checks':checks, 'payload':payload,
          'run_status_transcribed':run['status'], 'iv3_prediction_gate_transcribed':metrics['iv3_prediction_gate_passed'],
          'cumulative_controls':run['prior_physics_control_calls']+run['cost'].get('total_control_attempts',0),
          'cumulative_substeps':run['prior_physics_substeps']+run['cost'].get('confirmed_physics_substeps',0),
          'historical_RLS_scalar_updates':run['historical_RLS_scalar_updates'], 'continuous_goal':'active',
          'new_math_calls':0, 'fit_calls':0, 'model_calls':0, 'physics_calls':0, 'trace_decode_calls':0,
          'old_scientific_gate_recomputed':False, 'wall_seconds_before_write':time.perf_counter()-wall, 'unmeasured_IO':'unknown_not_zero'}
(destination/'delivery_checks.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8',newline='\n')
shutil.copyfile(Path(__file__),destination/'deliver_iv3_once.py')
print({'status':result['status'], 'checks':len(checks), 'run_status':run['status'], 'IV3_gate':metrics['iv3_prediction_gate_passed']})
assert result['status'] == 'passed', 'saved_payload_identity_or_population_check_failed'
