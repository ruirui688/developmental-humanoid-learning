"""One G physical execution from an explicit clean, byte-verified source commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

root = next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--expected-commit', required=True)
args = parser.parse_args()
base = root / 'external/guard_pd_tail_control_20261011_first'
freeze = Path(str(base)+'_runtime_source_freeze.json')
stdout = Path(str(base)+'_stdout.txt')
execution = Path(str(base)+'_execution.json')
assert all(not p.exists() for p in (base, freeze, stdout, execution))
commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()
assert commit == args.expected_commit
assert subprocess.check_output(['git','status','--porcelain','--untracked-files=all'], cwd=root, text=True) == ''
paths = [p.relative_to(root).as_posix() for p in sorted((root/'src/developmental_physics').glob('*.py'))]
paths += [p.relative_to(root).as_posix() for p in sorted((root/'src/developmental_physics/assets').glob('*.xml'))]
paths += [
 'scripts/audit_guard_pd_tail_control.py', 'scripts/audit_guard_lag_control.py',
 'scripts/audit_guard_lag_offline.py', 'scripts/audit_guard_coupled_development.py',
 'scripts/audit_guard_pair_development.py', 'scripts/audit_pair_frozen.py',
 'scripts/audit_local_frozen.py', 'docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md',
 'pyproject.toml',
]
records = {}
for name in paths:
    data = (root/name).read_bytes()
    assert data == subprocess.check_output(['git','show',f'{commit}:{name}'], cwd=root), name
    records[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
with freeze.open('x', encoding='utf-8') as stream:
    json.dump({'source_commit': commit, 'source_files': records, 'clean_worktree': True,
               'source_verification': 'Original working bytes equal explicit HEAD blobs',
               'source_verification_fee': {'working_source_opens': len(paths),
                   'working_source_binary_bytes': sum(value['bytes'] for value in records.values()),
                   'git_blob_queries': len(paths),
                   'git_blob_return_binary_bytes': sum(value['bytes'] for value in records.values()),
                   'git_identity_status_queries': 2},
               'model_predictions': 0, 'updates': 0, 'physics': 0}, stream, indent=2)
    stream.write('\n')
python = root/'external/cpu_physics_env/Scripts/python.exe'
command = [str(python), '-m', 'developmental_physics.pd_tail_control_development', '--output', str(base)]

env = os.environ.copy()
env['PYTHONPATH'] = str(root/'src')
env['OMP_NUM_THREADS'] = '1'
env['OPENBLAS_NUM_THREADS'] = '1'
env['MKL_NUM_THREADS'] = '1'
started = time.perf_counter()
code = error = None
try:
    with stdout.open('xb') as stream:
        code = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT).returncode
except BaseException as exc:
    error = {'type': type(exc).__name__, 'message': str(exc)}
    raise
finally:
    with execution.open('x', encoding='utf-8') as stream:
        json.dump({'source_commit': commit, 'command': command, 'exit_code': code,
                   'wrapper_exception': error, 'wrapper_wall_seconds': time.perf_counter()-started,
                   'wrapper_timing_scope': 'child launch through report snapshot; excludes source/Git preflight, final execution JSON write and printed report read',
                   'stdout_stderr': 'combined original bytes in exclusive stdout file',
                   'repeated': False, 'new_model_updates': 0,
                   'cost_warning': 'Failed or stopped trials retain all paid calls, planning and PD tail work.'}, stream, indent=2)
        stream.write('\n')
print(execution.read_text(encoding='utf-8'))
raise SystemExit(code)
