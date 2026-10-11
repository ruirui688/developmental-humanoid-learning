"""Verify new FR0 saved endpoint metrics once; no model or physical calls."""
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
raw = repo / 'results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering/raw'
out = repo / 'external/c4_fr0_new_metrics_check.json'
assert not out.exists()
began, cpu = time.perf_counter(), time.process_time()
pins = {}
def read(name):
    data = (raw / name).read_bytes()
    pins[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    return data

run = json.loads(read('run.json'))
metrics = json.loads(read('metrics.json'))
rows = [json.loads(line) for line in read('trace.jsonl').splitlines()]
groups = defaultdict(list)
for row in rows:
    groups[row['phase']].append(row)
checks, skipped = [], []
def check(label, got, saved):
    if isinstance(got, list):
        passed = len(got) == len(saved) and all(math.isclose(g, s, rel_tol=1e-11, abs_tol=1e-13) for g, s in zip(got, saved))
    elif isinstance(got, float):
        passed = math.isclose(got, saved, rel_tol=1e-11, abs_tol=1e-13)
    else:
        passed = got == saved
    checks.append(dict(check=label, computed=got, saved=saved, passed=passed))
    assert passed, label

check('trace_attempt_count', len(rows), run['cost']['control_call_attempts'])
check('trace_confirmed_substeps', sum(r.get('confirmed_physics_substeps', 0) for r in rows), run['cost']['confirmed_physics_substeps'])
for window in metrics['windows']:
    selected = [r for r in rows if type(r.get('active_index')) is int and window['active_first'] <= r['active_index'] <= window['active_last']]
    check('window_'+window['target']+'_population', len(selected), window['observed_count'])
    if window['available']:
        assert run['trial']['complete'] and len(selected) == 200
        computed = [math.fsum(abs(r['observation_after']['joint_position'][a] - r['target_rad'][a]) for r in selected)/200 for a in range(2)]
        check('window_'+window['target']+'_MAE', computed, window['mae_axis_rad'])
    else:
        assert window['mae_axis_rad'] is None
        skipped.append(dict(window=window['target'], reason='full_trial_or_population_unavailable', partial_ranking=False))

for phase, saved in metrics['phase_effort_and_contacts'].items():
    population = groups[phase]
    native = [r for r in population if r.get('complete_native_endpoint') is True]
    contacts = [r for r in population if r.get('contact_audit_complete') is True]
    paid = sum(r.get('confirmed_physics_substeps', 0) for r in population)
    check(phase+'_paid', paid, saved['confirmed_substeps'])
    check(phase+'_native', len(native), saved['observed_native_endpoints'])
    check(phase+'_contact_population', len(contacts), saved['observed_contact_endpoints'])
    for label, source, power in (
        ('requested_absolute_nm_s_axis', population, 1),
        ('requested_squared_nm2_s_axis', population, 2),
        ('actual_endpoint_sample_absolute_nm_s_axis', native, 1),
        ('actual_endpoint_sample_squared_nm2_s_axis', native, 2),
    ):
        requested = label.startswith('requested_')
        values = []
        for axis in range(2):
            terms = []
            for row in source:
                torque = row['requested_torque'][axis] if requested else row['observation_after']['actuator_torque'][axis]
                count = row.get('confirmed_physics_substeps', 0) if requested else 1
                terms.append(abs(torque)**power * count * .002)
            values.append(math.fsum(terms))
        check(phase+'_'+label, values, saved[label])
    for category, expected in saved['classes'].items():
        endpoint_forces, pair_positives = [], 0
        for row in contacts:
            forces = []
            for pair in row['contacts']['floor_pairs']:
                if pair['category'] != category:
                    continue
                force = max(0., pair['signed_normal_force_n'])
                assert math.isfinite(force)
                assert math.isclose(force, pair['positive_normal_force_n'], rel_tol=1e-13, abs_tol=1e-14)
                forces.append(force)
                pair_positives += force > 0
            endpoint_forces.append(math.fsum(forces))
        positives = sum(v > 0 for v in endpoint_forces)
        for label, computed in (
            ('positive_contact_endpoint_count', positives),
            ('positive_pair_event_count', pair_positives),
            ('observed_positive_duration_s', positives*.002),
            ('endpoint_sample_normal_impulse_ns', math.fsum(endpoint_forces)*.002),
            ('maximum_endpoint_normal_force_n', max(endpoint_forces, default=0.)),
            ('known_positive_fraction_of_paid_substeps', positives/paid if paid else None),
        ):
            check(phase+'_'+category+'_'+label, computed, expected[label])

record = dict(status='passed', checks=checks, skipped=skipped, trace_rows=len(rows),
              source_files=pins, reads=len(pins), read_bytes=sum(v['bytes'] for v in pins.values()),
              wall_seconds=time.perf_counter()-began, cpu_seconds=time.process_time()-cpu,
              old_scientific_metrics_recomputed=False, model_fit_physics_calls=0,
              automatic_retry=False)
with out.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
print(json.dumps({k: v for k, v in record.items() if k not in ('checks', 'skipped', 'source_files')}))
