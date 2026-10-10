"""Independently audit a frozen CPU history/horizon archive, without training.

Uses only NumPy, standard-library readers and Git blobs. It never imports the
project, generates planner actions, or reruns the experiment. The scalar Euler
implementation checks recorded actions, dynamics and predictions; planner
optimality remains a unit-test concern. Supports this archive schema and its
finite trajectories, including position/speed exits.

Usage:
    python scripts/audit_cpu_history_archive.py [archive_path] --output audit.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np


def audit_archive(archive_path: Path) -> dict:
    """Fail on any inconsistency; return a reviewable independent summary."""
    if not __debug__:
        raise RuntimeError("Run without -O so the audit assertions remain active")
    repo = Path(__file__).resolve().parents[1]
    archive_path = archive_path.resolve()
    report = json.loads((archive_path / 'report.json').read_text(encoding='utf-8'))
    commit = report['git']['commit']
    assert report['kind'] == 'cpu_no_training_history_horizon_diagnostic'
    assert commit and report['git']['dirty'] is False
    assert report['device'] == 'cpu' and report['gpu'] is None
    assert all(report[x] == 0 for x in ('model_parameter_updates', 'policy_parameter_updates', 'delay_parameter_updates'))
    assert report['model_fingerprint_before'] == report['model_fingerprint_after']
    assert report['fixed_parameters_before'] == report['fixed_parameters_after']

    def signature(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode('utf-8')).hexdigest()
    assert signature(report['config']) == report['fixed_parameters_before']
    assert signature(report['config']['model']) == report['model_fingerprint_before']
    with zipfile.ZipFile(archive_path / 'source_snapshot.zip') as z:
        assert set(z.namelist()) == set(report['source_sha256'])
        for name, digest in report['source_sha256'].items():
            blob = z.read(name)
            assert hashlib.sha256(blob).hexdigest() == digest
            git_blob = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=repo)
            assert blob == git_blob, name
    protocol_blob = subprocess.check_output(['git', 'show', commit + ':docs/CPU_HISTORY_PROTOCOL.md'], cwd=repo)
    assert hashlib.sha256(protocol_blob).hexdigest() == report['protocol_sha256']
    # The archived Git commit is authoritative; today's protocol may have evolved.

    text_fields = {'scenario', 'mode', 'phase', 'audit_half'}
    int_fields = {'seed', 'command_step', 'step', 'issued_history_length', 'declared_initial_delay_steps', 'assumed_delay_steps', 'horizon_steps', 'candidate_effect_steps', 'assumed_applied_command_step', 'applied_command_step', 'true_delay_steps', 'feasible_candidates', 'planner_model_transitions'}
    bool_fields = {'finite', 'safe', 'fallback', 'command_limit_violation', 'effective_exceeds_nominal_hard_limit'}
    def parse(row):
        result = {}
        for key, value in row.items():
            if key in text_fields:
                result[key] = value
            elif value == '':
                result[key] = None
            elif key in bool_fields:
                assert value in ('True', 'False')
                result[key] = value == 'True'
            elif key in int_fields:
                result[key] = int(value)
            else:
                result[key] = float(value)
        return result
    with gzip.open(archive_path / 'trace.csv.gz', 'rt', encoding='utf-8', newline='') as f:
        rows = [parse(row) for row in csv.DictReader(f)]
    trials = defaultdict(list)
    for row in rows:
        trials[(row['scenario'], row['seed'], row['mode'])].append(row)
    assert len(rows) == report['total_executed_steps']
    expected_trials = len(report['config']['scenarios']) * len(report['config']['config']['seeds']) * len(report['config']['controllers'])
    assert len(trials) == len(report['records']) == expected_trials
    assert report['planned_interaction_steps'] == expected_trials * report['config']['config']['rollout_steps']
    assert report['diagnostic_one_step_model_predictions'] == 3 * len(rows)
    assert report['total_planner_model_transitions'] == sum(row['planner_model_transitions'] for row in rows)
    assert json.loads((archive_path / 'gates.json').read_text(encoding='utf-8')) == []

    cfg = report['config']['config']
    nominal = report['config']['model']['parameters']
    scenarios = {item['plant']['name']: item for item in report['config']['scenarios']}
    specs = {item['name']: item for item in report['config']['controllers']}
    target = np.array(cfg['target'])
    scales = np.array([cfg['position_limit']] * 2 + [cfg['speed_limit']] * 2)
    maximum_error = defaultdict(float)
    checks = 0

    def compare(actual, expected, label):
        nonlocal checks
        checks += 1
        if isinstance(expected, dict):
            assert isinstance(actual, dict), label
            for key, value in expected.items():
                assert key in actual, (label, key)
                compare(actual[key], value, label + '.' + key)
        elif isinstance(expected, (bool, str)) or expected is None:
            assert actual == expected, (label, actual, expected)
        else:
            aa, bb = np.array(actual, dtype=float), np.array(expected, dtype=float)
            assert aa.shape == bb.shape, (label, aa.shape, bb.shape)
            difference = float(np.max(np.abs(aa - bb))) if aa.size else 0.
            maximum_error[label.split('.')[0]] = max(maximum_error[label.split('.')[0]], difference)
            assert np.allclose(aa, bb, rtol=2e-13, atol=2e-15), (label, actual, expected, difference)

    def euler(state, action, parameters, external=(0., 0.)):
        q0, q1, v0, v1 = [float(x) for x in state]
        positions, velocities = (q0, q1), (v0, v1)
        next_v = []
        for j in range(2):
            acceleration = (parameters['actuator_gain'][j] * action[j] + external[j]
                            - parameters['damping'][j] * velocities[j]
                            - parameters['stiffness'][j] * positions[j]
                            - parameters['coupling'] * (positions[j] - positions[1-j])) / parameters['inertia'][j]
            next_v.append(velocities[j] + cfg['dt'] * acceleration)
        return np.array([q0 + cfg['dt'] * next_v[0], q1 + cfg['dt'] * next_v[1], next_v[0], next_v[1]])

    def metrics(items):
        if not items:
            return None
        all_finite = all(row['finite'] for row in items)
        result = {'executed_steps': len(items),
                  'fallback_steps': sum(row['fallback'] for row in items),
                  'command_limit_violation_steps': sum(row['command_limit_violation'] for row in items),
                  'planner_model_transitions': sum(row['planner_model_transitions'] for row in items),
                  'effective_torque_exceeds_nominal_hard_limit_steps': sum(row['effective_exceeds_nominal_hard_limit'] for row in items)}
        for name in ('full_target_rmse', 'prediction_rmse', 'immediate_prediction_rmse', 'applied_label_prediction_rmse'):
            result[name] = float(np.sqrt(np.mean([row[name] ** 2 for row in items]))) if all_finite else None
        result['peak_speed'] = max(max(abs(row['v0']), abs(row['v1'])) for row in items) if all_finite else None
        result['peak_effective_torque'] = max(max(abs(row['effective_torque0']), abs(row['effective_torque1'])) for row in items)
        return result

    record_keys = set()
    for record in report['records']:
        key = record['scenario'], record['seed'], record['mode']
        assert key not in record_keys
        record_keys.add(key)
        items = trials[key]
        scenario, spec = scenarios[key[0]], specs[key[2]]
        plant = scenario['plant']
        change = plant['change_step']
        declared = scenario['declared_initial_delay_steps']
        assumed_delay = declared if spec['use_history'] else 0
        rng = np.random.default_rng(key[1])
        initial = np.concatenate((rng.uniform(-.005, .005, 2), rng.uniform(-.003, .003, 2)))
        compare(record['initial_state'], initial, 'initial')
        compare(record['initial_full_target_rmse'], float(np.sqrt(np.mean((initial[:2] - target) ** 2))), 'initial_rmse')
        assert signature(record['controller_parameters']) == record['fixed_parameters_before'] == record['fixed_parameters_after']
        cp = record['controller_parameters']
        assert cp['history_config'] == {'assumed_delay_steps': declared, 'use_history': spec['use_history']}
        assert cp['spec'] == spec
        assert cp['model'] == report['config']['model']
        assert cp['permission'] == report['config']['permission']
        candidates_per_joint = cp['planner']['candidates_per_joint']
        permission_limits = np.array(cp['permission']['torque_limits'])
        assert all(cp['permission']['active_joints']), 'This diagnostic expects two active joints'
        grids = [np.linspace(-limit, limit, candidates_per_joint) for limit in permission_limits]
        commands = []
        previous_state = initial
        for t, row in enumerate(items):
            assert row['command_step'] == row['issued_history_length'] == t
            assert row['step'] == t + 1
            compare(row['physical_seconds'], (t + 1) * cfg['dt'], 'time')
            phase = 'constant' if change is None else ('pre_change' if t < change else 'post_change')
            assert row['phase'] == phase
            assert row['audit_half'] == ('first225' if t < 225 else 'second225')
            assert row['declared_initial_delay_steps'] == declared and row['assumed_delay_steps'] == assumed_delay
            obs = np.array([row['obs_' + name] for name in ('q0', 'q1', 'v0', 'v1')])
            next_state = np.array([row[name] for name in ('q0', 'q1', 'v0', 'v1')])
            compare(obs, previous_state, 'state_continuity')
            command = np.array([row['command0'], row['command1']])
            inferred_source = t - assumed_delay
            inferred = np.zeros(2) if inferred_source < 0 else (commands[inferred_source] if inferred_source < t else command)
            assert row['assumed_applied_command_step'] == (None if inferred_source < 0 else inferred_source)
            compare([row['assumed_applied0'], row['assumed_applied1']], inferred, 'assumed_history')
            if spec['kind'] == 'planner':
                assert row['horizon_steps'] == spec['horizon_steps']
                assert row['candidate_effect_steps'] == max(spec['horizon_steps'] - assumed_delay, 0)
                assert row['planner_model_transitions'] == spec['horizon_steps'] * candidates_per_joint ** 2
                assert row['feasible_candidates'] in range(candidates_per_joint ** 2 + 1)
                assert row['fallback'] == (row['feasible_candidates'] == 0)
                assert all(np.any(np.abs(grid - value) <= 1e-15) for grid, value in zip(grids, command))
                if row['fallback']:
                    compare(command, np.zeros(2), 'fallback')
            else:
                assert row['horizon_steps'] is None and row['candidate_effect_steps'] is None
                assert row['planner_model_transitions'] == 0 and row['feasible_candidates'] is None and not row['fallback']
                feedforward = np.array(nominal['stiffness']) * target + nominal['coupling'] * (target - target[::-1])
                pd_command = np.clip(feedforward + 4. * (target - obs[:2]) - 2. * obs[2:], -permission_limits, permission_limits)
                compare(command, pd_command, 'pd_command')
            method_prediction = euler(obs, inferred, nominal)
            compare([row['pred_' + name] for name in ('q0', 'q1', 'v0', 'v1')], method_prediction, 'method_prediction')
            parameters = plant['before'] if change is None or t < change else plant['after']
            assert row['true_delay_steps'] == parameters['delay_steps']
            compare([row['true_gain0'], row['true_gain1']], parameters['actuator_gain'], 'true_gain')
            compare([row['true_inertia0'], row['true_inertia1']], parameters['inertia'], 'true_inertia')
            actual_source = t - parameters['delay_steps']
            commands.append(command.copy())
            applied = commands[actual_source] if actual_source >= 0 else np.zeros(2)
            assert row['applied_command_step'] == (actual_source if actual_source >= 0 else None)
            compare([row['applied0'], row['applied1']], applied, 'actual_history')
            compare([row['effective_torque0'], row['effective_torque1']], applied * parameters['actuator_gain'], 'effective_torque')
            external = np.array([.12, -.10]) if t % cfg['window_steps'] < 2 else np.zeros(2)
            compare([row['disturbance0'], row['disturbance1']], external, 'external')
            calculated_next = euler(obs, applied, parameters, external)
            compare(next_state, calculated_next, 'actual_dynamics')
            assert row['finite'] == bool(np.isfinite(calculated_next).all())
            safe = bool(np.isfinite(calculated_next).all() and max(np.abs(calculated_next[:2])) <= cfg['position_limit'] and max(np.abs(calculated_next[2:])) <= cfg['speed_limit'])
            assert row['safe'] == safe
            if t < len(items) - 1:
                assert safe
            for field, prediction in (('prediction_rmse', method_prediction), ('immediate_prediction_rmse', euler(obs, command, nominal)), ('applied_label_prediction_rmse', euler(obs, applied, nominal))):
                residual = float(np.sqrt(np.mean(((prediction - calculated_next) / scales) ** 2)))
                compare(row[field], residual, field)
            compare(row['full_target_rmse'], float(np.sqrt(np.mean((calculated_next[:2] - target) ** 2))), 'full_target_rmse')
            violation = bool(np.any(np.abs(command) > permission_limits + 1e-12) or np.any(np.abs(command) > np.array(cfg['hard_torque_limits']) + 1e-12))
            assert row['command_limit_violation'] == violation is False
            effective_violation = bool(np.any(np.abs(applied * parameters['actuator_gain']) > np.array(cfg['hard_torque_limits']) + 1e-12))
            assert row['effective_exceeds_nominal_hard_limit'] == effective_violation
            previous_state = calculated_next
        compare(record, metrics(items), 'whole_metrics')
        assert record['budget_steps'] == cfg['rollout_steps']
        compare(record['final_full_target_rmse'], items[-1]['full_target_rmse'], 'final_rmse')
        expected_termination = 'nonfinite_state' if not items[-1]['finite'] else ('completed' if items[-1]['safe'] else 'state_limit')
        assert record['termination_reason'] == expected_termination
        assert record['exit_step'] == (None if items[-1]['safe'] else len(items))
        compare(record['exit_seconds'], None if items[-1]['safe'] else len(items) * cfg['dt'], 'exit_seconds')
        if expected_termination == 'completed':
            assert len(items) == cfg['rollout_steps']
        for name, field in (('phases', 'phase'), ('audit_halves', 'audit_half')):
            for category, observed in record[name].items():
                compare(observed, metrics([row for row in items if row[field] == category]), name)
        timings = np.array([row['action_selection_ms'] for row in items])
        compare(record['action_selection_ms'], {'median': float(np.median(timings)), 'p95': float(np.percentile(timings, 95)), 'max': float(max(timings)), 'exceeds_dt_steps': int(sum(timings > cfg['dt'] * 1000))}, 'timings')
    assert record_keys == set(trials)
    comparisons = (('immediate_h20', 'history_h20'), ('immediate_h50', 'history_h50'), ('immediate_h20', 'immediate_h50'), ('history_h20', 'history_h50'))
    expected_pairs = {(scenario, seed, left, right) for scenario in scenarios for seed in cfg['seeds'] for left, right in comparisons if left in specs and right in specs}
    observed_pairs = {(p['scenario'], p['seed'], p['left'], p['right']) for p in report['paired_comparisons']}
    assert observed_pairs == expected_pairs and len(observed_pairs) == len(report['paired_comparisons'])
    for pair in report['paired_comparisons']:
        a = trials[(pair['scenario'], pair['seed'], pair['left'])]
        b = trials[(pair['scenario'], pair['seed'], pair['right'])]
        count = min(len(a), len(b))
        assert pair['common_executed_steps'] == count
        compare(pair['left_common_metrics'], metrics(a[:count]), 'paired_left')
        compare(pair['right_common_metrics'], metrics(b[:count]), 'paired_right')
        identical = all(all(x[name] == y[name] for name in ('q0', 'q1', 'v0', 'v1', 'command0', 'command1')) for x, y in zip(a[:count], b[:count]))
        assert pair['identical_common_state_and_commands'] == identical
        if scenarios[pair['scenario']]['declared_initial_delay_steps'] == 0 and pair['left'].replace('immediate', 'history') == pair['right']:
            assert identical and len(a) == len(b)
            assert all(x['prediction_rmse'] == y['prediction_rmse'] for x, y in zip(a, b))

    grouped = defaultdict(list)
    for record in report['records']:
        grouped[(record['scenario'], record['mode'])].append(record)
    method_outcomes = []
    zero_groups = []
    for (scenario, mode), records in sorted(grouped.items()):
        group_rows = [row for record in records for row in trials[(scenario, record['seed'], mode)]]
        post = [record['phases']['post_change'] for record in records
                if record['phases']['post_change'] is not None]
        nonzero = sum(row['command0'] != 0 or row['command1'] != 0 for row in group_rows)
        outcome = {
            'scenario': scenario, 'mode': mode, 'runs': len(records),
            'completed': sum(record['termination_reason'] == 'completed' for record in records),
            'state_limit_exits': sum(record['termination_reason'] == 'state_limit' for record in records),
            'executed_steps_by_seed': {str(record['seed']): record['executed_steps'] for record in records},
            'whole_target_rmse_mean_rad': float(np.mean([record['full_target_rmse'] for record in records])),
            'post_change_runs': len(post),
            'post_change_steps_by_seed': {
                str(record['seed']): None if record['phases']['post_change'] is None
                else record['phases']['post_change']['executed_steps'] for record in records},
            'post_change_target_rmse_mean_rad': float(np.mean([x['full_target_rmse'] for x in post])) if post else None,
            'causal_residual_mean': float(np.mean([record['prediction_rmse'] for record in records])),
            'nonzero_command_steps': nonzero,
            'peak_issued_command': max(max(abs(row['command0']), abs(row['command1'])) for row in group_rows),
        }
        method_outcomes.append(outcome)
        if nonzero == 0:
            zero_groups.append({'scenario': scenario, 'mode': mode,
                                'runs': len(records), 'executed_steps': len(group_rows)})
    worse_horizon = []
    for scenario in scenarios:
        for model_assumption in ('immediate', 'history'):
            low = {x['seed']: x for x in grouped[(scenario, model_assumption + '_h20')]}
            high = {x['seed']: x for x in grouped[(scenario, model_assumption + '_h50')]}
            eligible = [seed for seed in cfg['seeds'] if seed in low and seed in high
                        and low[seed]['phases']['post_change'] is not None
                        and high[seed]['phases']['post_change'] is not None]
            if not eligible:
                continue
            lo = [low[s]['phases']['post_change']['full_target_rmse'] for s in eligible]
            hi = [high[s]['phases']['post_change']['full_target_rmse'] for s in eligible]
            if float(np.mean(hi)) > float(np.mean(lo)):
                worse_horizon.append({
                    'scenario': scenario, 'model_assumption': model_assumption,
                    'seeds': eligible, 'h20_mean_rad': float(np.mean(lo)),
                    'h50_mean_rad': float(np.mean(hi)),
                    'same_post_change_step_count': all(
                        low[s]['phases']['post_change']['executed_steps']
                        == high[s]['phases']['post_change']['executed_steps'] for s in eligible),
                })
    exits = [{key: record[key] for key in ('scenario', 'seed', 'mode', 'executed_steps',
                                         'termination_reason', 'exit_step', 'exit_seconds')}
             for record in report['records'] if record['termination_reason'] != 'completed']
    return {
        'kind': 'independent_offline_cpu_history_audit', 'passed': True,
        'archive_name': archive_path.name, 'source_commit': commit,
        'audit_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'input_sha256': {name: hashlib.sha256((archive_path / name).read_bytes()).hexdigest()
                         for name in ('report.json', 'trace.csv.gz', 'source_snapshot.zip', 'gates.json')},
        'counts': {
            'trace_rows': len(rows), 'trials': len(trials), 'paired_comparisons': len(report['paired_comparisons']),
            'numerical_checks': checks, 'source_files': len(report['source_sha256']),
            'planned_interaction_steps': report['planned_interaction_steps'],
            'planner_model_transitions': report['total_planner_model_transitions'],
            'diagnostic_one_step_predictions': report['diagnostic_one_step_model_predictions'],
            'completed': sum(r['termination_reason'] == 'completed' for r in report['records']),
            'state_limit_exits': sum(r['termination_reason'] == 'state_limit' for r in report['records']),
            'nonfinite_exits': sum(r['termination_reason'] == 'nonfinite_state' for r in report['records']),
        },
        'max_abs_errors': dict(maximum_error), 'method_outcomes': method_outcomes,
        'unfavorable_outcomes': {'exits': exits, 'all_zero_command_groups': zero_groups,
                                 'h50_worse_post_change_than_h20': worse_horizon},
        'scope': [
            'All checks use archived data, independently written scalar Euler and Git blobs.',
            'No project imports, planner calls, simulation reruns or parameter learning.',
            'Checks data/implementation consistency; not external replication or planner optimality.',
            'Missing early-exit steps remain missing; whole-trajectory and common-prefix metrics are distinct.',
            'Zero commands, low residuals or no exits alone do not demonstrate task success.',
            'Method outcomes average per-seed RMSE; they do not establish universal superiority.',
        ],
    }


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive_path', nargs='?', type=Path,
                        default=repo / 'results/cpu_validation/2026-10-10_history_horizon')
    parser.add_argument('--output', type=Path, help='Write a JSON audit summary after every check passes')
    args = parser.parse_args()
    summary = audit_archive(args.archive_path)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('w', encoding='utf-8', newline='\n') as handle:
            json.dump(summary, handle, indent=2, allow_nan=False)
            handle.write('\n')
    print(json.dumps({'passed': summary['passed'], 'source_commit': summary['source_commit'],
                      'counts': summary['counts'], 'max_abs_errors': summary['max_abs_errors'],
                      'unfavorable_outcomes': summary['unfavorable_outcomes']}, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
