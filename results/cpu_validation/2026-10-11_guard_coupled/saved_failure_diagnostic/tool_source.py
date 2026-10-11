"""Extract B saved forecasts and labels once; no new model or audit call."""
from pathlib import Path
import gzip
import hashlib
import json
import time

root=Path(__file__).resolve().parents[1]
source=root/'external/guard_coupled_20261011_first/trace.jsonl.gz'
output=root/'external/guard_coupled_20261011_failure_diagnostic_01'
output.mkdir(exist_ok=False)
wall,cpu=time.perf_counter(),time.process_time()
data=source.read_bytes();rows=[]
for line in gzip.decompress(data).splitlines():
 r=json.loads(line)
 if r['phase']!='control':continue
 p=r['predicted_next_qv']['coupled_guard'];d=r['planner_decision']
 rows.append({'seed':r['seed'],'source_transition_id':r['shared_transition_id'],
  'active_index':r['step_index']-100,'target_q':r['target_q'],
  'requested_nm':r['requested_torque'][:2],
  'begin_q':r['observation_before']['joint_position'][:2],
  'begin_v':r['observation_before']['joint_velocity'][:2],
  'saved_prediction_next_q':p[0],'saved_prediction_next_v':p[1],
  'measured_next_q':r['observation_after']['joint_position'][:2],
  'measured_next_v':r['observation_after']['joint_velocity'][:2],
  'saved_selected_horizon_last_q':d['predicted_q'][-1],
  'saved_selected_horizon_last_v':d['predicted_v'][-1],
  'study_abort':r['study_abort'],'executed_substeps':r['diagnostics']['executed_substeps']})
record={'scope':'Extracted all first B saved control decisions; descriptive only.',
 'trace_sha256':hashlib.sha256(data).hexdigest(),'trace_read_passes':1,
 'new_physics':0,'new_model_updates':0,'new_predictions':0,'audit_executions':0,
 'rows':rows,'claim_boundary':'No counterfactual, refit or new scientific gate.',
 'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu}
with (output/'saved_failed_controls.json').open('x',encoding='utf-8') as stream:
 json.dump(record,stream,indent=2);stream.write('\n')
(output/'tool_source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'output':str(output),'rows':len(rows),'sha256':hashlib.sha256((output/'saved_failed_controls.json').read_bytes()).hexdigest(),
 'wall_seconds':record['wall_seconds'],'cpu_seconds':record['cpu_seconds']}))
print(json.dumps([r for r in rows if r['seed']==0 and r['active_index']>=98],indent=2))
