"""One-read standard-library summary of recorded pair development and first audit.

No simulator/project import, RLS replay, new prediction, fit, audit reexecution,
holdout access or physical call. Read and hash each original once in memory.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

COMMIT = '884188416b982ad03c0b3ba6f94999e162ddf98f'
AUDIT_SHA = 'bb717cd064af534a84a4b8fac43e80c16bd59220392d9aaeedc27feee1614456'
SEEDS = (0, 1, 2)
KINDS = ('calibration', 'prediction_low', 'prediction_full', 'nominal_mpc',
         'diagonal_mpc', 'coupled_mpc', 'combined_pd', 'zero_torque')
DEPENDENT = ('prediction_low', 'prediction_full', 'diagonal_mpc', 'coupled_mpc')
PHASES = ('prefix', 'calibration', 'prediction', 'control')
JOINTS = ('left_shoulder', 'left_elbow', 'right_shoulder', 'right_elbow',
          'left_hip', 'left_knee', 'right_hip', 'right_knee')
EFFORT = ('requested_absolute_nm_s', 'requested_squared_nm2_s',
          'actual_absolute_nm_s', 'actual_squared_nm2_s')
DT = .002


def sha(data):
    return hashlib.sha256(data).hexdigest()


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def paired_rmse(errors):
    if not errors:
        return None
    per_axis = [math.sqrt(sum(e[i]**2 for e in errors)/len(errors)) for i in range(2)]
    return {'joint': math.sqrt(sum(sum(x*x for x in e) for e in errors)/(2*len(errors))),
            'per_axis': per_axis, 'complete_endpoints': len(errors)}


def pulse(active):
    slot = active % 20
    return 1 if slot < 5 else -1 if 10 <= slot < 15 else 0


def calibration_command(active, directions):
    if type(active) is not int or not 0 <= active < 400:
        raise ValueError('calibration active index outside [0,400)')
    block = active // 20
    amplitude = (.125, .25, .375, .5, .25)[block % 5]
    shape = (1, 0) if block < 5 else (0, 1) if block < 10 else (1, 1) if block < 15 else (1, -1)
    return [directions[i]*shape[i]*amplitude*pulse(active) for i in range(2)]


def add_effort(rows):
    result = {key: [0., 0.] for key in EFFORT}
    screened = [0]*8
    returned = 0
    for row in rows:
        n = row['diagnostics']['executed_substeps']
        history = row['diagnostics']['applied_torque_history']
        returned += n
        for i, u in enumerate(row['requested_torque'][:2]):
            result[EFFORT[0]][i] += abs(u)*n*DT
            result[EFFORT[1]][i] += u*u*n*DT
            result[EFFORT[2]][i] += sum(abs(a[i]) for a in history)*DT
            result[EFFORT[3]][i] += sum(a[i]*a[i] for a in history)*DT
        for i in range(8):
            screened[i] += sum(a[i] != row['requested_torque'][i] for a in history)
    return {'per_axis': result, 'combined': {k: sum(v) for k, v in result.items()},
            'permission_screened_substeps_native8': screened, 'physics_substeps': returned}


def triggers(q, v, qref):
    result = []
    for i in range(2):
        if abs(q[i]-qref[i]) >= .12:
            result.append({'joint_index': i, 'signal': 'absolute_q_minus_qref_rad'})
        if abs(v[i]) >= 1.:
            result.append({'joint_index': i, 'signal': 'absolute_velocity_rad_s'})
    return result


def step_detail(row, qref):
    before, after, d = row['observation_before'], row['observation_after'], row['diagnostics']
    active = row['step_index']-100
    return {'step_index': row['step_index'], 'active_index_zero_based': active,
            'active_call_one_based': active+1, 'block_zero_based': active//20,
            'slot_zero_based': active % 20, 'pulse_sign': pulse(active),
            'known_request_native8': row['requested_torque'],
            'before_q_native8': before['joint_position'], 'before_v_native8': before['joint_velocity'],
            'after_q_native8': after['joint_position'], 'after_v_native8': after['joint_velocity'],
            'q_minus_qref': [after['joint_position'][i]-qref[i] for i in range(2)],
            'before_torque_feedback_native8': before['actuator_torque'],
            'after_torque_feedback_native8': after['actuator_torque'],
            'executed_substeps': d['executed_substeps'],
            'actual_history_native8': d['applied_torque_history'],
            'permission_screened_substeps_native8': add_effort([row])['permission_screened_substeps_native8'],
            'study_abort': row['study_abort'], 'ground_force_peak_n': d['peak_substep_ground_normal_force'],
            'kinetic_energy_peak_j': d['peak_substep_kinetic_energy']}


def tracking(rows):
    eligible = [r for r in rows if r['target_q'] is not None and r['diagnostics']['executed_substeps'] == 10]
    errors = [[r['observation_after']['joint_position'][i]-r['target_q'][i] for i in range(2)] for r in eligible]
    segments = []
    for start, end in ((0, 99), (100, 199)):
        segment = [r for r in eligible if start <= r['step_index']-100 <= end]
        tail = [r for r in eligible if end-19 <= r['step_index']-100 <= end]
        def report(part):
            values = [[r['observation_after']['joint_position'][i]-r['target_q'][i] for i in range(2)] for r in part]
            return {'returned_complete_endpoints': len(part), 'rmse': paired_rmse(values),
                    'signed_mean_error': None if not values else [sum(e[i] for e in values)/len(values) for i in range(2)]}
        segments.append({'active_window': [start, end], 'segment': report(segment),
                         'planned_tail_window': [end-19, end], 'tail': report(tail),
                         'missing_segment_endpoints': 100-len(segment), 'missing_tail_endpoints': 20-len(tail)})
    return {'rmse': paired_rmse(errors), 'target_segments': segments}


class Checks:
    def __init__(self):
        self.count, self.failures, self.maximum_difference = 0, [], 0.

    def check(self, condition, location):
        self.count += 1
        if not condition:
            self.failures.append(location)

    def compare(self, expected, actual, location):
        if isinstance(expected, dict):
            self.check(isinstance(actual, dict), location+'/dict')
            if isinstance(actual, dict):
                for k, value in expected.items():
                    self.check(k in actual, location+'/'+k+'/present')
                    if k in actual:
                        self.compare(value, actual[k], location+'/'+k)
        elif isinstance(expected, list):
            self.check(isinstance(actual, list) and len(expected) == len(actual), location+'/list')
            if isinstance(actual, list) and len(expected) == len(actual):
                for i, (a, b) in enumerate(zip(expected, actual)):
                    self.compare(a, b, location+'/'+str(i))
        elif finite(expected) and finite(actual):
            difference = abs(expected-actual)
            self.maximum_difference = max(self.maximum_difference, difference)
            self.check(difference <= 1e-10+1e-10*abs(expected), location)
        else:
            self.check(expected == actual, location)


def xml_mapping(data):
    root = ET.fromstring(data)
    joint_map, qadr, dadr = {}, 0, 0
    for node in root.find('worldbody').iter():
        if node.tag == 'freejoint':
            qadr += 7
            dadr += 6
        elif node.tag == 'joint':
            kind = node.get('type', 'hinge')
            joint_map[node.get('name')] = {'qpos_index': qadr, 'qvel_index': dadr,
                'range_rad': [math.radians(float(x)) for x in node.get('range').split()]}
            qadr += 4 if kind == 'ball' else 1
            dadr += 3 if kind == 'ball' else 1
    return [joint_map[name] for name in JOINTS]


def review(archive, audit_path, git_root):
    wall, cpu = time.perf_counter(), time.process_time()
    checks = Checks()
    archive, audit_path, git_root = Path(archive), Path(audit_path), Path(git_root)
    names = ('manifest.json', 'metadata.json', 'episodes.json', 'seed_results.json', 'trace.jsonl.gz', 'source_snapshot.zip')
    data = {name: (archive/name).read_bytes() for name in names}
    audit_bytes = audit_path.read_bytes()
    hashes = {name: sha(value) for name, value in data.items()}
    hashes['first_audit.json'] = sha(audit_bytes)
    manifest, metadata, episodes, seeds = [json.loads(data[n]) for n in names[:4]]
    audit = json.loads(audit_bytes)
    checks.compare(AUDIT_SHA, hashes['first_audit.json'], 'first_audit_exact_sha')
    checks.compare(0, audit['failed'], 'first_audit_zero_failures')
    checks.compare(COMMIT, metadata['source_commit'], 'formal_commit')
    checks.compare(False, metadata['source_dirty'], 'formal_clean')
    checks.compare('', metadata['source_status'], 'formal_source_status')
    checks.compare(False, metadata['synthetic'], 'real_cpu_archive')
    checks.compare(None, metadata['gpu'], 'cpu_only')
    checks.compare(True, metadata['complete'], 'archive_complete')
    checks.compare(list(SEEDS), metadata['seeds'], 'development_seed_bank')
    checks.compare([0, 1], metadata['joint_indices'], 'native_pair_indices')
    checks.compare(8, metadata['native_joint_count'], 'native_eight_dimensions')
    checks.compare(set(names)-{'manifest.json'}, set(manifest), 'manifest_exact_files')
    for name, expected in manifest.items():
        checks.compare(expected, hashes[name], 'manifest/'+name)
    source_hashes = {}
    with zipfile.ZipFile(io.BytesIO(data['source_snapshot.zip'])) as z:
        checks.check(len(z.namelist()) == len(set(z.namelist())), 'source_zip_unique_names')
        checks.compare(set(metadata['source_sha256']), set(z.namelist()), 'source_zip_exact_members')
        for name in z.namelist():
            member = z.read(name)
            source_hashes[name] = sha(member)
            checks.compare(metadata['source_sha256'][name], source_hashes[name], 'source_zip/'+name)
            committed = subprocess.check_output(['git', 'show', COMMIT+':'+name], cwd=git_root)
            checks.compare(sha(committed), source_hashes[name], 'git_blob/'+name)
        native_map = xml_mapping(z.read('src/developmental_physics/assets/ground_body.xml'))
    raw = [json.loads(line) for line in gzip.decompress(data['trace.jsonl.gz']).decode('utf-8').splitlines() if line]
    grouped = defaultdict(list)
    for row in raw:
        grouped[row['trial_id']].append(row)
    by_seed = {s['seed']: s for s in seeds}
    checks.compare(list(SEEDS), sorted(by_seed), 'seed_results_bank')
    checks.compare([f'seed{s}_{k}' for s in SEEDS for k in KINDS], [e['trial_id'] for e in episodes], 'episode_order')
    checks.compare(24, len(episodes), 'episode_count')
    summaries, stops, committed_per_model = [], [], defaultdict(int)
    for episode in episodes:
        tid, seed, kind = episode['trial_id'], episode['seed'], episode['kind']
        rows, sr = grouped.get(tid, []), by_seed[seed]
        ev = sr['evaluations'][kind]
        if episode['status'] == 'blocked':
            checks.check(kind in DEPENDENT, tid+'/allowed_dependency')
            checks.compare({'type': 'DependencyBlocked', 'dependencies': [f'seed{seed}_calibration']}, episode['reason'], tid+'/dependency')
            checks.compare(0, len(rows), tid+'/no_raw_rows')
            checks.compare({'control_calls_attempted': 0, 'control_steps': 0, 'physics_steps': 0}, episode, tid+'/blocked_zero_budget')
            summaries.append({'trial_id': tid, 'status': 'blocked', 'reason': episode['reason'], 'evaluated': False})
            continue
        qref = sr['reference_q']
        checks.compare(list(range(len(rows))), [r['step_index'] for r in rows], tid+'/contiguous_steps')
        checks.compare(len(rows), episode['control_calls_attempted'], tid+'/raw_vs_attempted')
        checks.compare(len(rows), episode['control_steps'], tid+'/raw_vs_returned')
        checks.compare(sum(r['diagnostics']['executed_substeps'] for r in rows), episode['physics_steps'], tid+'/raw_vs_physics')
        checks.compare(None, episode['collector_exception'], tid+'/no_exception')
        checks.compare(None, episode['trace_write_failure'], tid+'/no_trace_failure')
        checks.compare(0, episode['unreturned_physics_steps'], tid+'/no_unreturned_paid_steps')
        phase_rows = {p: [r for r in rows if r['phase'] == p] for p in PHASES}
        phase_effort = {p: add_effort(pr) for p, pr in phase_rows.items()}
        for phase, pr in phase_rows.items():
            checks.compare({'control_calls_attempted': len(pr), 'control_steps': len(pr), 'physics_steps': phase_effort[phase]['physics_substeps']},
                           episode['phase_budgets'][phase], tid+'/phase_budget/'+phase)
            checks.compare(phase_effort[phase]['per_axis'], ev['phase_effort'][phase], tid+'/effort/'+phase)
        prediction_errors = defaultdict(lambda: {'q': [], 'v': []})
        row_commits = Counter()
        for row_index, row in enumerate(rows):
            checks.compare(tid+':'+str(row_index), row['shared_transition_id'], tid+'/transition_id/'+str(row_index))
            checks.compare([0, 1], row['joint_indices'], tid+'/native_pair/'+str(row_index))
            u = row['requested_torque']
            checks.check(len(u) == 8 and all(finite(x) and abs(x) <= .5 for x in u) and all(x == 0. for x in u[2:]), tid+'/request8/'+str(row_index))
            for label in ('observation_before', 'observation_after'):
                obs = row[label]
                for key, size in (('joint_position',8), ('joint_velocity',8), ('actuator_torque',8), ('previous_command',8), ('imu_gyro',3), ('imu_acceleration',3)):
                    checks.check(len(obs[key]) == size and all(finite(x) for x in obs[key]), tid+'/'+label+'/'+key+'/'+str(row_index))
            if row_index:
                checks.compare(rows[row_index-1]['observation_after'], row['observation_before'], tid+'/observation_continuity/'+str(row_index))
            for i, mapping in enumerate(native_map):
                checks.compare(row['qpos'][mapping['qpos_index']], row['observation_after']['joint_position'][i], tid+'/qpos_encoder/'+str(row_index)+'/'+str(i))
                checks.compare(row['qvel'][mapping['qvel_index']], row['observation_after']['joint_velocity'][i], tid+'/qvel_encoder/'+str(row_index)+'/'+str(i))
            n, history = row['diagnostics']['executed_substeps'], row['diagnostics']['applied_torque_history']
            checks.check(type(n) is int and 0 <= n <= 10 and len(history) == n, tid+'/substep_history/'+str(row_index))
            checks.check(all(len(a) == 8 and all(finite(x) and abs(x) <= .5 for x in a) for a in history), tid+'/actual8/'+str(row_index))
            if row['phase'] == 'prefix':
                checks.compare([0.]*8, u, tid+'/zero_prefix/'+str(row_index))
                checks.compare(None, row['model_update'], tid+'/prefix_no_update/'+str(row_index))
                continue
            if kind == 'calibration':
                checks.compare(calibration_command(row_index-100, sr['direction']), u[:2], tid+'/fixed_pulse/'+str(row_index))
            expected_triggers = triggers(row['observation_after']['joint_position'], row['observation_after']['joint_velocity'], qref)
            checks.compare(expected_triggers, [] if row['study_abort'] is None else row['study_abort']['triggers'], tid+'/study_abort/'+str(row_index))
            if n == 10:
                for name, recorded in row['predicted_next_qv'].items():
                    for metric, target in (('q',0), ('v',1)):
                        key = 'joint_position' if metric == 'q' else 'joint_velocity'
                        prediction_errors[name][metric].append([row['observation_after'][key][i]-recorded[target][i] for i in range(2)])
                if kind == 'calibration':
                    for name, update in row['model_update'].items():
                        checks.compare(2, update['committed_scalar_updates'], tid+'/committed_heads/'+str(row_index)+'/'+name)
                        checks.compare(True, update['updated'], tid+'/update_true/'+str(row_index)+'/'+name)
                        row_commits[name] += update['committed_scalar_updates']
            else:
                checks.check(kind != 'calibration' or row['model_update']['updated'] is False, tid+'/partial_no_update/'+str(row_index))
        for name, errors in prediction_errors.items():
            checks.compare(paired_rmse(errors['q']), ev['position_prediction_rmse'][name], tid+'/recorded_q_residual/'+name)
            checks.compare(paired_rmse(errors['v']), ev['velocity_prediction_rmse'][name], tid+'/recorded_v_residual/'+name)
        tracking_metrics = tracking(rows)
        checks.compare(tracking_metrics['rmse'], ev['tracking_rmse'], tid+'/tracking')
        active_rows = [r for r in rows if r['phase'] != 'prefix']
        final = active_rows[-1] if active_rows else None
        if episode['study_abort'] is not None:
            checks.compare(final['study_abort'], episode['study_abort'], tid+'/stop_endpoint')
            stop = {'trial_id': tid, 'seed': seed, 'kind': kind, 'endpoint': step_detail(final,qref),
                    'previous_five_active_steps': [step_detail(r,qref) for r in active_rows[-6:-1]],
                    'last_five_including_stop': [step_detail(r,qref) for r in active_rows[-5:]]}
            stops.append(stop)
        blocks = []
        if kind == 'calibration':
            for b in range(20):
                br = [r for r in active_rows if (r['step_index']-100)//20 == b]
                blocks.append({'block_zero_based': b, 'active_window_planned': [20*b,20*b+19],
                    'amplitude_nm': (.125,.25,.375,.5,.25)[b%5],
                    'shape': 'shoulder_only' if b<5 else 'elbow_only' if b<10 else 'same_direction' if b<15 else 'opposite_direction',
                    'active_returned_steps': len(br), 'planned_steps':20,
                    'pulse_slots': dict(Counter('positive' if pulse(r['step_index']-100)>0 else 'negative' if pulse(r['step_index']-100)<0 else 'zero' for r in br)),
                    'effort': add_effort(br),
                    'endpoint_native8_speed_peak': [max((abs(r['observation_after']['joint_velocity'][i]) for r in br),default=0.) for i in range(8)],
                    'first': None if not br else step_detail(br[0],qref), 'last': None if not br else step_detail(br[-1],qref)})
            for name in ('diagonal','coupled'):
                snapshot = sr['calibration_models'][name]
                checks.compare(row_commits[name], snapshot['scalar_update_count'], tid+'/snapshot_committed/'+name)
                checks.compare(row_commits[name]//2, snapshot['vector_update_count'], tid+'/snapshot_vectors/'+name)
                checks.compare([snapshot['vector_update_count']]*2, snapshot['output_update_counts'], tid+'/snapshot_heads/'+name)
                committed_per_model[name] += row_commits[name]
            checks.compare(sum(row_commits.values()), sr['calibration_scalar_updates'], tid+'/seed_scalar')
            checks.compare(sum(row_commits.values())//2, sr['calibration_vector_updates'], tid+'/seed_vector')
            checks.compare(False, sr['calibration_completed'], tid+'/calibration_not_complete')
            checks.compare({}, sr['learned_models'], tid+'/failed_models_not_published')
        native_ranges = {key: [[min(r[label][key][i] for r in rows for label in ('observation_before','observation_after')),
                               max(r[label][key][i] for r in rows for label in ('observation_before','observation_after'))] for i in range(8)]
                         for key in ('joint_position','joint_velocity')}
        summary = {'trial_id':tid, 'seed':seed, 'kind':kind, 'status':episode['status'], 'completed':episode['completed'],
            'budget': {k:episode[k] for k in ('control_calls_attempted','control_steps','physics_steps')},
            'phase_effort':phase_effort, 'reference_q':qref, 'directions':sr['direction'],
            'tracking':tracking_metrics, 'prediction_residuals_from_recorded_predictions':{name:{k:paired_rmse(value) for k,value in errs.items()} for name,errs in prediction_errors.items()},
            'calibration_blocks':blocks, 'row_committed_scalar_updates':dict(row_commits), 'native8_state_ranges':native_ranges,
            'final_active_endpoint':None if final is None else step_detail(final,qref),
            'full_tracking_evidence':bool(episode['completed'] and len(active_rows)==200 and kind not in ('calibration','prediction_low','prediction_full')),
            'stopped_fragment_is_method_advantage':False,
            'recorded_planning_accounting':ev['planning_accounting'], 'planner_fallbacks':ev['planner_fallbacks']}
        summaries.append(summary)
    budget = {k:sum(e[k] for e in episodes) for k in ('control_calls_attempted','control_steps','physics_steps')}
    budget.update(model_updates=sum(s['calibration_scalar_updates'] for s in seeds), vector_model_updates=sum(s['calibration_vector_updates'] for s in seeds))
    for k,value in budget.items():
        checks.compare(value, metadata[k], 'metadata_budget/'+k)
        checks.compare(value, audit['archive']['budget'][k], 'first_audit_budget/'+k)
    statuses = dict(Counter(e['status'] for e in episodes))
    for k,status in (('completed_trials','completed'),('terminated_trials','terminated'),('exception_trials','exception'),('blocked_trials','blocked')):
        checks.compare(statuses.get(status,0), metadata[k], 'metadata_status/'+status)
    audit_hashes = audit['archive']['input_hashes']
    for name,value in hashes.items():
        if name in audit_hashes:
            checks.compare(value,audit_hashes[name],'first_audit_input/'+name)
    for s in seeds:
        prefix = grouped[f"seed{s['seed']}_calibration"][99]['observation_after']
        for kind in ('nominal_mpc','combined_pd','zero_torque'):
            checks.compare(prefix,grouped[f"seed{s['seed']}_{kind}"][99]['observation_after'],f"seed{s['seed']}/paired_prefix/{kind}")
    gates = audit['final_gates']
    for name in ('diagonal_contribution','coupled_contribution','coupled_increment'):
        checks.compare(False,gates[name]['passed'],'first_audit_gate/'+name)
    for name,gate in gates['combined_pd_comparison'].items():
        checks.compare(False,gate['passed'],'first_audit_pd_gate/'+name)
    checks.compare(False,gates['complete_matrix'],'first_audit_complete_matrix')
    return {'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'checks':checks.count,'failed':len(checks.failures),'violations':checks.failures,'maximum_difference':checks.maximum_difference,
        'input_hashes':hashes,'source_zip_members_sha256':source_hashes,'formal_source_commit':metadata['source_commit'],
        'native_joint_order':list(JOINTS),'native_joint_mapping_from_asset':native_map,
        'raw_returned_rows':len(raw),'independently_recomputed_budget':budget,'statuses':statuses,
        'committed_scalar_updates_by_model':dict(committed_per_model),
        'cumulative_actual_budget':{'control_calls':221663+budget['control_steps'],'physics_substeps':2216630+budget['physics_steps'],'scalar_updates':10800+budget['model_updates']},
        'episodes':summaries,'stops':stops,'seed_results_recorded':seeds,
        'first_audit_reference':{'path':str(audit_path),'sha256':sha(audit_bytes),'checks':audit['checks'],'failed':audit['failed'],
            'maximum_difference':audit['maximum_recomputation_difference'],'execution':audit['execution']},
        'first_audit_scientific_gates':gates,
        'first_audit_derived_metrics':audit['archive']['seeds'],
        'claim_boundary':'Calibration failed before model publication; prediction and learned control blocked. All scientific gates fail eligibility; coupling contribution was not evaluated. No causal assertion about pulse, passive state, learning, safety or locomotion.',
        'collection_execution':{k:metadata.get(k) for k in ('wall_seconds','cpu_seconds','mujoco_version','python_version','dependencies')},
        'execution':{'wall_seconds':time.perf_counter()-wall,'cpu_seconds':time.process_time()-cpu,
            'physical_calls':0,'physics_substeps':0,'model_updates':0,'new_predictions':0,'audit_reexecutions':0,
            'reads_per_original_file':1,'third_party_imports':[],'python':sys.version}}
