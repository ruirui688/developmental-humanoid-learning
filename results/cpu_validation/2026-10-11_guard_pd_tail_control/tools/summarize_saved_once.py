"""Copy one verified G first audit into a thin summary; no replay/new metrics.

The E projection structure is retained. G adds the already audited paid tail
request accounting and declares its suite; no model or audit is called here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-source-commit', required=True)
    parser.add_argument('--expected-audit-sha256', required=True)
    parser.add_argument('--expected-raw-manifest-sha256', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    wall, cpu = time.perf_counter(), time.process_time()
    checks = reads = read_bytes = 0
    bindings = {}
    source_bytes = Path(__file__).read_bytes()

    def read(path):
        nonlocal reads, read_bytes
        data = path.read_bytes()
        reads += 1
        read_bytes += len(data)
        bindings[str(path)] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        return data

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError(message)

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    try:
        audit_bytes = read(args.audit)
        require(digest(audit_bytes) == args.expected_audit_sha256, 'first G audit identity')
        audit = json.loads(audit_bytes)
        manifest_bytes = read(args.raw/'manifest.json')
        require(digest(manifest_bytes) == args.expected_raw_manifest_sha256, 'raw manifest identity')
        manifest = json.loads(manifest_bytes)
        metadata_bytes = read(args.raw/'metadata.json')
        metadata = json.loads(metadata_bytes)
        episodes_bytes = read(args.raw/'episodes.json')
        episodes = json.loads(episodes_bytes)
        require(audit['failed'] == 0 and audit['data_consistency_verified'] is True, 'first audit consistent')
        require(audit['development_validation_eligible'] is True, 'first audit verified frozen Git sources')
        require(audit['c4_scientifically_validated'] is False, 'C4 science remains unvalidated')
        require(set(audit['final_gates']) == {'control_hypothesis', 'pd_reference', 'matrix_complete', 'c4_scientific_validation'}, 'exact four development gates')
        require(audit['archive']['source_commit'] == metadata['source_commit'] == args.expected_source_commit, 'source commit binding')
        require(manifest['status'] == metadata['status'] == 'completed', 'first collector batch ended')
        require(metadata['suite'] == 'pd_tail_control_development', 'G suite identity')
        require(isinstance(audit['archive'].get('paid_tail_request_accounting'), dict), 'saved verified G paid tail request accounting exists')
        for name, data in (('metadata.json', metadata_bytes), ('episodes.json', episodes_bytes)):
            require(manifest['files'][name] == {'sha256': digest(data), 'bytes': len(data)}, 'raw member identity '+name)
            require(audit['archive']['input_hashes'][name] == digest(data), 'audit read same raw member '+name)
        require(audit['archive']['input_hashes']['manifest.json'] == digest(manifest_bytes), 'audit read same raw manifest')
        require(len(episodes) == 12 and len(audit['archive']['seeds']) == 3, 'all declared trials and seeds retained')
        for key in ('control_calls_attempted', 'control_steps', 'physics_steps'):
            require(audit['archive']['budget'][key] == metadata[key], 'verified paid budget '+key)
        for key in ('model_updates', 'policy_parameter_updates', 'gain_updates', 'gate_updates'):
            require(audit['archive']['budget'][key] == metadata[key] == 0, 'zero updates '+key)
        for episode in episodes:
            require(episode['trial_id'] in {e['trial_id'] for e in audit['archive']['episodes']}, 'verified trial '+episode['trial_id'])
        result = {'schema_version': 1, 'suite': 'pd_tail_control_development', 'source_commit': args.expected_source_commit,
            'first_audit_sha256': digest(audit_bytes), 'raw_manifest_sha256': digest(manifest_bytes),
            'data_consistency_verified': True, 'binding_checks': {'checks': checks, 'failed': 0},
            'physics_budget': audit['archive']['budget'],
            'outcomes': {k: metadata[k] for k in ('completed_trials', 'terminated_trials', 'exception_trials', 'blocked_trials')},
            'paid_prediction_accounting': audit['archive']['paid_prediction_accounting'],
            'paid_tail_request_accounting': audit['archive']['paid_tail_request_accounting'],
            'restoration_and_cloning': audit['archive']['restoration_and_cloning'],
            'D_binding': audit['archive']['D_binding'], 'pd_binding': audit['archive']['pd_binding'],
            'seeds': audit['archive']['seeds'], 'episodes': audit['archive']['episodes'],
            'final_gates': audit['final_gates'], 'c4_scientifically_validated': False,
            'collector_seconds': {k: metadata[k] for k in ('wall_seconds', 'cpu_seconds')},
            'first_audit_execution': audit['execution'],
            'execution': {'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
                'input_reads': reads, 'input_binary_bytes': read_bytes, 'input_bindings': bindings,
                'physics': 0, 'model_predictions': 0, 'model_updates': 0, 'old_audit_reexecutions': 0, 'git_queries': 0,
                'new_statistical_metrics': 0, 'summary_source_sha256': digest(source_bytes),
                'summary_source_read_bytes': len(source_bytes)},
            'scope': 'G: copies saved verified metrics/gates/paid tail accounting only; no new physical, predictor, fit, planning or audit execution.'}
        with (args.output/'summary.json').open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write('\n')
        print(json.dumps({'binding_checks': result['binding_checks'], 'outcomes': result['outcomes'],
                         'physics_budget': result['physics_budget'], 'execution': result['execution']}, indent=2))
        return 0
    except BaseException as exc:
        with (args.output/'first_failure.json').open('x', encoding='utf-8') as stream:
            json.dump({'checks_completed': checks, 'error': {'type': type(exc).__name__, 'message': str(exc)},
                'input_bindings': bindings, 'input_reads': reads, 'input_binary_bytes': read_bytes,
                'summary_source_read_bytes': len(source_bytes), 'summary_source_sha256': digest(source_bytes),
                'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
                'new_physics': 0, 'new_model_predictions': 0, 'new_updates': 0}, stream, indent=2)
            stream.write('\n')
        raise


if __name__ == '__main__':
    raise SystemExit(main())
