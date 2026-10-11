"""Independent frozen shoulder-final review of raw logs and first audit.

Do not execute before root authorizes the completed formal raw/audit paths.
Standard library only: no project imports, simulator, predictions, RLS replay,
fitting, premature holdout reads or new interactions. Recompute residual metrics from
recorded predictions, calibration/control input coverage, actual effort,
stops/budgets/update counts and frozen model/PD/full-matrix gates. Preserve all
audited multi-step/risk/tail details, exact source bytes, input hashes and timing.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sys
import time

SEEDS = [20, 21, 22]
RESET_SEEDS = {20: 1822509288, 21: 2605417566, 22: 1950464737}
KINDS = ('calibration', 'prediction_low', 'prediction_full',
         'nominal_mpc', 'learned_mpc', 'tuned_pd', 'zero_torque')
CONTROLS = KINDS[3:]
MODEL_REQUIRED = KINDS[:5]
SCHEDULES = ('short',)
PHASES = ('prefix', 'calibration', 'prediction', 'control')
EFFORT = ('requested_absolute_nm_s', 'requested_squared_nm2_s',
          'actual_absolute_nm_s', 'actual_squared_nm2_s')
PROTOCOL = 'docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md'
PHYSICS_DT = .002


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def rmse(values):
    if not values:
        return None
    scale = max(abs(x) for x in values)
    return 0. if scale == 0. else scale*math.sqrt(sum((x/scale)**2 for x in values)/len(values))


def mean(values):
    return sum(values)/3 if len(values) == 3 and all(finite(v) for v in values) else None


def ratio_change(new, old):
    return None if old == 0. else new/old-1.


class Checks:
    def __init__(self):
        self.count = 0
        self.failures = []
        self.maximum_difference = 0.

    def check(self, condition, location):
        self.count += 1
        if not condition:
            self.failures.append(location)

    def compare(self, expected, actual, location):
        if isinstance(expected, dict):
            self.check(isinstance(actual, dict), location+'/dict')
            if isinstance(actual, dict):
                for key, value in expected.items():
                    self.check(key in actual, location+'/'+key+'/present')
                    if key in actual:
                        self.compare(value, actual[key], location+'/'+key)
        elif isinstance(expected, list):
            self.check(isinstance(actual, list) and len(actual) == len(expected), location+'/list')
            if isinstance(actual, list) and len(actual) == len(expected):
                for i, (left, right) in enumerate(zip(expected, actual)):
                    self.compare(left, right, location+'/'+str(i))
        elif finite(expected) and finite(actual):
            diff = abs(expected-actual)
            self.maximum_difference = max(self.maximum_difference, diff)
            # Counters and gate decisions compare exactly; only independently
            # summed diagnostic floats allow roundoff, never gate thresholds.
            self.check(expected == actual if type(expected) is int else diff <= 1e-12+1e-10*abs(expected), location)
        else:
            self.check(type(expected) is type(actual) and expected == actual, location)


def require_final(path):
    m = load_json(Path(path)/'metadata.json')
    if (m.get('suite') != 'shoulder_final' or m.get('split') != 'final_holdout' or m.get('seeds') != SEEDS
            or any(type(s) is not int for s in m.get('seeds', []))
            or m.get('pose') != 'supine' or type(m.get('joint_index')) is not int or m['joint_index'] != 0
            or m.get('calibration_dose') != 'old' or m.get('model_structure') != 'hinge5'
            or m.get('structures') != ['hinge5'] or m.get('integration') != 'endpoint_euler'
            or m.get('calibration_schedule') != 'short' or m.get('calibration_schedules') != list(SCHEDULES)
            or m.get('pd_gains') != {'kp': 64., 'kd': 0.} or m.get('protocol', {}).get('path') != PROTOCOL):
        raise ValueError('Only frozen supine joint0 shoulder-final20/21/22 may be read after root authorizes completion.')
    if m.get('source_dirty') is not False or m.get('source_status') != '' or not re.fullmatch(r'[0-9a-f]{40}', m.get('source_commit', '')):
        raise ValueError('Formal collection source must be clean with a full commit.')
    return m


def input_hashes(path):
    path = Path(path)
    manifest = load_json(path/'manifest.json')
    names = {p.name for p in path.iterdir() if p.is_file() and p.name != 'manifest.json'}
    if set(manifest) != names or not {'metadata.json', 'episodes.json', 'seed_results.json',
                                    'trace.jsonl.gz', 'source_snapshot.zip'}.issubset(manifest):
        raise ValueError('Manifest must cover all original inputs exactly.')
    hashes = {}
    for name, expected in manifest.items():
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Manifest path is not local.')
        actual = file_hash(path/name)
        if actual != expected:
            raise ValueError('Input manifest mismatch: '+name)
        hashes[name] = actual
    hashes['manifest.json'] = file_hash(path/'manifest.json')
    return hashes


def duration(kind):
    return 300 if kind == 'calibration' else 100 if kind.startswith('prediction_') else 200


def complete(e):
    return (e.get('eligible') is True and e.get('completed') is True and e.get('status') == 'completed'
            and e.get('study_aborted') is False and e.get('environment_terminated') is False)


def coverage(cal, control, qref):
    def inputs(rows):
        return [(r['observation_before']['joint_position'][0]-qref,
                 r['observation_before']['joint_velocity'][0]) for r in rows
                if r['step_index'] >= 100 and r['diagnostics']['executed_substeps'] == 10]
    samples, states = inputs(cal), inputs(control)
    if not samples:
        return {'available': False, 'calibration_native_samples': 0, 'control_native_samples': len(states)}
    lo, hi = [min(x[i] for x in samples) for i in range(2)], [max(x[i] for x in samples) for i in range(2)]
    q_out = sum(q < lo[0] or q > hi[0] for q, v in states)
    v_out = sum(v < lo[1] or v > hi[1] for q, v in states)
    union = sum(q < lo[0] or q > hi[0] or v < lo[1] or v > hi[1] for q, v in states)
    nearest = [min(abs(q-cq) for cq, cv in samples) for q, v in states]
    return {'available': True, 'calibration_native_samples': len(samples), 'control_native_samples': len(states),
            'q_offset_envelope_rad': [lo[0], hi[0]], 'velocity_envelope_rad_s': [lo[1], hi[1]],
            'q_outside_count': q_out, 'v_outside_count': v_out, 'either_outside_count': union,
            'q_outside_fraction': q_out/len(states) if states else None,
            'v_outside_fraction': v_out/len(states) if states else None,
            'either_outside_fraction': union/len(states) if states else None,
            'nearest_q_distance_mean_rad': sum(nearest)/len(states) if states else None,
            'nearest_q_distance_max_rad': max(nearest, default=None)}


def complete_trials(seeds, kinds):
    unique = len(seeds) == 3 and all(type(s.get('seed')) is int for s in seeds) and {s['seed'] for s in seeds} == set(SEEDS)
    return unique and all(complete(s['evaluations'].get(k, {})) for s in seeds for k in kinds)


def independent_model_gate(seeds):
    all_five = complete_trials(seeds, MODEL_REQUIRED)
    pairs = []
    for s in seeds:
        ev = s['evaluations']
        old, new = ev.get('nominal_mpc', {}), ev.get('learned_mpc', {})
        a, b = old.get('tracking_rmse_rad'), new.get('tracking_rmse_rad')
        valid = all_five and finite(a) and finite(b) and a >= 0 and b >= 0
        prediction = {}
        for kind in ('prediction_low', 'prediction_full'):
            ep = ev.get(kind, {})
            n = ep.get('velocity_prediction_rmse', {}).get('nominal_mpc')
            l = ep.get('velocity_prediction_rmse', {}).get('learned_mpc')
            available = complete(ep) and finite(n) and finite(l) and n >= 0 and l >= 0
            prediction[kind] = {'available': available, 'nominal_velocity_rmse': n, 'learned_velocity_rmse': l,
                                'relative_improvement': 1.-l/n if available and n > 0 else None,
                                'passed': available and l <= .8*n}
            valid = valid and available
        pairs.append({'seed': s['seed'], 'complete_pair': valid,
                      'nominal_tracking_rmse_rad': a, 'learned_tracking_rmse_rad': b,
                      'strict_tracking_improvement': valid and b < a, 'prediction_gates': prediction})
    valid = all_five and all(r['complete_pair'] for r in pairs)
    old_mean = mean([p['nominal_tracking_rmse_rad'] for p in pairs]) if valid else None
    new_mean = mean([p['learned_tracking_rmse_rad'] for p in pairs]) if valid else None
    improvement = 1.-new_mean/old_mean if valid and old_mean > 0 else None
    passed = (valid and all(p['strict_tracking_improvement'] and all(g['passed'] for g in p['prediction_gates'].values()) for p in pairs)
              and improvement is not None and improvement >= .20)
    return {'evaluated': valid, 'all_five_required_trials_complete': all_five, 'passed': passed, 'per_seed': pairs,
            'nominal_raw_tracking_mean': old_mean, 'learned_raw_tracking_mean': new_mean,
            'tracking_mean_improvement': improvement}


def independent_classical_gate(seeds, contribution):
    all_six = complete_trials(seeds, (*MODEL_REQUIRED, 'tuned_pd'))
    pairs = []
    for s in seeds:
        ev = s['evaluations']
        old, new = ev.get('tuned_pd', {}), ev.get('learned_mpc', {})
        a, b = old.get('tracking_rmse_rad'), new.get('tracking_rmse_rad')
        valid = (all_six and finite(a) and finite(b) and a >= 0 and b >= 0
                 and all(e.get('actual_effort_complete') is True
                     and all(finite(e.get('control_effort', {}).get(k)) and e['control_effort'][k] >= 0 for k in EFFORT[2:])
                     for e in (old, new)))
        pairs.append({'seed': s['seed'], 'complete_pair': valid,
                      'pd_tracking_rmse_rad': a, 'learned_tracking_rmse_rad': b,
                      'tracking_non_worse': valid and b <= a,
                      'pd_actual_effort': old.get('control_effort'), 'learned_actual_effort': new.get('control_effort')})
    valid = all_six and all(r['complete_pair'] for r in pairs)
    old_mean = mean([p['pd_tracking_rmse_rad'] for p in pairs]) if valid else None
    new_mean = mean([p['learned_tracking_rmse_rad'] for p in pairs]) if valid else None
    improvement = 1.-new_mean/old_mean if valid and old_mean > 0 else None
    efforts = {}
    for key in EFFORT[2:]:
        a = mean([p['pd_actual_effort'][key] for p in pairs]) if valid else None
        b = mean([p['learned_actual_effort'][key] for p in pairs]) if valid else None
        efforts[key] = {'pd_mean': a, 'learned_mean': b,
                        'relative_increase': ratio_change(b, a) if valid else None,
                        'passed': valid and b <= 1.05*a}
    passed = (contribution['passed'] and valid and all(p['tracking_non_worse'] for p in pairs)
              and improvement is not None and improvement >= .05 and all(g['passed'] for g in efforts.values()))
    return {'evaluated': valid, 'same_mpc_contribution_passed': contribution['passed'],
            'all_six_required_trials_complete': all_six, 'passed': passed, 'per_seed': pairs,
            'pd_raw_tracking_mean': old_mean, 'learned_raw_tracking_mean': new_mean,
            'tracking_mean_improvement': improvement, 'actual_effort_gates': efforts}


def native_study_record(row, qref, checks, location):
    """Rebuild only the stop payload from recorded native endpoint values."""
    q, v = (row['observation_after'][key][0] for key in ('joint_position', 'joint_velocity'))
    checks.check(finite(q) and finite(v), location+'/finite_native_endpoint')
    expected = None
    if row['phase'] != 'prefix':
        checks.check(finite(qref), location+'/finite_reference')
        if finite(qref) and finite(q) and finite(v):
            triggers = []
            if abs(q-qref) >= .12:
                triggers.append('absolute_q_minus_qref_rad')
            if abs(v) >= 1.:
                triggers.append('absolute_velocity_rad_s')
            if triggers:
                expected = {'type': 'StudyAbort', 'message': 'predeclared native active envelope reached',
                    'stage': 'endpoint', 'triggers': triggers, 'q_rad': q, 'qref_rad': qref,
                    'q_minus_qref_rad': q-qref, 'velocity_rad_s': v,
                    'thresholds': {'absolute_q_minus_qref_rad': .12, 'absolute_velocity_rad_s': 1.},
                    'feedback_action': None, 'phase': row['phase'], 'step_index': row['step_index']}
    checks.compare(expected, row.get('study_abort'), location+'/native_stop_payload')
    return expected


def rebuild_trial(ep, rows, checks, qref):
    tid, kind = ep['trial_id'], ep['kind']
    regular = [r for r in rows if 'collector_exception' not in r]
    exceptions = [r for r in rows if 'collector_exception' in r]
    effort = {p: {k: 0. for k in EFFORT} for p in PHASES}
    physics, endpoints = Counter(), Counter()
    tracking, q_errors, v_errors = [], {}, {}
    complete_inputs = Counter()
    failed_at_start = len(checks.failures)
    last_study, returned_environment_stop = None, False
    for index, r in enumerate(regular):
        checks.compare(index, r['step_index'], tid+'/row_index')
        p, n = r['phase'], r['diagnostics']['executed_substeps']
        checks.check(p in PHASES and type(n) is int and 0 <= n <= 10, tid+'/phase_and_substeps')
        physics[p] += n
        endpoints[p] += 1
        if n == 10:
            complete_inputs[p] += 1
        history, u = r['diagnostics']['applied_torque_history'], r['requested_torque'][0]
        checks.check(len(history) == n and all(len(a) == 8 for a in history), tid+'/history_length')
        checks.check(r['requested_torque'][1:] == [0.]*7 and finite(u) and abs(u) <= .5, tid+'/permission')
        checks.check(not r.get('invalid_numeric_fields'), tid+'/finite_raw_record')
        native_stop = native_study_record(r, qref, checks, tid+'/'+str(index))
        if native_stop is not None:
            last_study = native_stop
        returned_environment_stop = returned_environment_stop or bool(r['diagnostics']['terminated'])
        checks.check(not (native_stop is not None or r['diagnostics']['terminated'])
                     or index == len(regular)-1 and ep['status'] in ('terminated', 'exception'),
                     tid+'/stop_is_final_returned_row')
        effort[p][EFFORT[0]] += abs(u)*n*PHYSICS_DT
        effort[p][EFFORT[1]] += u*u*n*PHYSICS_DT
        effort[p][EFFORT[2]] += sum(abs(a[0]) for a in history)*PHYSICS_DT
        effort[p][EFFORT[3]] += sum(a[0]*a[0] for a in history)*PHYSICS_DT
        if index >= 100:
            q, v = r['observation_after']['joint_position'][0], r['observation_after']['joint_velocity'][0]
            for name, (pq, pv) in r['predicted_next_qv'].items():
                q_errors.setdefault(name, [])
                v_errors.setdefault(name, [])
                if n == 10:
                    q_errors[name].append(q-pq)
                    v_errors[name].append(v-pv)
            if n == 10 and r['target_q'] is not None:
                tracking.append(q-r['target_q'])
    for r in exceptions:
        # Native endpoints the environment never returned did not reach the
        # collector's monitor. A storage exception may retain a returned one.
        received_endpoint = (r.get('observation_after') is not None and r.get('step_index') is not None
            and (any(x['step_index'] == r['step_index'] for x in regular)
                 or ep['control_steps'] > len(regular) and r.get('unreturned_physics_steps', 0) == 0))
        if received_endpoint:
            native_stop = native_study_record(r, qref, checks, tid+'/exception')
            if native_stop is not None:
                last_study = native_stop
    if ep['status'] != 'blocked':
        checks.compare(last_study, ep.get('study_abort'), tid+'/native_episode_study_stop')
        if not exceptions:
            checks.compare(returned_environment_stop, ep.get('environment_terminated'), tid+'/native_episode_environment_stop')
    else:
        checks.check(not rows and ep['control_calls_attempted'] == ep['control_steps'] == ep['physics_steps'] == 0,
                     tid+'/blocked_zero_cost')
    phase_details = {}
    for p in PHASES:
        paid = ep['phase_budgets'][p]['physics_steps']
        missing = paid-physics[p]
        checks.check(type(paid) is int and 0 <= missing <= 10, tid+'/paid_physics/'+p)
        commands = [r.get('requested_torque') for r in exceptions if r.get('phase') == p]
        reconstructable = missing == 0 or (0 < missing <= 10 and len(commands) == 1
            and isinstance(commands[0], list) and len(commands[0]) == 8
            and all(finite(u) and abs(u) <= .5 for u in commands[0]) and commands[0][1:] == [0.]*7)
        if missing > 0 and reconstructable:
            u = commands[0][0]
            effort[p][EFFORT[0]] += abs(u)*missing*PHYSICS_DT
            effort[p][EFFORT[1]] += u*u*missing*PHYSICS_DT
        phase_details[p] = {'independent_effort': effort[p],
                            'requested_effort_reconstruction_complete': reconstructable,
                            'actual_effort_reconstruction_complete': missing == 0,
                            'actual_effort_is_lower_bound': missing > 0,
                            'unreconstructed_actual_effort_substeps': missing,
                            'known_physical_substeps': physics[p], 'paid_physical_substeps': paid,
                            'returned_endpoint_samples': endpoints[p], 'complete_input_samples': complete_inputs[p]}
    full = (ep['status'] == 'completed' and len(regular) == 100+duration(kind)
            and ep['control_calls_attempted'] == ep['control_steps'] == len(regular)
            and ep['physics_steps'] == 10*len(regular) and not exceptions
            and all(r['diagnostics']['executed_substeps'] == 10 and not r['diagnostics'].get('terminated')
                    and r.get('study_abort') is None for r in regular)
            and ep.get('study_abort') is None and ep.get('environment_terminated') is False)
    checks.check(ep['status'] != 'completed' or full, tid+'/claimed_completion')
    return {'completed': full, 'eligible': full and len(checks.failures) == failed_at_start,
            'status': ep['status'], 'study_aborted': last_study is not None,
            'environment_terminated': ep.get('environment_terminated') is True,
            'tracking_rmse_rad': rmse(tracking), 'position_prediction_rmse': {n: rmse(v) for n, v in q_errors.items()},
            'velocity_prediction_rmse': {n: rmse(v) for n, v in v_errors.items()},
            'control_effort': effort['control'],
            'actual_effort_complete': ep['status'] != 'blocked' and phase_details['control']['actual_effort_reconstruction_complete'],
            'phase_effort': phase_details,
            'metric_control_step_count': len(tracking),
            'metric_prediction_step_count': {n: len(v) for n, v in v_errors.items()},
            'raw_exception_records': exceptions,
            'paid_budget': {k: ep[k] for k in ('control_calls_attempted', 'control_steps', 'physics_steps')}}, regular


def count_model_updates(sr, grouped, checks):
    models = {}
    for schedule in SCHEDULES:
        name = schedule+'_hinge5'
        saved = sr.get('learned_models', {}).get(name)
        if saved is None:
            continue
        rows = grouped.get(f"seed{sr['seed']}_calibration", [])
        unique = {}
        exceptional = 0
        snapshots = []
        for r in rows:
            item = (r.get('model_update') or {}).get('hinge5')
            if item is not None and item.get('updated') is True:
                identity = r['shared_transition_id']
                if identity in unique:
                    checks.compare(unique[identity], item['update_count'], name+'/duplicate_atomic_count')
                else:
                    unique[identity] = item['update_count']
                    exceptional += int('collector_exception' in r)
            snapshot = r.get('partial_model_snapshots', {}).get('hinge5')
            if snapshot is not None:
                snapshots.append((r, snapshot))
        known = len(unique)
        checks.compare(list(range(1, known+1)), list(unique.values()), name+'/atomic_event_sequence')
        snapshot_extra = 0
        checks.check(len(snapshots) <= 1, name+'/single_exception_snapshot')
        for r, snapshot in snapshots:
            difference = snapshot['update_count']-known
            item = (r.get('model_update') or {}).get('hinge5')
            if difference == 1 and item is None:
                episode = sr['_episodes']['calibration']
                ep_physics = episode['physics_steps']
                raw_physics = sum(x['diagnostics']['executed_substeps'] for x in rows if 'collector_exception' not in x)
                raw_calibration = sum(x['diagnostics']['executed_substeps'] for x in rows
                    if 'collector_exception' not in x and x['phase'] == 'calibration')
                observation = r.get('observation_after')
                regular_count = sum('collector_exception' not in x for x in rows)
                full_missing = (ep_physics-raw_physics == 10
                    and episode['phase_budgets']['calibration']['physics_steps']-raw_calibration == 10
                    and r.get('step_index', -1) == regular_count >= 100 and observation is not None
                    and r.get('diagnostics', {}).get('physics_steps') == ep_physics)
                checks.check(full_missing, name+'/snapshot_recovery_complete_native_interval')
                if full_missing:
                    snapshot_extra += 1
            checks.check(difference in (0, 1), name+'/snapshot_atomic_gap')
        reported = saved['update_count']
        reconstructed = known+snapshot_extra
        checks.check(type(reported) is int and 0 <= reconstructed <= reported <= 300, name+'/paid_update_cap')
        models[name] = {'reported_updates': reported, 'replayed_updates': reconstructed,
                        'exception_replayed_updates': exceptional+snapshot_extra,
                        'unreconstructed_updates': reported-reconstructed,
                        'count_semantics': 'Count stored successful atomic events/snapshots only; no RLS or parameter math executed.'}
    return models


def raw_means(seeds):
    output = {}
    for kind in CONTROLS:
        ev = [s['evaluations'].get(kind, {}) for s in seeds]
        complete_tracking = all(complete(e) and finite(e.get('tracking_rmse_rad')) for e in ev)
        complete_effort = complete_tracking and all(e.get('actual_effort_complete') is True for e in ev)
        output[kind] = {'all_three_complete': complete_tracking,
                        'tracking_raw_mean_rad': mean([e['tracking_rmse_rad'] for e in ev]) if complete_tracking else None,
                        'actual_control_effort_raw_means': {k: mean([e['control_effort'][k] for e in ev]) if complete_effort else None for k in EFFORT[2:]}}
    for kind in ('prediction_low', 'prediction_full'):
        ev = [s['evaluations'].get(kind, {}) for s in seeds]
        all_complete = all(complete(e) for e in ev)
        output[kind] = {field: {name: mean([e.get(field, {}).get(name) for e in ev]) if all_complete else None
                               for name in ('learned_mpc', 'nominal_mpc', 'persistence')}
                        for field in ('position_prediction_rmse', 'velocity_prediction_rmse')}
    return output


def review(archive_path, audit_path):
    wall, cpu = time.perf_counter(), time.process_time()
    archive_path, audit_path = Path(archive_path).resolve(), Path(audit_path).resolve()
    metadata = require_final(archive_path)  # Scope gate before trace/audit outcomes.
    hashes, audit_hash = input_hashes(archive_path), file_hash(audit_path)
    authoritative = load_json(audit_path)
    if authoritative.get('failed') != 0 or type(authoritative.get('checks')) is not int or authoritative['checks'] <= 0:
        raise ValueError('Successful authoritative data-consistency audit required; science gates may fail.')
    archived = authoritative['archive']
    if (Path(archived['path']).resolve() != archive_path or archived['input_hashes'] != hashes
            or archived['source_commit'] != metadata['source_commit'] or archived['split'] != 'final_holdout'):
        raise ValueError('Authoritative audit does not match exact inputs.')
    episodes = load_json(archive_path/'episodes.json')
    snapshots = load_json(archive_path/'seed_results.json')
    checks = Checks()
    expected_ids = [f'seed{s}_{k}' for s in SEEDS for k in KINDS]
    checks.compare(expected_ids, [e['trial_id'] for e in episodes], 'ordered_full_plan')
    if len({e['trial_id'] for e in episodes}) != 21:
        raise ValueError('Exactly 21 unique planned outcomes required.')
    ep_map, sr_map = {e['trial_id']: e for e in episodes}, {s['seed']: s for s in snapshots}
    if len(sr_map) != len(snapshots) or not set(sr_map).issubset(SEEDS):
        raise ValueError('Duplicate or foreign raw seed snapshots.')
    if [s['seed'] for s in archived['seeds']] != SEEDS:
        raise ValueError('Authoritative audit must retain all three seed outcomes.')
    grouped = {}
    with gzip.open(archive_path/'trace.jsonl.gz', 'rt', encoding='utf-8') as stream:
        for line in stream:
            r = json.loads(line)
            if r.get('trial_id') not in ep_map or r.get('seed') not in SEEDS:
                raise ValueError('Trace foreign scope.')
            grouped.setdefault(r['trial_id'], []).append(r)
    seeds = []
    for seed, audited_seed in zip(SEEDS, archived['seeds']):
        sr = sr_map.get(seed)
        if sr is None:
            checks.check(all(ep_map[f'seed{seed}_{k}']['status'] == 'blocked' for k in KINDS), f'seed{seed}/unstarted')
            seeds.append({'seed': seed, 'evaluations': {}, 'models': {}})
            continue
        checks.compare(RESET_SEEDS[seed], sr['reset_seed'], f'seed{seed}/fixed_reset_seed')
        qref = sr.get('reference_q')
        ev, regular = {}, {}
        for kind in KINDS:
            tid = f'seed{seed}_{kind}'
            ev[kind], regular[kind] = rebuild_trial(ep_map[tid], grouped.get(tid, []), checks, qref)
            fields = {k: ev[kind][k] for k in ('completed', 'eligible', 'status', 'study_aborted', 'environment_terminated',
                      'tracking_rmse_rad', 'position_prediction_rmse', 'velocity_prediction_rmse', 'control_effort', 'actual_effort_complete', 'paid_budget')}
            audited = audited_seed['evaluations'][kind]
            checks.compare(fields, audited, tid+'/authoritative_metrics')
            for phase in PHASES:
                effort = {k: v for k, v in ev[kind]['phase_effort'][phase].items() if k in (
                    'independent_effort', 'requested_effort_reconstruction_complete', 'actual_effort_reconstruction_complete',
                    'actual_effort_is_lower_bound', 'unreconstructed_actual_effort_substeps')}
                if ep_map[tid]['status'] != 'blocked':
                    checks.compare(effort, audited['phase_effort'][phase], tid+'/phase_effort/'+phase)
                checks.compare(ev[kind]['phase_effort'][phase]['known_physical_substeps'],
                               audited['phase_risk'][phase]['physical_substeps'], tid+'/risk_known_substeps/'+phase)
        supports = {}
        if qref is not None:
            if not finite(qref):
                raise ValueError('Native reference must be finite.')
            supports = coverage(regular['calibration'], [], qref)
            for kind in CONTROLS:
                ev[kind]['state_coverage'] = coverage(regular['calibration'], regular[kind], qref)
                checks.compare(ev[kind]['state_coverage'], audited_seed['evaluations'][kind]['state_coverage'], f'seed{seed}/{kind}/raw_coverage')
        sr_for_count = {**sr, '_episodes': {k: ep_map[f'seed{seed}_{k}'] for k in KINDS}}
        model_counts = count_model_updates(sr_for_count, grouped, checks)
        checks.compare({n: {k: m[k] for k in ('reported_updates', 'replayed_updates', 'exception_replayed_updates', 'unreconstructed_updates')}
                        for n, m in model_counts.items()}, audited_seed.get('models', {}), f'seed{seed}/update_counts')
        checks.compare(sum(m['reported_updates'] for m in model_counts.values()), sr['calibration_updates'], f'seed{seed}/collector_update_sum')
        seeds.append({'seed': seed, 'calibration_support': supports, 'models': model_counts, 'evaluations': ev})
    budgets = {k: sum(e[k] for e in episodes) for k in ('control_calls_attempted', 'control_steps', 'physics_steps')}
    budgets['model_updates'] = sum(m['reported_updates'] for s in seeds for m in s['models'].values())
    checks.compare(budgets, archived['budget'], 'independent_budget')
    checks.compare(budgets, metadata, 'collector_budget')
    checks.check(budgets['control_calls_attempted'] <= 6000 and budgets['control_steps'] <= 6000
                 and budgets['physics_steps'] <= 60000 and budgets['model_updates'] <= 900, 'budget_caps')
    phase_budget = {p: {k: sum(e['phase_budgets'][p][k] for e in episodes)
                       for k in ('control_calls_attempted', 'control_steps', 'physics_steps')} for p in PHASES}
    checks.compare(phase_budget, archived['phase_budget'], 'independent_phase_budget')
    statuses = Counter(e['status'] for e in episodes)
    stops = {'study': sum(e.get('study_abort') is not None for e in episodes),
             'environment': sum(e.get('environment_terminated') is True for e in episodes),
             'both': sum(e.get('study_abort') is not None and e.get('environment_terminated') is True for e in episodes)}
    checks.compare(stops, archived['stops'], 'independent_stop_counts')
    for status in ('completed', 'terminated', 'exception', 'blocked', 'planned'):
        key = 'unprocessed_trials' if status == 'planned' else status+'_trials'
        checks.compare(statuses[status], metadata[key], 'collector_status/'+status)
    checks.compare(statuses['completed'] == 21, metadata['all_trials_successful'], 'collector_all_trials_successful')
    checks.compare(statuses['terminated']+statuses['exception'], metadata['failed_trials'], 'collector_failed_trials')
    checks.compare(statuses['blocked'], metadata['skipped_trials'], 'collector_skipped_trials')
    calibration_transfers = sum(e['phase_budgets']['calibration']['control_steps'] for e in episodes)
    checks.compare(calibration_transfers, archived['physical_calibration_transfers'], 'independent_calibration_transfers')
    startup_costs = []
    for seed in SEEDS:
        costs = {}
        for kind in CONTROLS:
            own = ep_map[f'seed{seed}_{kind}']
            prerequisite = ep_map[f'seed{seed}_calibration'] if kind == 'learned_mpc' else None
            costs[kind] = {k: own[k]+(prerequisite[k] if prerequisite else 0)
                           for k in ('control_calls_attempted', 'control_steps', 'physics_steps')}
        evaluation = [ep_map[f'seed{seed}_{kind}'] for kind in ('prediction_low', 'prediction_full')]
        startup_costs.append({'seed': seed, 'cold_start_plus_paired_control': costs,
                             'shared_prediction_evaluation_cost': {k: sum(e[k] for e in evaluation)
                                 for k in ('control_calls_attempted', 'control_steps', 'physics_steps')},
                             'semantics': 'Learned includes own paid calibration plus own control trial; nominal/PD/zero do not require a fit. Diagnostic shared predictions and prior development/PD tuning are additional disclosed costs. Failed/blocked paid calibration is retained; these costs are not four equal portions of the batch.'})
    model_gate = independent_model_gate(seeds)
    classical_gate = independent_classical_gate(seeds, model_gate)
    gates = {'model_contribution_gate': model_gate, 'classical_comparison_gate': classical_gate,
             'complete_matrix': complete_trials(seeds, KINDS), 'data_consistency_verified': True}
    git_enabled = authoritative['execution'].get('source_git_verification_enabled')
    if type(git_enabled) is not bool:
        raise ValueError('Audit must expose source Git verification switch.')
    for name in ('model_contribution_gate', 'classical_comparison_gate'):
        gates[name]['validated_pass'] = gates[name]['passed'] and git_enabled
    checks.compare(gates, authoritative['final_gates'], 'independent_final_gates')
    source = Path(__file__).read_bytes()
    report = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(), 'purpose': __doc__,
              'source_commit': metadata['source_commit'], 'split': 'final_holdout',
              'archive_path': str(archive_path), 'input_hashes': hashes, 'audit_path': str(audit_path), 'audit_sha256': audit_hash,
              'summary_source_sha256': hashlib.sha256(source).hexdigest(), 'summary_source_bytes_base64': base64.b64encode(source).decode('ascii'),
              'checks': checks.count, 'failed': len(checks.failures), 'violations': checks.failures,
              'maximum_recomputation_difference': checks.maximum_difference,
              'independently_recomputed_budget': budgets, 'independently_recomputed_phase_budget': phase_budget,
              'independently_counted_calibration_transfers': calibration_transfers,
              'per_seed_method_startup_costs': startup_costs,
              'statuses': dict(statuses), 'stops': stops,
              'formal_collection_timing': archived['collector_timing'], 'authoritative_audit_checks': authoritative['checks'],
              'independent_final_gates': gates,
              'review_validated_model_contribution': gates['model_contribution_gate']['validated_pass'] and not checks.failures,
              'review_validated_classical_comparison': gates['classical_comparison_gate']['validated_pass'] and not checks.failures,
              'scientific_gates_verified': not checks.failures,
              'raw_three_seed_means': raw_means(seeds), 'raw_recomputed_seed_details': seeds,
              'audited_seed_details': archived['seeds'], 'audited_final_gates': authoritative['final_gates'],
              'comparison_semantics': 'Raw per-seed means; same-MPC model contribution and independent learned/PD comparison require five/six complete trials; all seven completion is separate. Different controller trajectories are separate closed-loop effects. Equal permission/control windows are not equal total startup budgets. No pooling overlapping windows, picked blocks or seed-wise controller choices.',
              'coverage_semantics': 'Complete active native inputs; strict q/v envelope exclusion, equality inside; nearest q-only distance. Coverage is descriptive; no new adoption threshold or safety claim.',
              'audited_diagnostic_semantics': 'Full per-seed risk, conditional and 1/5/15/50-step rollout details and fixed active80-99/180-199 tail metrics retained from first audit. No new model prediction or RLS math is executed here.',
              'risk_semantics': 'Full audited per-seed/full/phase raw risk retained; missing substep peaks/impulse/penetration are lower bounds, minimum contact distance upper bound, native joint speed/limits endpoints only; zero stops do not prove safety.',
              'execution': {'python': sys.version, 'platform': platform.platform(), 'third_party_dependencies': [],
                            'physical_simulation_calls': 0, 'model_prediction_calls': 0, 'rls_replay_calls': 0,
                            'real_parameter_fitting_calls': 0, 'real_parameter_updates': 0, 'new_environment_interactions': 0,
                            'timing_scope': 'review entry through source bytes/input unchanged validation and report assembly; excludes imports and JSON serialization/writing'}}
    if input_hashes(archive_path) != hashes or file_hash(audit_path) != audit_hash:
        raise ValueError('Read-only review inputs changed.')
    report['execution'].update(wall_seconds=time.perf_counter()-wall, cpu_seconds=time.process_time()-cpu)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('external/local_frozen_20261011_final'))
    parser.add_argument('--audit', type=Path, default=Path('external/local_frozen_20261011_final_audit.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output, archive, audit = args.output.resolve(), args.archive.resolve(), args.audit.resolve()
    if output.exists() or output.is_relative_to(archive) or output == audit or output == Path(__file__).resolve():
        parser.error('Refusing overwrite, input/source replacement or output inside raw archive.')
    report = review(archive, audit)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'report': str(output), 'checks': report['checks'], 'failed': report['failed'],
                      'model_contribution_pass': report['review_validated_model_contribution'],
                      'classical_comparison_pass': report['review_validated_classical_comparison'],
                      'complete_matrix': report['independent_final_gates']['complete_matrix'], 'execution': report['execution']}))
    return int(report['failed'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
