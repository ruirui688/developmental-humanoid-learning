"""Byte-only first D closure; preserves engineering and execution originals."""
import hashlib
import json
from pathlib import Path
import shutil
import time

root=Path(__file__).resolve().parents[1]
target=root/'results/cpu_validation/2026-10-11_guard_lag_offline'
assert not target.exists()
started_wall,started_cpu=time.perf_counter(),time.process_time()
copied=[]


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def copy(source,name):
    path=target/name
    path.parent.mkdir(parents=True,exist_ok=True)
    blob=source.read_bytes()
    with path.open('xb') as stream:
        stream.write(blob)
    assert path.read_bytes()==blob
    copied.append({'path':name.replace('\\','/'),'original_path':str(source.relative_to(root)).replace('\\','/'),
        'sha256':sha(blob),'bytes':len(blob)})


groups=(
 ('external/guard_lag_offline_20261011_first','raw'),
 ('external/guard_lag_offline_20261011_summary_01','summary_once'),
 ('external/c4_lag_offline_staging','engineering/evaluator'),
 ('external/c4_lag_offline_audit_staging','engineering/auditor'),
 ('external/guard_lag_offline_promotion_01','engineering/promotion'),
 ('external/c4_lag_control_design_staging','forward_control_design'),
 ('external/c4_lag_read_accounting_reconciliation','read_accounting_reconciliation'),
 ('external/c4_lag_result_interpretation_01','saved_result_interpretation'),
)
for directory,prefix in groups:
    source=root/directory
    assert source.is_dir(),directory
    for item in sorted(source.rglob('*')):
        if item.is_file() and '__pycache__' not in item.parts and not item.name.endswith(('.pyc','.pyo')):
            copy(item,f'{prefix}/{item.relative_to(source).as_posix()}')
for name,destination in (
 ('guard_lag_offline_20261011_first_audit.json','first_audit.json'),
 ('guard_lag_offline_20261011_first_audit_stdout.txt','execution/first_audit_stdout.txt'),
 ('guard_lag_offline_20261011_summary_01_stdout.txt','execution/summary_stdout.txt'),
 ('guard_lag_offline_20261011_first_runtime_source_freeze.json','execution/runtime_source_freeze.json'),
 ('guard_lag_offline_20261011_first_context.json','execution/context.json'),
 ('guard_lag_offline_20261011_first_stdout.txt','execution/first_stdout.txt'),
 ('guard_lag_offline_20261011_first_execution.json','execution/first_execution.json'),
 ('guard_lag_offline_20261011_postprocess_execution.json','execution/postprocess_execution.json'),
 ('guard_lag_offline_20261011_summary_execution.json','execution/summary_execution.json'),
 ('run_guard_lag_offline_once.py','tools/run_guard_lag_offline_once.py'),
 ('audit_and_summarize_guard_lag_once.py','tools/audit_and_summarize_guard_lag_once.py'),
 ('summarize_guard_lag_saved_once.py','tools/summarize_guard_lag_saved_once.py'),
 ('run_guard_lag_summary_once.py','tools/run_guard_lag_summary_once.py'),
 ('archive_guard_lag_offline_once.py','tools/archive_guard_lag_offline_once.py'),
):
    copy(root/'external'/name,destination)
manifest={'schema_version':1,'kind':'first_bound_single_lag_development_offline_evidence',
 'boundary':'Same C development data; no new physics, no controller selection, no scientific adoption gates.',
 'files':{item['path']:{k:item[k] for k in ('sha256','bytes','original_path')} for item in copied},
 'closure_checks':{'copied_original_byte_equal_checks':len(copied),'failed':0},
 'execution':{'wall_seconds':time.perf_counter()-started_wall,'cpu_seconds':time.process_time()-started_cpu,
    'new_physics_calls':0,'new_model_predictions':0,'new_model_updates':0,'audit_reexecutions':0,'git_calls':0,
    'scope':'Original-byte copy/identity only, excludes final manifest write'}}
with (target/'manifest.json').open('x',encoding='utf-8',newline='\n') as stream:
    json.dump(manifest,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps({'payload_files':len(copied),'payload_bytes':sum(item['bytes'] for item in copied),
    'manifest_sha256':sha((target/'manifest.json').read_bytes()),'closure_checks':manifest['closure_checks'],'execution':manifest['execution']}))
