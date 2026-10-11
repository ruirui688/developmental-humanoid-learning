"""Append exact requested diagnostics from saved summary, never reread formal raw."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
prefix = root/'external/elbow_body_20261011_summary_01'
wall, cpu = time.perf_counter(), time.process_time()
summary_path = Path(str(prefix)+'_summary.json')
summary_bytes = summary_path.read_bytes()
s = json.loads(summary_bytes)
rows = []
lines = ['', '## 补充精确表（仅读取已保存summary）', '',
    '以下是固定一次summary已有字段的算术整理，没有重新读取raw/audit或重新运行summary；q绝对范围由qref+原生输入qoffset范围计算。多关节遗漏/保护条件只为机制假设，没有因果采用结论。', '',
    '| seed | qref rad | cal qoffset min | cal qoffset max | cal q absolute min | cal q absolute max | cal v min | cal v max | learned q域外率 | learned v域外率 |',
    '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
def fmt(x):
    return f'{x:.17g}'
for seed in s['raw_recomputed_seed_details']:
    ref=seed['cold_start_and_frozen_parameters']['selection']['joint_position_rad']
    cal=seed['calibration_support']; cov=seed['evaluations']['learned_mpc']['state_coverage']
    first=seed['native_trajectory_diagnostics']['learned_mpc']['first_three_recorded_mpc_choices'][0]
    stop=seed['native_trajectory_diagnostics']['learned_mpc']['stop_native_transitions'][0]
    d=first['recorded_chosen_planner_decision']; end=stop['recorded_chosen_planner_decision']
    row={'seed':seed['seed'],'qref_rad':ref,'theta':seed['cold_start_and_frozen_parameters']['final_coefficients'],
        'calibration_qoffset_range_rad':cal['q_offset_envelope_rad'],
        'calibration_qabsolute_range_rad':[ref+x for x in cal['q_offset_envelope_rad']],
        'calibration_v_range_rad_s':cal['velocity_envelope_rad_s'],
        'learned_control_input_coverage':cov,
        'first_current_q_rad':first['q_before_rad'],'first_current_v_rad_s':first['v_before_rad_s'],
        'first_target_q_rad':first['target_q_rad'],'first_chosen_u_nm':first['requested_torque_nm'],
        'first_chosen_cost':d['cost'],'first_15_step_forecast_endpoint_q_rad':d['predicted_q'][-1],
        'first_15_step_forecast_endpoint_v_rad_s':d['predicted_v'][-1],
        'stop_step_index':stop['step_index'],'stop_current_q_rad':stop['q_before_rad'],
        'stop_current_v_rad_s':stop['v_before_rad_s'],'stop_predicted_next_q_rad':end['predicted_q'][0],
        'stop_predicted_next_v_rad_s':end['predicted_v'][0],'stop_actual_next_q_rad':stop['q_after_rad'],
        'stop_actual_next_v_rad_s':stop['v_after_rad_s'],'stop_target_q_rad':stop['target_q_rad'],
        'stop_chosen_u_nm':stop['requested_torque_nm'],'stop_chosen_cost':end['cost'],
        'forecast_origin':'Original collector chosen forecasts, replayed by first audit and retained in saved summary; no new forecasts.'}
    rows.append(row)
    values=[ref,*row['calibration_qoffset_range_rad'],*row['calibration_qabsolute_range_rad'],
            *row['calibration_v_range_rad_s'],cov['q_outside_fraction'],cov['v_outside_fraction']]
    lines.append('| '+str(seed['seed'])+' | '+' | '.join(fmt(x) for x in values)+' |')
lines += ['', '| seed | 首次current q | 首次current v | target q | chosen u | chosen cost | 15步预测末q | 15步预测末v |',
    '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for row in rows:
    keys=('first_current_q_rad','first_current_v_rad_s','first_target_q_rad','first_chosen_u_nm','first_chosen_cost',
          'first_15_step_forecast_endpoint_q_rad','first_15_step_forecast_endpoint_v_rad_s')
    lines.append('| '+str(row['seed'])+' | '+' | '.join(fmt(row[k]) for k in keys)+' |')
lines += ['', '| seed | stop112 current q | current v | predicted next q | predicted next v | actual next q | actual next v | target q | chosen u | chosen cost |',
    '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for row in rows:
    keys=('stop_current_q_rad','stop_current_v_rad_s','stop_predicted_next_q_rad','stop_predicted_next_v_rad_s',
          'stop_actual_next_q_rad','stop_actual_next_v_rad_s','stop_target_q_rad','stop_chosen_u_nm','stop_chosen_cost')
    lines.append('| '+str(row['seed'])+' | '+' | '.join(fmt(row[k]) for k in keys)+' |')
table_path=Path(str(prefix)+'_review_detail_tables.json')
source_path=Path(str(prefix)+'_detail_append_builder.py')
with source_path.open('xb') as stream:
    stream.write(Path(__file__).read_bytes())
record={'source_summary_path':str(summary_path),'source_summary_sha256':hashlib.sha256(summary_bytes).hexdigest(),
        'rows':rows,'formal_raw_audit_rereads':0,'summary_reexecutions':0,'new_model_predictions':0,
        'physical_calls':0,'updates':0,'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu}
with table_path.open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(record,stream,ensure_ascii=False,indent=2,allow_nan=False); stream.write('\n')
lines += ['', f"补充表路径 `{table_path.relative_to(root).as_posix()}` SHA256 `{hashlib.sha256(table_path.read_bytes()).hexdigest()}`。",
    f"补充生成源码 `{source_path.relative_to(root).as_posix()}` SHA256 `{hashlib.sha256(source_path.read_bytes()).hexdigest()}`。",
    f"补充整理wall={record['wall_seconds']} s，CPU={record['cpu_seconds']} s；scope为saved-summary读取/表构建/源码保存，JSON写盘之前。", '']
delivery=root/'external/elbow_body_20261011_summary_delivery.md'
with delivery.open('ab') as stream:
    stream.write(('\n'.join(lines)).encode())
print(json.dumps({'delivery':str(delivery),'sha256':hashlib.sha256(delivery.read_bytes()).hexdigest(),
    'detail_tables_sha256':hashlib.sha256(table_path.read_bytes()).hexdigest(),'wall':record['wall_seconds'],'cpu':record['cpu_seconds']}))
