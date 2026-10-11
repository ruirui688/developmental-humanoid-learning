"""One independent G first audit, guarded by an explicit clean source commit.

This wrapper is prepared without archive execution. Run it only after root
has collected the once-only frozen G physics matrix and authorizes first audit.
Every output path is exclusive; a reservation prevents a second attempt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-source-commit', required=True)
    parser.add_argument('--python', type=Path, default=Path('D:/Python3.10/python.exe'))
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.expected_source_commit):
        parser.error('expected source commit must be one exact lowercase 40-digit Git SHA')
    root = Path(__file__).resolve().parents[2]
    target = root/'external/guard_pd_tail_control_20261011_first_audit.json'
    execution = root/'external/guard_pd_tail_control_20261011_first_audit_execution.json'
    stdout = root/'external/guard_pd_tail_control_20261011_first_audit_stdout.txt'
    reservation = root/'external/guard_pd_tail_control_20261011_first_audit_reservation'
    if any(p.exists() for p in (target, execution, stdout, reservation)):
        raise FileExistsError('refuse to replace any first G audit artifact or reservation')
    wall, cpu = time.perf_counter(), time.process_time()
    reservation.mkdir(exist_ok=False)
    command = [str(args.python), 'scripts/audit_guard_pd_tail_control.py',
               '--input', 'external/guard_pd_tail_control_20261011_first',
               '--output', str(target)]
    commit = None
    code = error = None
    audit_started = False
    source_reads = []
    audit_output_identity = None
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        if commit != args.expected_source_commit:
            raise RuntimeError('G first audit source commit differs from explicit expected commit')
        status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root, text=True)
        if status:
            raise RuntimeError('G first audit requires a clean working tree')
        for path in (Path(__file__).resolve(), root/'scripts/audit_guard_pd_tail_control.py'):
            data = path.read_bytes()
            record = {'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            source_reads.append(record)
            preserved = reservation/'source_snapshot'/record['path']
            preserved.parent.mkdir(parents=True, exist_ok=True)
            preserved.write_bytes(data)
        with stdout.open('xb') as stream:
            audit_started = True
            code = subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT).returncode
        if target.exists():
            data = target.read_bytes()
            audit_output_identity = {'path': target.relative_to(root).as_posix(),
                                     'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    except BaseException as exc:
        error = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        record = {'schema_version': 1, 'suite': 'pd_tail_control_development',
            'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'source_commit': commit, 'expected_source_commit': args.expected_source_commit,
            'command': command, 'exit_code': code, 'wrapper_exception': error,
            'audit_started': audit_started,
            'wrapper_wall_seconds': time.perf_counter()-wall,
            'wrapper_cpu_seconds_excluding_child': time.process_time()-cpu,
            'source_snapshot_identity': source_reads, 'first_audit_output_identity': audit_output_identity,
            'explicit_wrapper_source_read_bytes': sum(x['bytes'] for x in source_reads),
            'explicit_wrapper_audit_output_read_bytes': 0 if audit_output_identity is None else audit_output_identity['bytes'],
            'read_scope': 'source hash/copy and one saved first audit output hash; subprocess audit has its own separate read/math accounting',
            'wall_scope': 'exclusive reservation/preflight/source copy through first audit completion and output hashing; excludes execution JSON write',
            'repeated': False, 'new_physics': 0, 'new_model_updates': 0, 'old_audit_reexecutions': 0,
            'reservation': reservation.relative_to(root).as_posix()}
        with execution.open('x', encoding='utf-8') as stream:
            json.dump(record, stream, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps(record, indent=2, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
