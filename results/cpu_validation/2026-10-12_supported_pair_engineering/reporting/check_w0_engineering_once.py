"""Independent stdlib check of the new W0 engineering record; no model calls."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

parser=argparse.ArgumentParser()
parser.add_argument('--raw',required=True)
parser.add_argument('--expected-source-commit',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
root,output=Path(args.raw),Path(args.output)
if output.exists():
    raise SystemExit('first W0 verification exists; no repeat')
output.mkdir(parents=True)
wall,cpu=time.perf_counter(),time.process_time()
reads=byte_count=parses=0
checks=[]
def read(name):
    global reads,byte_count
    data=(root/name).read_bytes(); reads+=1; byte_count+=len(data)
    return data
def parsed(data):
    global parses
    parses+=1
    return json.loads(data)
def check(name,passed,detail=None):
    checks.append({'check':name,'passed':bool(passed),'detail':detail})
manifest=parsed(read('manifest.json'))
payload={name:read(name) for name in manifest['files']}
check('payload_bytes_and_hashes',all(len(payload[name])==pin['bytes'] and
      hashlib.sha256(payload[name]).hexdigest()==pin['sha256'] for name,pin in manifest['files'].items()))
run,metrics=parsed(payload['run.json']),parsed(payload['metrics.json'])
plain=gzip.decompress(payload['trace.jsonl.gz'])
rows=[parsed(line) for line in plain.splitlines() if line]
check('fixed_engineering_identity',run['seed']==7300 and run['source']['commit']==args.expected_source_commit
      and run['self_check'] is False and run['planned_calls']==300 and run['planned_substeps']==3000 and
      (run['source']['clean_committed_bytes_verified'] is True or
       run['status']=='failed' and run['cost']['control_call_attempts']==0))
check('zero_learning_and_scientific_flags',all(run['cost'].get(key)==0 for key in
      ('RLS_updates','body_model_fits','body_model_restorations','MPC_calls','teacher_calls')) and
      all(run.get(key) is False and metrics.get(key) is False for key in
      ('scientific_adoption','old_free_root_C4_validation','c4_scientific_validation','c5_scientific_dependency_released')))
returned=[row for row in rows if row.get('returned') is True]
confirmed=sum((row.get('diagnostics') or {}).get('executed_substeps',0) if row.get('returned') else
              row.get('confirmed_completed_substeps',0) for row in rows)
check('paid_calls_substeps_and_order',len(rows)==run['cost']['control_call_attempts'] and
      len(returned)==run['cost']['control_call_returns'] and confirmed==run['cost']['confirmed_physics_substeps']
      and len(rows)<=300 and confirmed<=3000 and
      all(row['control_index']==i and row['phase']==('prefix' if i<100 else 'active') and
          row['phase_index']==(i if i<100 else i-100) for i,row in enumerate(rows)))
check('requests_and_shared_final_authority',all(len(row['requested_torque'])==8 and
      all(math.isfinite(x) and abs(x)<=.5 for x in row['requested_torque']) and
      row['requested_torque'][2:]==[0.]*6 and
      (row['phase']!='prefix' or row['requested_torque']==[0.]*8) for row in rows))
samples=[]; complete_telemetry=True
expected_root=(run.get('support') or {}).get('installation')
native_shapes={'joint_position':8,'joint_velocity':8,'imu_gyro':3,'imu_acceleration':3,
               'actuator_torque':8,'previous_command':8}
def finite_vector(value,size):
    return isinstance(value,list) and len(value)==size and all(
        isinstance(x,(int,float)) and math.isfinite(x) for x in value)
for row in returned:
    diagnostic=row['diagnostics']; interval=diagnostic.get('substep_native_and_contact_records',[])
    complete_telemetry &= len(interval)==diagnostic['executed_substeps']
    for sample in interval:
        samples.append(sample)
        vectors=(sample.get('actual_actuator_torque8',[]),sample.get('applied_command8',[]))
        complete_telemetry &= all(finite_vector(vector,8) for vector in vectors)
        complete_telemetry &= sample['physics_step']==len(samples)
        complete_telemetry &= isinstance(sample.get('time'),(int,float)) and math.isfinite(sample['time'])
        complete_telemetry &= all(finite_vector(sample.get('observation',{}).get(name),size)
                                  for name,size in native_shapes.items())
        complete_telemetry &= all(isinstance(pair.get(key),(int,float)) and math.isfinite(pair[key])
                                  for pair in sample.get('floor_contacts',[])
                                  for key in ('normal_force_n','distance_m'))
        if expected_root:
            complete_telemetry &= sample['diagnostics']['root_position']==expected_root['fixed_torso_world_position']
            complete_telemetry &= sample['diagnostics']['root_quaternion']==expected_root['fixed_torso_world_quaternion']
check('returned_substep_effort_and_fixed_root_evidence',complete_telemetry)
full=(len(rows)==300 and len(returned)==300 and confirmed==3000 and complete_telemetry and
      all(row.get('environment_terminated') is False and
      row.get('study_abort') is None and row['diagnostics']['executed_substeps']==10 for row in rows))
contact=False
for row in returned:
    if row['phase']!='prefix' or not 80<=row['phase_index']<100:
        continue
    for sample in row['diagnostics'].get('substep_native_and_contact_records',[]):
        for pair in sample.get('floor_contacts',[]):
            names=pair.get('geom_names',[]); force=pair.get('normal_force_n')
            if ('floor' in names and any(x in names for x in ('left_upper_arm_geom','left_forearm_geom')) and
                    isinstance(force,(int,float)) and math.isfinite(force) and force>0):
                contact=True
windows=[]; metric_calculations=0; window_passes=[]
for index,(lower,upper) in enumerate(((80,100),(180,200))):
    selected=[row for row in returned if row['phase']=='active' and lower<=row['phase_index']<upper]
    available=full and len(selected)==20 and all(finite_vector(row.get('target_error_rad'),2)
                                              for row in selected)
    recorded=metrics['last20_post_step_windows'][index]
    check('window_population_'+str(index),recorded['observed_count']==len(selected) and
          recorded['available']==available)
    if available:
        values=[sum(abs(row['observation_after']['joint_position'][axis]-row['current_target_q2'][axis])
                    for row in selected)/20 for axis in range(2)]
        windows.append(values); metric_calculations+=2
        check('new_engineering_MAE_'+str(index),finite_vector(recorded['per_axis_mae_rad'],2) and all(
              math.isclose(recorded['per_axis_mae_rad'][axis],values[axis],rel_tol=1e-12,abs_tol=1e-15)
              for axis in range(2)),{'recomputed_mae_rad':values})
        window_passes.append(all(value<=.01 for value in values))
    else:
        windows.append(None); window_passes.append(False)
        check('unavailable_window_'+str(index),recorded['per_axis_mae_rad'] is None)
qualified=(full and contact and all(window_passes) and run.get('failure') is None and
           metrics.get('collector_failed') is not True)
check('frozen_engineering_qualification',metrics['full_100_prefix_200_active']==full and
      metrics['fixed_prefix_last20_left_arm_positive_floor_contact']==contact and
      metrics['engineering_qualification_passed']==qualified and run['engineering_qualification_passed']==qualified)
self_bytes=Path(__file__).read_bytes(); reads+=1; byte_count+=len(self_bytes)
report={'checks':checks,'failed_checks':sum(not item['passed'] for item in checks),'records':len(rows),
        'confirmed_substeps':confirmed,'full':full,'contact':contact,'independent_mae_rad':windows,
        'engineering_qualification_passed':qualified,'model_calls':0,'physics_calls':0,'RLS_updates':0,
        'new_engineering_MAE_recalculations':metric_calculations,'new_engineering_gate_verifications':1,
        'old_scientific_metric_recalculations':0,'cost':{'file_reads':reads,'read_bytes':byte_count,
        'json_parses':parses,'decompressed_bytes':len(plain),'wall_seconds':time.perf_counter()-wall,
        'cpu_seconds':time.process_time()-cpu}}
(output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
(output/'checker.py').write_bytes(self_bytes)
print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
raise SystemExit(bool(report['failed_checks']))
