"""Seal E engineering originals without replaying any mathematics or physics."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
root = Path(__file__).resolve().parents[1]
destination = root/'results/cpu_validation/2026-10-11_guard_lag_control_preparation'
assert not destination.exists()
groups = {
    'mpc_staging':'external/c4_lag_mpc_staging',
    'runner_staging':'external/c4_lag_control_runner_staging',
    'audit_staging':'external/c4_lag_control_audit_staging',
    'next_decision':'external/c4_e_next_decision_staging',
}
mapping = {}
for name,relative in groups.items():
    directory = root/relative
    assert (directory/'INTEGRITY.json').exists() or name == 'next_decision', relative
    for path in sorted(directory.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            mapping[name+'/'+path.relative_to(directory).as_posix()] = path
for relative in (
    'external/verify_e_mpc_promotion_once.py','external/c4_e_mpc_promotion_01.json',
    'external/verify_e_mpc_test_entry_once.py','external/c4_e_mpc_test_entry_01.json',
    'external/verify_e_runner_promotion_once.py','external/c4_e_runner_promotion_01.json',
    'external/verify_e_audit_promotion_once.py','external/c4_e_audit_promotion_01.json',
    'external/run_guard_lag_control_once.py',
    'external/c4_e_d_manifest_schema_read_01.json',
):
    mapping['root_tools/'+Path(relative).name] = root/relative
mapping['root_tools/archive_guard_lag_preparation_once.py'] = Path(__file__).resolve()
assert all(p.is_file() for p in mapping.values())
started = time.perf_counter()
destination.mkdir(parents=True)
records = {}
for name,original in mapping.items():
    data = original.read_bytes()
    target = destination/name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, target)
    copied = target.read_bytes()
    assert copied == data, name
    records[name] = {'sha256':hashlib.sha256(copied).hexdigest(),'bytes':len(copied),
                     'original_path':original.relative_to(root).as_posix()}
report = {'schema_version':1,'scope':'E engineering preparation only; no formal physics or scientific adoption',
          'base_source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
          'files':records,'payload_count':len(records),'payload_bytes':sum(x['bytes'] for x in records.values()),
          'byte_copy_checks':len(records),'failed':0,'new_physics':0,'new_predictions':0,'new_updates':0,
          'archive_wall_seconds':time.perf_counter()-started,
          'failures_retained':True,'note':'Read per-stage first records for artificial math, imports and failed engineering cost.'}
with (destination/'manifest.json').open('x',encoding='utf-8') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
