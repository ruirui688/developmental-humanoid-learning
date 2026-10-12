"""Root-only first FR4 report capture; one child invocation, no retry loop."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time

PINS = {
    'fr4_report_common_candidate.py': (25229, '3a23ebb4588ca39978de4176d6a8bee36c6251ba6a4f6f2dd00e190cd6e7576c'),
    'write_fr4a_report_candidate.py': (176, '4a5d58f710abf8abcc1b5a4e9b21819972aafe920398d2038b97c30fa252fa68'),
    'write_fr4b_report_candidate.py': (176, '1991f5e75c3a9bca75a7273c43a02c7918a527692b0431d9f6a324105b2e4ce4'),
}


def main():
    root = Path(__file__).resolve().parents[2]
    candidate = root / 'external/fr4_report_candidate'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--stage', choices=('prediction', 'control'), required=True)
    parser.add_argument('--audit-status', choices=('passed', 'failed'), required=True)
    parser.add_argument('--audit-checks', type=int, required=True)
    parser.add_argument('--audit-failed', type=int, required=True)
    parser.add_argument('--audit-rmse-vectors', type=int, required=True)
    for name in ('control', 'substeps', 'online-scalar', 'offline-scalar'):
        parser.add_argument('--base-' + name, type=int, required=True)
    args = parser.parse_args()
    if not args.write:
        raise ValueError('explicit_write_required_before_report_capture')
    for name, expected in PINS.items():
        data = (candidate / name).read_bytes()
        if (len(data), hashlib.sha256(data).hexdigest()) != expected:
            raise ValueError('frozen_report_source_differs:' + name)
    prefix = 'fr4a' if args.stage == 'prediction' else 'fr4b'
    capture = root / f'external/{prefix}_report_captured_once'
    if capture.exists():
        raise FileExistsError('first_report_capture_exists_no_rerun')
    capture.mkdir()
    command = [sys.executable, str(candidate / f'write_{prefix}_report_candidate.py'), '--write',
               '--audit-status', args.audit_status, '--audit-checks', str(args.audit_checks),
               '--audit-failed', str(args.audit_failed), '--audit-rmse-vectors', str(args.audit_rmse_vectors),
               '--base-control', str(args.base_control), '--base-substeps', str(args.base_substeps),
               '--base-online-scalar', str(args.base_online_scalar), '--base-offline-scalar', str(args.base_offline_scalar)]
    start = time.perf_counter()
    result, error = None, None
    try:
        with (capture / 'stdout.log').open('xb') as out, (capture / 'stderr.log').open('xb') as err:
            result = subprocess.run(command, cwd=root, stdout=out, stderr=err, check=False)
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
    receipt = {'stage': args.stage, 'experiment_id': prefix.upper(), 'first_report_attempt': True,
               'automatic_retry': False, 'command': command,
               'exit_code': result.returncode if result is not None else None,
               'capture_exception': error, 'wall_seconds': time.perf_counter()-start,
               'raw_parameter_audit_or_navigation_reads_by_capture': 0,
               'writer_source_pins': PINS, 'navigation_modified': False}
    with (capture / 'first_execution_receipt.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps(receipt, ensure_ascii=False, allow_nan=False))
    for name in ('stdout.log', 'stderr.log'):
        path = capture / name
        if path.is_file():
            print(path.read_text(encoding='utf-8'))
    raise SystemExit(result.returncode if result is not None else 1)


if __name__ == '__main__':
    main()
