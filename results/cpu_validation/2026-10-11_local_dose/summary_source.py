"""Draft standard-library summary for audited C2-B development archives.

Do not run before the formal data and authoritative audit schema are complete.
This consumes frozen recorded metrics, computes paired factor differences and
independently applies the predeclared development default-selection rule.
No simulator, RLS fitting/update, model prediction or held-out input is used.
All output is a new file outside the input archive. Source bytes and input
hashes are retained in that file; failed/incomplete trials remain in the report.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sys
import time


SEEDS = [0, 1, 2]
CANDIDATES = ('old_linear4', 'old_hinge5', 'new_linear4', 'new_hinge5')
MODELS = tuple(name+'_mpc' for name in CANDIDATES)
CONTROLLERS = (*MODELS, 'nominal_mpc')
TRAJECTORIES = ('calibration_old', 'calibration_new', 'prediction_low',
                'prediction_full', *CONTROLLERS)
ANCHOR = MODELS[1]
EFFORT_KEYS = ('actual_absolute_nm_s', 'actual_squared_nm2_s')
PHASES = ('prefix', 'calibration', 'prediction', 'control')
PHYSICS_DT = .002


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def require_development(path):
    metadata = load_json(Path(path)/'metadata.json')
    if (metadata.get('split') != 'development' or metadata.get('seeds') != SEEDS
            or metadata.get('pose') != 'supine' or metadata.get('joint_index') != 0
            or metadata.get('integration') != 'endpoint_euler'
            or metadata.get('structures') != ['linear4', 'hinge5']):
        raise ValueError('Only frozen C2-B supine joint0 development0/1/2 may be read.')
    if metadata.get('source_dirty') is not False or metadata.get('source_status') != '':
        raise ValueError('The formal collection source must be clean.')
    if not re.fullmatch(r'[0-9a-f]{40}', metadata.get('source_commit', '')):
        raise ValueError('Invalid formal source commit.')
    return metadata


def input_hashes(path):
    path = Path(path)
    manifest = load_json(path/'manifest.json')
    names = {p.name for p in path.iterdir() if p.is_file() and p.name != 'manifest.json'}
    if set(manifest) != names:
        raise ValueError('Manifest must cover every original input file exactly.')
    required = {'metadata.json', 'episodes.json', 'seed_results.json',
                'trace.jsonl.gz', 'source_snapshot.zip'}
    if not required.issubset(manifest):
        raise ValueError('Missing formal core inputs.')
    hashes = {}
    for name, expected in manifest.items():
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Manifest filenames must remain local.')
        actual = file_hash(path/name)
        if actual != expected:
            raise ValueError('Formal manifest mismatch: '+name)
        hashes[name] = actual
    hashes['manifest.json'] = file_hash(path/'manifest.json')
    return hashes


def complete_metric(evaluation, key):
    value = evaluation.get(key)
    return value if evaluation.get('eligible') is True and finite(value) and value >= 0 else None


def factorial(values):
    """Raw per-seed effects; never treat four controllers as four seeds."""
    if set(values) != set(MODELS) or not all(finite(v) for v in values.values()):
        return None
    lo, ho, ln, hn = (values[name] for name in MODELS)
    return {'hinge_minus_linear': {'old': ho-lo, 'new': hn-ln},
            'new_minus_old': {'linear4': ln-lo, 'hinge5': hn-ho},
            'difference_of_differences': (hn-ho)-(ln-lo)}


def independent_selection(seeds):
    """Protocol section4; exact comparisons, no tuned epsilon or partial RMSE."""
    if len(seeds) != 3 or [s['seed'] for s in seeds] != SEEDS:
        raise ValueError('All three development seed outcomes are required.')
    candidates = []
    for index, model in enumerate(MODELS):
        rows = []
        for seed in seeds:
            ev = seed['evaluations']
            candidate = ev.get(model, {})
            anchor = ev.get(ANCHOR, {})
            cr = complete_metric(candidate, 'tracking_rmse_rad')
            ar = complete_metric(anchor, 'tracking_rmse_rad')
            efforts = [{key: group.get('control_effort', {}).get(key) for key in EFFORT_KEYS}
                       for group in (candidate, anchor)]
            complete = (cr is not None and ar is not None
                        and candidate.get('actual_effort_complete') is True
                        and anchor.get('actual_effort_complete') is True
                        and all(finite(v) and v >= 0 for e in efforts for v in e.values()))
            predictions = {}
            for trajectory in ('prediction_low', 'prediction_full'):
                prediction = ev.get(trajectory, {})
                errors = prediction.get('velocity_prediction_rmse', {})
                cv, av = errors.get(model), errors.get(ANCHOR)
                legal = (prediction.get('eligible') is True and finite(cv) and finite(av)
                         and cv >= 0 and av >= 0)
                predictions[trajectory] = {'candidate_rmse': cv, 'anchor_rmse': av,
                                           'complete': legal, 'non_worse': legal and cv <= av}
                complete = complete and legal
            rows.append({'seed': seed['seed'], 'complete': complete,
                         'tracking_non_worse': complete and cr <= ar,
                         'candidate_tracking_rmse_rad': candidate.get('tracking_rmse_rad'),
                         'anchor_tracking_rmse_rad': anchor.get('tracking_rmse_rad'),
                         'candidate_control_effort': efforts[0], 'anchor_control_effort': efforts[1],
                         'prediction_pairs': predictions})
        complete = all(r['complete'] for r in rows)
        candidate_mean = sum(r['candidate_tracking_rmse_rad'] for r in rows)/3 if complete else None
        anchor_mean = sum(r['anchor_tracking_rmse_rad'] for r in rows)/3 if complete else None
        improvement = 1-candidate_mean/anchor_mean if complete and anchor_mean > 0 else None
        effort_gates = {}
        for key in EFFORT_KEYS:
            cm = sum(r['candidate_control_effort'][key] for r in rows)/3 if complete else None
            am = sum(r['anchor_control_effort'][key] for r in rows)/3 if complete else None
            change = ((0. if cm == 0. else None) if am == 0. else cm/am-1.) if complete else None
            effort_gates[key] = {'candidate_mean': cm, 'anchor_mean': am, 'relative_increase': change,
                                'passed': complete and cm <= 1.05*am}
        passed = (index != 1 and complete and improvement is not None and improvement >= .05
                  and all(r['tracking_non_worse'] and all(p['non_worse'] for p in r['prediction_pairs'].values())
                          for r in rows) and all(g['passed'] for g in effort_gates.values()))
        candidates.append({'candidate_index': index, 'candidate': CANDIDATES[index],
                           'model': model, 'anchor': index == 1,
                           'complete': complete, 'passed_new_candidate_gate': passed,
                           'candidate_tracking_raw_mean': candidate_mean,
                           'anchor_tracking_raw_mean': anchor_mean,
                           'tracking_mean_improvement': improvement,
                           'actual_effort_gates': effort_gates, 'per_seed': rows,
                           'model_dimension': 4 if 'linear4' in model else 5})
    passed = [c for c in candidates if c['passed_new_candidate_gate']]
    chosen = min(passed, key=lambda c: (c['candidate_tracking_raw_mean'],
                 c['actual_effort_gates']['actual_squared_nm2_s']['candidate_mean'],
                 c['model_dimension'], c['candidate_index'])) if passed else candidates[1]
    return {'selected_candidate_index': chosen['candidate_index'],
            'selected_candidate': chosen['candidate'], 'selected_model': chosen['model'],
            'new_candidate_adopted': bool(passed), 'candidates': candidates,
            'claim_boundary': 'Development default selection only; no unseen superiority, risk or skill claim.'}


def verify_selection(independent, audit):
    """Normalize suffixes explicitly and reconcile both scientific and validated choices."""
    formal = audit['development_adoption_gate']
    if formal.get('anchor') != 'old_hinge5' or formal.get('candidate_order') != list(CANDIDATES):
        raise ValueError('Authoritative candidate order or anchor changed.')
    pairs = [('passed', independent['new_candidate_adopted']),
             ('selected_candidate', independent['selected_candidate']),
             ('data_consistency_verified', True)]
    historical = audit.get('historical_anchor', {}).get('exact_replay_verified') is True
    pairs.append(('historical_replay_verified', historical))
    # Successful audit source-git checks are part of this archive's verification;
    # the source commit and every original input are also checked by this summary.
    git_enabled = audit.get('execution', {}).get('source_git_verification_enabled')
    if type(git_enabled) is not bool:
        raise ValueError('Authoritative audit must disclose whether Git source verification was enabled.')
    validated = independent['new_candidate_adopted'] and historical and git_enabled
    selected = independent['selected_candidate'] if validated else 'old_hinge5'
    pairs.extend([('validated_pass', validated), ('validated_selected_candidate', selected)])
    for key, value in pairs:
        if formal.get(key) != value:
            raise ValueError('Independent selection mismatch: '+key)
    recorded = formal.get('candidates', [])
    if len(recorded) != len(CANDIDATES):
        raise ValueError('Incomplete authoritative candidate gate ledger.')
    for own, authoritative in zip(independent['candidates'], recorded):
        checks = {
            'candidate_id': own['candidate_index'], 'candidate': own['candidate'],
            'dimension': own['model_dimension'], 'evaluated': own['complete'],
            'passed': own['passed_new_candidate_gate'],
            'anchor_raw_tracking_mean': own['anchor_tracking_raw_mean'],
            'candidate_raw_tracking_mean': own['candidate_tracking_raw_mean'],
            'tracking_mean_improvement': own['tracking_mean_improvement'],
            'actual_effort_gates': own['actual_effort_gates'],
        }
        for key, value in checks.items():
            if authoritative.get(key) != value:
                raise ValueError('Independent candidate gate mismatch: '+own['candidate']+'/'+key)
        official_rows = authoritative.get('per_seed', [])
        if [r.get('seed') for r in official_rows] != SEEDS:
            raise ValueError('Incomplete authoritative candidate seed ledger.')
        for row, saved in zip(own['per_seed'], official_rows):
            for key, value in {
                'seed': row['seed'], 'complete_pair': row['complete'],
                'tracking_non_worse': row['tracking_non_worse'],
                'anchor_tracking_rmse_rad': row['anchor_tracking_rmse_rad'],
                'candidate_tracking_rmse_rad': row['candidate_tracking_rmse_rad'],
            }.items():
                if saved.get(key) != value:
                    raise ValueError('Independent per-seed selection mismatch: '+own['candidate']+'/'+key)
            for kind, prediction in row['prediction_pairs'].items():
                expected = {'complete': prediction['complete'], 'anchor_rmse': prediction['anchor_rmse'],
                            'candidate_rmse': prediction['candidate_rmse'], 'passed': prediction['non_worse']}
                if saved.get('prediction_gates', {}).get(kind) != expected:
                    raise ValueError('Independent prediction gate mismatch: '+own['candidate']+'/'+kind)
    return {'all_candidate_gates_exactly_equal': True,
            'selected_candidate': independent['selected_candidate'], 'validated_pass': validated,
            'validated_selected_candidate': selected,
            'source_git_verification_enabled': git_enabled,
            'name_semantics': 'Candidate names omit _mpc; controller/evaluation names append _mpc.'}


def reconcile_diagnostic_denominators(seeds):
    """Audit descriptive fractions without treating unknown telemetry as zero risk."""
    output = []
    for seed in seeds:
        ev = seed['evaluations']
        by_kind = {}
        for kind, evaluation in ev.items():
            full = evaluation['full_risk']
            phases = evaluation['phase_risk']
            missing = evaluation['phase_risk_missing_substeps']
            if set(phases) != set(PHASES) or set(missing) != set(PHASES):
                raise ValueError('Unknown or missing risk phase.')
            for key in ('physical_substeps', 'returned_endpoint_samples', 'guarded_substeps', 'target_guarded_substeps'):
                if full[key] != sum(phases[p][key] for p in PHASES):
                    raise ValueError('Risk denominator phase sum mismatch: '+kind+'/'+key)
            if (sum(missing.values()) != evaluation['missing_risk_substeps']
                    or full['physical_substeps']+sum(missing.values()) != evaluation['paid_budget']['physics_steps']):
                raise ValueError('Paid risk substeps do not reconcile: '+kind)
            diagnostics = {}
            for phase in PHASES:
                risk = phases[phase]
                known = risk['physical_substeps']
                unknown = missing[phase]
                general, target = risk['guarded_substeps'], risk['target_guarded_substeps']
                if (any(type(v) is not int or v < 0 for v in (known, unknown, general, target, risk['returned_endpoint_samples']))
                        or not 0 <= target <= general <= known):
                    raise ValueError('Invalid saved risk denominator: '+kind+'/'+phase)
                diagnostics[phase] = {
                    'known_substeps': known, 'unknown_paid_substeps': unknown,
                    'paid_substeps': known+unknown,
                    'known_duration_seconds': known*PHYSICS_DT,
                    'returned_endpoint_samples': risk['returned_endpoint_samples'],
                    'guarded_fraction_of_known_substeps': general/known if known else None,
                    'target_guarded_fraction_of_known_substeps': target/known if known else None,
                    'risk_telemetry_has_no_missing_substeps': unknown == 0,
                }
            coverage = evaluation.get('state_coverage')
            if coverage is not None:
                calibration = ev.get('calibration_'+kind.split('_')[0], {})
                count = coverage['control_native_samples']
                cal_count = coverage['calibration_native_samples']
                if (type(count) is not int or type(cal_count) is not int or count < 0 or cal_count < 0
                        or count > phases['control']['returned_endpoint_samples']
                        or cal_count > calibration.get('phase_risk', {}).get('calibration', {}).get('returned_endpoint_samples', 0)):
                    raise ValueError('Coverage denominator exceeds returned active inputs: '+kind)
                if evaluation.get('eligible') is True and count != 200:
                    raise ValueError('Complete controller coverage requires 200 input states.')
                if calibration.get('eligible') is True and cal_count != 300:
                    raise ValueError('Complete calibration coverage requires 300 input states.')
                if coverage.get('available') is True:
                    if cal_count == 0:
                        raise ValueError('Available coverage lacks calibration inputs.')
                    for prefix in ('q', 'v', 'either'):
                        n = coverage[prefix+'_outside_count']
                        fraction = coverage[prefix+'_outside_fraction']
                        expected = n/count if count else None
                        if type(n) is not int or not 0 <= n <= count or fraction != expected:
                            raise ValueError('Coverage fraction does not match its denominator: '+kind+'/'+prefix)
                    if not max(coverage['q_outside_count'], coverage['v_outside_count']) <= coverage['either_outside_count'] <= min(count, coverage['q_outside_count']+coverage['v_outside_count']):
                        raise ValueError('Coverage union count violates its marginal bounds.')
                elif cal_count != 0:
                    raise ValueError('Unavailable coverage must lack calibration inputs.')
            by_kind[kind] = {'phase_denominators': diagnostics,
                            'coverage': coverage,
                            'coverage_semantics': 'Complete active input states only; strict q/v envelope exclusions; nearest q-only distance in rad. Empty control has no fraction. Partial-return endpoints can enter risk/conditional counts, never complete coverage.',
                            'risk_semantics': 'Fractions use recorded physical substeps. Unknown paid substeps are separate; returned native endpoints are not substep joint-speed maxima.'}
        output.append({'seed': seed['seed'], 'trials': by_kind})
    return output


def controller_means(seeds):
    output = {}
    for model in CONTROLLERS:
        rows = [s['evaluations'].get(model, {}) for s in seeds]
        complete = all(complete_metric(row, 'tracking_rmse_rad') is not None
                       and row.get('actual_effort_complete') is True
                       and all(finite(row.get('control_effort', {}).get(key))
                               and row['control_effort'][key] >= 0 for key in EFFORT_KEYS)
                       for row in rows)
        output[model] = {'all_three_complete': complete,
                        'tracking_raw_rmse_mean_rad': sum(r['tracking_rmse_rad'] for r in rows)/3 if complete else None,
                        'control_actual_effort_raw_means': {
                            key: sum(r['control_effort'][key] for r in rows)/3 if complete else None
                            for key in EFFORT_KEYS}}
    return output


def numeric_leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from numeric_leaves(item, prefix+'/'+key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from numeric_leaves(item, prefix+'/'+str(index))
    elif finite(value):
        yield prefix.lstrip('/'), value


def factorial_metric_matrices(evaluations):
    matrices = {'tracking_rmse_rad': {m: complete_metric(evaluations.get(m, {}), 'tracking_rmse_rad') for m in MODELS}}
    for key in EFFORT_KEYS:
        matrices[key] = {m: evaluations.get(m, {}).get('control_effort', {}).get(key)
                        if evaluations.get(m, {}).get('eligible') is True
                        and evaluations.get(m, {}).get('actual_effort_complete') is True else None for m in MODELS}
    for trajectory in ('prediction_low', 'prediction_full'):
        ep = evaluations.get(trajectory, {})
        for key in ('velocity_prediction_rmse', 'position_prediction_rmse'):
            matrices[trajectory+'/'+key] = {m: ep.get(key, {}).get(m) if ep.get('eligible') is True else None for m in MODELS}
    for model in MODELS:
        trial = evaluations.get(model, {})
        if trial.get('eligible') is not True:
            continue
        controller_metrics = {
            'own_velocity_prediction_rmse': trial['velocity_prediction_rmse'].get(model),
            'own_position_prediction_rmse': trial['position_prediction_rmse'].get(model),
            'saturated_control_steps': trial['saturated_control_steps'], 'planner_fallbacks': trial['planner_fallbacks'],
        }
        if trial.get('risk_telemetry_complete') is True:
            controller_metrics.update(full_risk=trial['full_risk'], phase_risk=trial['phase_risk'])
        for label, value in numeric_leaves(controller_metrics):
            matrices.setdefault(label, {m: None for m in MODELS})[model] = value
    return matrices


def three_seed_factorial_means(effects):
    labels = set.intersection(*(set(row['raw_per_seed_metrics']) for row in effects))
    summaries = {}
    for label in sorted(labels):
        values = [row['raw_per_seed_metrics'][label] for row in effects]
        complete = all(set(v) == set(MODELS) and all(finite(x) for x in v.values()) for v in values)
        means = {m: sum(v[m] for v in values)/3 for m in MODELS} if complete else None
        summaries[label] = {'all_three_four_group_matrices_complete': complete,
                            'raw_three_seed_means': means,
                            'factorial_effects_of_raw_means': factorial(means) if complete else None}
    return summaries


def summarize(archive_path, audit_path):
    wall = time.perf_counter()
    cpu = time.process_time()
    archive_path, audit_path = Path(archive_path).resolve(), Path(audit_path).resolve()
    # Refuse foreign scope before opening trace or audit evaluation contents.
    metadata = require_development(archive_path)
    hashes = input_hashes(archive_path)
    audit_hash = file_hash(audit_path)
    audit = load_json(audit_path)
    if audit.get('failed') != 0 or type(audit.get('checks')) is not int or audit['checks'] <= 0:
        raise ValueError('An independent successful data-integrity audit is required; benefit may still fail.')
    recorded = audit.get('archive', {})
    if (recorded.get('split') != 'development'
            or recorded.get('source_commit') != metadata['source_commit']
            or recorded.get('input_hashes') != hashes
            or Path(recorded.get('path', '')).resolve() != archive_path):
        raise ValueError('Audit does not match this exact formal input archive.')
    seeds = recorded['seeds']
    if len(seeds) != 3 or [s['seed'] for s in seeds] != SEEDS:
        raise ValueError('Missing or reordered development seed outcomes.')
    effects = []
    for seed in seeds:
        evaluations = seed['evaluations']
        metrics = factorial_metric_matrices(evaluations)
        effects.append({'seed': seed['seed'], 'raw_per_seed_metrics': metrics,
                        'factorial_effects': {name: factorial(values) for name, values in metrics.items()}})
    selection = independent_selection(seeds)
    selection_verification = verify_selection(selection, audit)
    denominators = reconcile_diagnostic_denominators(seeds)
    script_bytes = Path(__file__).read_bytes()
    report = {
        'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': __doc__, 'source_commit': metadata['source_commit'], 'split': 'development',
        'source_archive_path': str(archive_path), 'input_hashes': hashes,
        'audit_path': str(audit_path), 'audit_sha256': audit_hash, 'audit_checks': audit['checks'],
        'summary_source_sha256': hashlib.sha256(script_bytes).hexdigest(),
        'summary_source_bytes_base64': base64.b64encode(script_bytes).decode('ascii'),
        'formal_collection_budget': {key: metadata[key] for key in
            ('control_calls_attempted', 'control_steps', 'physics_steps', 'model_updates', 'wall_seconds')},
        'planned_budget': {'trials': 27, 'maximum_control_calls': 8100,
                          'maximum_physical_substeps': 81000, 'full_calibration_rls_updates': 3600},
        'all_formal_trials_successful': metadata['all_trials_successful'],
        'controller_raw_means': controller_means(seeds),
        'per_seed_factorial_effects': effects,
        'three_seed_factorial_raw_means': three_seed_factorial_means(effects),
        'independent_development_selection': selection,
        'selection_reconciliation': selection_verification,
        'diagnostic_denominator_reconciliation': denominators,
        'audited_development_adoption_gate': audit['development_adoption_gate'],
        'audited_budget': recorded['budget'], 'audited_phase_budget': recorded['phase_budget'],
        'physical_calibration_transfers': recorded['physical_calibration_transfers'],
        'sample_semantics': recorded['sample_semantics'],
        'audited_rollout_semantics': audit['rollout_semantics'],
        'conditional_metric_semantics': 'All reported amplitude/block/target/switch/hold bins are retained per seed. returned_transition_count includes returned partial endpoints; known_substep_effort is not a per-transition average. No pooled bins or selected favorable blocks.',
        'audited_seed_details': seeds,
        'aggregation_semantics': 'Three raw per-seed RMSE means; no pooling of overlapping windows or controller trajectories as extra seeds. Missing or failed groups are retained, complete means withheld.',
        'execution': {
            'timing_scope': 'summarize entry through metrics, source-byte capture, unchanged-input validation and report assembly; excludes imports and final serialization/writing',
            'python': sys.version, 'platform': platform.platform(), 'third_party_dependencies': [],
            'physical_simulation_calls': 0, 'real_parameter_fitting_calls': 0,
            'real_parameter_updates': 0, 'new_environment_interactions': 0},
    }
    if input_hashes(archive_path) != hashes or file_hash(audit_path) != audit_hash:
        raise ValueError('Read-only summary inputs changed during assembly.')
    report['execution'].update(wall_seconds=time.perf_counter()-wall,
                               cpu_seconds=time.process_time()-cpu)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    archive, audit = args.archive.resolve(), args.audit.resolve()
    if output.exists() or output.is_relative_to(archive) or output == audit:
        parser.error('Refusing overwrite or output inside the original input archive.')
    report = summarize(archive, audit)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'report': str(output), 'selected_model': report['independent_development_selection']['selected_model'],
                      'new_candidate_adopted': report['independent_development_selection']['new_candidate_adopted'],
                      'execution': report['execution']}))


if __name__ == '__main__':
    main()
