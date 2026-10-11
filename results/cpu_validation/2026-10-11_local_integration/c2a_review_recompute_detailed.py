"""A second read-only review retaining every comparison and unchanged input hashes.

Uses the captured original arithmetic source, with only labelled-comparison
recording added. No simulator, fit/update function or held-out input is imported.
This is a new review run, not reconstructed first-run output.
"""
import hashlib
import json
from pathlib import Path
import sys
import time


def main():
    wall = time.perf_counter()
    cpu = time.process_time()
    source_path = Path(__file__).with_name('c2a_review_recompute_initial.py')
    output_path = Path(__file__).with_name('c2a_review_recompute_detailed.json')
    if output_path.exists():
        raise FileExistsError(output_path)
    source_bytes = source_path.read_bytes()
    source = source_bytes.decode('utf-8')
    replacements = [
        ("def near(a,b):\n    differences.append(abs(a-b)); assert abs(a-b)<=1e-12,(a,b)",
         "def near(a,b,label):\n    difference=abs(a-b)\n    differences.append(difference)\n    comparison_records.append({'label':label,'independent_value':a,'recorded_value':b,'absolute_difference':difference,'tolerance':1e-12,'passed':difference<=1e-12})\n    assert difference<=1e-12,(label,a,b)"),
        ("near(tracking,ev['tracking_rmse_rad']); near(tracking,ae['tracking_rmse_rad'])",
         "near(tracking,ev['tracking_rmse_rad'],f'{seed}/{kind}/tracking/raw_summary'); near(tracking,ae['tracking_rmse_rad'],f'{seed}/{kind}/tracking/audit')"),
        ("for key,val in effort.items(): near(val,ev['control_effort'][key]); near(val,ae['control_effort'][key])",
         "for key,val in effort.items(): near(val,ev['control_effort'][key],f'{seed}/{kind}/effort/{key}/raw_summary'); near(val,ae['control_effort'][key],f'{seed}/{kind}/effort/{key}/audit')"),
        ("near(risk[scope][k],ref[rk])",
         "near(risk[scope][k],ref[rk],f'{seed}/{kind}/risk/{scope}/{k}/audit')"),
        ("for key,val in values.items():near(val,ref[key])",
         "for key,val in values.items():near(val,ref[key],f'{seed}/{kind}/horizon{h}/{name}/{key}/audit')"),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError('Original arithmetic source no longer matches exact capture.')
        source = source.replace(before, after)
    records = []
    namespace = {'comparison_records': records, 'print': lambda *args, **kwargs: None}
    exec(compile(source, str(source_path), 'exec'), namespace)
    if len(records) != 1440 or len({r['label'] for r in records}) != 1440:
        raise AssertionError('Incomplete or duplicate comparison ledger.')
    report = {
        'schema_version': 1,
        'purpose': __doc__,
        'source_capture': 'Second run with explicit labels added to the first inline source; original incomplete first-run stdout is not reconstructed.',
        'source_sha256': {
            source_path.name: hashlib.sha256(source_bytes).hexdigest(),
            Path(__file__).name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        'executed_transformed_source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'input_path': str(namespace['base'].resolve()),
        'input_hashes': namespace['hash_before'],
        'audit_path': str(namespace['audpath'].resolve()),
        'audit_sha256': hashlib.sha256(namespace['audpath'].read_bytes()).hexdigest(),
        'numeric_comparisons': len(records),
        'failed_comparisons': sum(not r['passed'] for r in records),
        'maximum_difference': max(r['absolute_difference'] for r in records),
        'comparison_records': records,
        'independent_primary_metrics': namespace['primary'],
        'independent_rollouts': [{'seed': seed, 'trajectory': kind, 'horizons': values}
                                 for (seed, kind), values in namespace['rollouts'].items()],
        'execution': {
            'python': sys.version,
            'wall_seconds': time.perf_counter()-wall,
            'cpu_seconds': time.process_time()-cpu,
            'timing_scope': 'main entry through report assembly; excludes imports, JSON serialization and file writing',
            'physical_simulation_calls': 0,
            'real_parameter_fitting_calls': 0,
            'real_parameter_updates': 0,
            'new_environment_interactions': 0,
        },
    }
    with output_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'report': str(output_path), 'checks': report['numeric_comparisons'],
                      'failed': report['failed_comparisons'], 'maximum_difference': report['maximum_difference'],
                      'source_sha256': report['source_sha256'], 'input_hashes': report['input_hashes'],
                      'audit_sha256': report['audit_sha256'], 'execution': report['execution']}, indent=2))


if __name__ == '__main__':
    main()
