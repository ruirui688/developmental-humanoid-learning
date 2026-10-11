"""One byte-bound saved D description; no model, fit, rollout, audit or Git."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import time


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--audit', required=True)
    parser.add_argument('--expected-auditor-sha256', required=True)
    parser.add_argument('--read-accounting-reconciliation')
    parser.add_argument('--expected-reconciliation-tool-sha256')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    source, output = Path(args.input), Path(args.output)
    output.mkdir(exist_ok=False)
    cache, checks = {}, 0

    def read(path):
        key = str(path.resolve())
        if key not in cache:
            cache[key] = path.read_bytes()
        return cache[key]

    def require(value, label):
        nonlocal checks
        checks += 1
        if not value:
            raise ValueError(label)

    manifest = json.loads(read(source/'manifest.json'))
    require(set(manifest['files']) == {p.name for p in source.iterdir() if p.is_file()}-{'manifest.json'}, 'Exact D file coverage')
    for name, record in manifest['files'].items():
        require(Path(name).name == name, 'Plain output filename')
        blob = read(source/name)
        require(record == {'sha256': sha(blob), 'bytes': len(blob)}, 'Saved D byte identity: '+name)
    audit = json.loads(read(Path(args.audit)))
    correction = None
    if args.read_accounting_reconciliation:
        correction_path = Path(args.read_accounting_reconciliation)
        correction = json.loads(read(correction_path))
        require(audit['failed'] == 1 and audit['violations'] == [{'check':'exact_source_or_causal_identity','location':'runner_original_read_accounting'}], 'Only original disclosed read-accounting discrepancy')
        require(correction['first_audit_sha256'] == sha(read(Path(args.audit))) and correction['first_audit_failed'] == 1, 'Original failed audit retained and bound')
        require(correction['sole_original_violation_location'] == 'runner_original_read_accounting', 'Supplement limited to the original location')
        require(correction['failed'] == 0 and correction['effective_data_consistency_verified'] is True, 'Independent read-accounting supplement passed')
        require(correction['tool_sha256'] == args.expected_reconciliation_tool_sha256, 'Expected independent supplemental source')
    else:
        require(audit['failed'] == 0, 'First independent audit passed')
    require(audit['audit_script_sha256'] == args.expected_auditor_sha256, 'Expected first auditor identity')
    audited_hashes = audit.get('input_file_sha256', audit.get('file_sha256'))
    require(isinstance(audited_hashes, dict), 'First audit byte binding available')
    for name in (*manifest['files'], 'manifest.json'):
        require(audited_hashes.get(name) == sha(read(source/name)), 'First audit original D byte binding: '+name)
        if correction:
            require(correction['input_file_sha256'].get(name) == audited_hashes.get(name), 'Supplement bound to the same D bytes: '+name)
    run = json.loads(read(source/'run.json'))
    summary = json.loads(read(source/'summary.json'))
    require(summary['no_scientific_gates_or_ranking'] is True and summary['same_development_data'] is True, 'Development-only description')
    require(run['status'] == manifest['status'], 'Saved execution status')
    for key in ('new_physics_control_calls', 'new_physics_substeps', 'original9_refits', 'mpc_select_calls', 'policy_gain_gate_updates', 'pd_teacher_calls', 'real_robot_calls'):
        require(run[key] == 0, 'Original zero-cost boundary: '+key)
    fields = ['seed','trial_kind','original_status','original_completed','predictor','h','axis','group','complete_window_count','mathematical_failure_count','unavailable_model_window_count','successful_endpoint_count','available','reason','q_rmse','q_bias','q_max_error','v_rmse','v_bias','v_max_error']
    rows = []
    for trial in summary['trials']:
        for item in trial['metrics']:
            row = {key: item.get(key) for key in fields}
            row.update(seed=trial['seed'], trial_kind=trial['kind'], original_status=trial['original_status'], original_completed=trial['original_completed'])
            for key in ('q','v'):
                metric = item[key]
                row[key+'_rmse'] = metric['rmse'] if metric else None
                row[key+'_bias'] = metric['signed_bias_prediction_minus_observation'] if metric else None
                row[key+'_max_error'] = metric['maximum_absolute_error'] if metric else None
            rows.append(row)
    with (output/'all_saved_metrics.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    result = {'schema_version':1, 'source_commit':run['execution_context']['verified_source_commit'],
        'first_audit_sha256':sha(read(Path(args.audit))), 'expected_auditor_sha256':args.expected_auditor_sha256,
        'original_input_sha256':{name:sha(read(source/name)) for name in (*manifest['files'],'manifest.json')},
        'first_audit':{key:audit[key] for key in ('checks','failed','maximum_recomputation_difference')},
        'read_accounting_reconciliation':correction,
        'read_accounting_reconciliation_sha256':sha(read(correction_path)) if correction else None,
        'effective_data_consistency_verified':True,
        'status':run['status'], 'calibrations':run['calibrations'], 'cost_ledger':run['cost_ledger'],
        'original_execution':run['execution'], 'predictors':summary['predictors'], 'horizons':summary['horizons'],
        'trials':summary['trials'], 'no_scientific_gates_or_ranking':True, 'same_development_data':True,
        'binding_checks':{'checks':checks,'failed':0}, 'metric_rows_copied':len(rows),
        'read_cost':{'unique_input_files':len(cache),'input_bytes_cached':sum(map(len,cache.values()))},
        'execution':{'wall_seconds':time.perf_counter()-started_wall,'cpu_seconds':time.process_time()-started_cpu,
            'physical_calls':0,'model_constructions':0,'new_predictions':0,'model_updates':0,'audit_reexecutions':0,'git_calls':0,
            'scope':'Only original-byte bindings and saved-metric copying; excludes final writes'}}
    save(output/'summary.json',result)
    save(output/'manifest.json',{'files':{p.name:{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size} for p in output.iterdir() if p.is_file()}})
    print(json.dumps({'binding_checks':result['binding_checks'],'rows_copied':len(rows),'execution':result['execution']}))


if __name__ == '__main__':
    main()
