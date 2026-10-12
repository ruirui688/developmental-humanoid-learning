"""Archive first IV2D records and inspect saved population, without new math."""
from pathlib import Path
import hashlib,json,shutil,zipfile,time
root=Path(__file__).resolve().parents[1]
src=root/'external/iv2d_saved_residual_first/raw'
out=root/'results/cpu_validation/2026-10-12_consistent_model_residual'
if (out/'delivery_checks.json').exists():raise ValueError('completed_delivery_refused')
if not (out/'checks/first_delivery_failure.json').exists():raise ValueError('archived_first_failure_required_for_finalization')
wall,cpu=time.perf_counter(),time.process_time();payload={}
for name in ['run.json','analysis.json','source.zip','first_stdout.log','first_stderr.log']:
 b=(out/'raw'/name).read_bytes();payload['raw/'+name]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
r=json.loads((out/'raw/run.json').read_bytes());a=json.loads((out/'raw/analysis.json').read_bytes());checks=[]
def check(name,value):checks.append({'name':name,'passed':bool(value)})
check('first_complete_frozen_source',r['status']=='completed' and r['first_failure'] is None and r['source']['commit']=='14088b6a877af05e7ff061ebc0ac011f44a796e8' and r['source']['clean_committed_bytes_verified'])
check('six_complete_training_slots',len(a['training_state_residuals'])==6 and all(t['status']=='completed' and t['error']['count']==2000 for t in a['training_state_residuals']))
check('sixty_complete_saved_groups',len(a['saved_endpoint_error_and_recursive_box'])==60 and all(t['status']=='completed' and t['q_error']['count']==t['planned_origins'] and len(t['saved_origin_active_indices'])==t['planned_origins'] and t['recursive_input_box']['points']==t['planned_recursive_inputs'] and t['original_RMSE_transcribed']['recomputed'] is False for t in a['saved_endpoint_error_and_recursive_box']))
check('three_complete_unique_native_H1',len(a['native_H1_unique_origin_box'])==3 and all(t['status']=='completed' and t['box']['points']==100 for t in a['native_H1_unique_origin_box']))
check('six_new_matmul_and_fixed_label_uses',r['cost']['state_matmul_returns']==6 and r['cost']['training_state_velocity_scalar_outputs']==24000 and r['cost']['reused_training_Y_scalar_uses']==24000)
check('full_saved_record_and_input_counts',r['cost']['saved_prediction_record_returns']==5772 and r['cost']['recursive_input_points']==249360 and r['cost']['recursive_box_scalar_uses']==997440 and r['cost']['native_H1_input_points']==300)
check('zero_new_physics_fit_predict_RLS_or_old_gate',all(r[k]==0 for k in ['new_physics_controls','new_physics_substeps','fit_attempts','model_predict_calls','RLS_updates','source_trace_reads','old_gate_recomputations','fresh_RMSE_recomputations']))
flags=['scientific_adoption','old_free_root_C4_validation','c4_scientific_validation','c4_contact_scientific_validation','c5_scientific_dependency_released','control_candidate_opened']
check('science_flags_remain_false',all(r[k] is False and a[k] is False for k in flags))
check('original_IV2_gate_transcribed_false',r['original_IV2_prediction_gate_transcribed'] is False)
with zipfile.ZipFile(out/'raw/source.zip') as z:
 check('source_zip_exact_closure',set(z.namelist())==set(r['source']['files']))
 for name,identity in r['source']['files'].items():
  b=z.read(name);check('source_'+name,{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}==identity)
report={'status':'passed' if all(c['passed'] for c in checks) else 'failed','first_delivery_failure_archive':'checks/first_delivery_failure.json','finalization_reason':'correct_saved_field_namespace_only_after_original_delivery_KeyError','checks':checks,'payload':payload,'new_math_calls':0,'physics_calls':0,'fit_calls':0,'model_calls':0,'trace_decode_calls':0,'science_gate_reexecuted':False,'continuous_goal':'active','cumulative_controls':535345,'cumulative_substeps':2815018,'historical_RLS_scalar_updates':125652,'wall_seconds_before_report':time.perf_counter()-wall,'cpu_seconds_before_report':time.process_time()-cpu,'unmeasured_filesystem_IO':'unknown_not_zero'}
(out/'delivery_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');shutil.copyfile(Path(__file__).resolve(),out/'checks'/Path(__file__).name)
print(json.dumps({'status':report['status'],'checks':len(checks),'output':str(out)}))
