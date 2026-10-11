"""First fixed F description from clean source; no new model or physics."""
import argparse
import json
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-commit', required=True)
parser.add_argument('--source-manifest-sha256', required=True)
args = parser.parse_args()
output = root / 'external/guard_native_context_20261011_first'
stdout = Path(str(output) + '_stdout.txt')
execution = Path(str(output) + '_execution.json')
assert not any(path.exists() for path in (output, stdout, execution))
commit_bytes = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root)
status_bytes = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root)
assert commit_bytes.decode('ascii').strip() == args.expected_commit
assert status_bytes == b''
command = ['D:/Python3.10/python.exe', 'scripts/diagnose_guard_native_context.py',
    '--archive', 'results/cpu_validation/2026-10-11_guard_lag_control',
    '--binding', 'configs/cpu/guard_native_context_binding.json',
    '--source-manifest-sha256', args.source_manifest_sha256, '--output', str(output)]
wall, cpu = time.perf_counter(), time.process_time()
code = error = None
try:
    with stdout.open('xb') as stream:
        code = subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT).returncode
except BaseException as exc:
    error = {'type': type(exc).__name__, 'message': str(exc)}
    raise
finally:
    with execution.open('x', encoding='utf-8') as stream:
        json.dump({'source_commit': args.expected_commit, 'source_manifest_sha256': args.source_manifest_sha256,
            'command': command, 'exit_code': code, 'wrapper_exception': error, 'repeated': False,
            'wrapper_wall_seconds': time.perf_counter()-wall, 'wrapper_cpu_seconds': time.process_time()-cpu,
            'timing_scope': 'subprocess launch through completion; excludes preflight and final execution record write',
            'preflight_git_reads': 2, 'preflight_git_binary_return_bytes': len(commit_bytes) + len(status_bytes),
            'new_physics': 0, 'new_model_predictions': 0, 'new_updates': 0, 'old_audit_runs': 0}, stream, indent=2)
        stream.write('\n')
print(execution.read_text(encoding='utf-8'))
raise SystemExit(code)
