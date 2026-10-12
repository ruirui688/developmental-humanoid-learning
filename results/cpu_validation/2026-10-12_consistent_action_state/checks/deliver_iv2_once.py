"""Copy first IV2 originals and check saved identities/populations without replay."""
from pathlib import Path
import hashlib,json,shutil,time,zipfile
import numpy as np
root=Path(__file__).resolve().parents[1]
src=root/'external/iv2_state_refit_first/raw'
out=root/'results/cpu_validation/2026-10-12_consistent_action_state'
out.mkdir(parents=True,exist_ok=False);(out/'raw').mkdir();(out/'checks').mkdir()
wall,cpu=time.perf_counter(),time.process_time()
payload={}
for name in ['run.json','models.json','moments.json','metrics.json','source.zip','source_trace.jsonl.gz','predictions.jsonl.gz','first_stdout.log','first_stderr.log']:
 data=(src/name).read_bytes();(out/'raw'/name).write_bytes(data)
 payload['raw/'+name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
run,models,moments,metrics=(json.loads((out/'raw'/name).read_bytes()) for name in ['run.json','models.json','moments.json','metrics.json'])
checks=[]
def check(name,passed):checks.append({'name':name,'passed':bool(passed)})
check('source_exact_frozen_commit',run['source']['commit']=='d8491b2e0f8b3bae649b8bf9a297bebba7f76270' and run['source']['clean_committed_bytes_verified'])
check('saved_metrics_identical',run['metrics']==metrics)
check('planned_population_preserved',len(run['fits'])==3 and len(run['trials'])==3 and len(run['complete_prediction_population'])==5772)
check('complete_execution_and_fresh_population',run['status']=='completed' and run['first_failure'] is None and all(t['status']=='completed' for t in run['trials']) and all(t['available'] for t in run['complete_prediction_population']))
check('stored_cost_population',run['cost'].get('total_control_attempts')==6000 and run['cost'].get('confirmed_physics_substeps')==6000 and run['cost'].get('pair_prediction_returns')==249360)
check('native_reuse_and_no_new_training',run['cost'].get('reused_state_fit_scalar_label_uses')==12000 and run['cost'].get('state_fit_returns')==3 and run['cost'].get('state_fitted_coefficient_scalar_outputs')==30 and run['new_training_physics_controls']==0 and run['new_unique_training_scalar_labels']==0 and run['RLS_updates']==0)
for seed in ['8101','8102','8103']:
 group=models[seed];fit=moments[seed]
 check(seed+'_all_four_models_and_rank5',set(group)=={'cold','oldlearned','IV1','newmatched'} and fit['samples']==2000 and fit['fit']['rank']==5)
 old=np.asarray(group['IV1']['coefficients'],dtype=np.float64)[:,4:8].tobytes();new=np.asarray(group['newmatched']['coefficients'],dtype=np.float64)[:,4:8].tobytes()
 check(seed+'_fixed_action8_bitwise',old==new and fit['fixed_action_float64_bytes_hex']==old.hex())
 check(seed+'_saved_parameter_fingerprints_frozen',all(m['parameter_fingerprint']==m['fingerprint_before_prediction'] for m in group.values()))
check('science_flags_false_and_no_control',all(run[key] is False for key in ['scientific_adoption','old_free_root_C4_validation','c4_scientific_validation','c4_contact_scientific_validation','c5_scientific_dependency_released','control_candidate_opened']))
with zipfile.ZipFile(out/'raw/source.zip') as z:
 check('source_zip_complete_closure',set(z.namelist())==set(run['source']['files']))
 for name,identity in run['source']['files'].items():
  data=z.read(name);check('archived_source_'+name,{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}==identity)
report={'status':'passed' if all(c['passed'] for c in checks) else 'failed','checks':checks,'payload':payload,'physics_calls':0,'fit_calls':0,'model_calls':0,'trace_decode_calls':0,'science_gate_reexecuted':False,'continuous_goal':'active','cumulative_controls':529345+run['cost'].get('total_control_attempts',0),'cumulative_substeps':2809018+run['cost'].get('confirmed_physics_substeps',0),'historical_RLS_scalar_updates':125652,'IV2_reused_scalar_label_uses':run['cost'].get('reused_state_fit_scalar_label_uses',0),'wall_seconds_before_report':time.perf_counter()-wall,'cpu_seconds_before_report':time.process_time()-cpu,'unmeasured_filesystem_IO':'unknown_not_zero'}
(out/'delivery_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
shutil.copyfile(Path(__file__).resolve(),out/'checks'/Path(__file__).name)
print(json.dumps({'status':report['status'],'checks':len(checks),'output':str(out),'experiment_status':run['status'],'stored_prediction_gate':metrics['iv2_prediction_gate_passed']}))
