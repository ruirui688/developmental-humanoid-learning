"""Read the saved G thin summary once for report fields; no metrics recomputation."""
import hashlib
import json
from pathlib import Path
import time
root=Path(__file__).resolve().parents[1]
out=root/'external/c4_g_report_projection_01.json'
assert not out.exists()
wall,cpu=time.perf_counter(),time.process_time()
data=(root/'external/guard_pd_tail_control_20261011_summary_01/summary.json').read_bytes()
s=json.loads(data)
episodes={e['trial_id']:e for e in s['episodes']}
rows=[]
for row in s['seeds']:
    for kind,ev in row['evaluations'].items():
        ep=episodes[f"seed{row['seed']}_{kind}"]
        rows.append({'seed':row['seed'],'kind':kind,'status':ev['status'],'eligible':ev['eligible'],
            'active_steps':ep['phase_budgets']['control']['control_steps'],
            'ranking_joint_rmse_rad':ev['tracking_rmse_rad'] if ev['eligible'] else None,
            'complete_score_endpoints':ev['complete_score_endpoints'],
            'planning_fallbacks':ev['planning_fallbacks'],'study_abort':ep['study_abort']})
report={'source_commit':s['source_commit'],'summary_sha256':hashlib.sha256(data).hexdigest(),
    'rows':rows,'outcomes':s['outcomes'],'budget':s['physics_budget'],
    'gates':{k:({f:v[f] for f in ('evaluated','passed')} if isinstance(v,dict) else v) for k,v in s['final_gates'].items()},
    'prediction_fees':s['paid_prediction_accounting'],'tail_fees':s['paid_tail_request_accounting'],
    'collector_seconds':s['collector_seconds'],'audit_execution':s['first_audit_execution'],
    'projection_fee':{'opens':1,'binary_bytes':len(data),'wall_seconds':time.perf_counter()-wall,
        'cpu_seconds':time.process_time()-cpu,'new_statistics_predictions_updates_physics':0}}
out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
