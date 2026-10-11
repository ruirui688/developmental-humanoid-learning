"""Byte-only final ignored delivery seal; no code, data or math execution."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent;target=root/'INTEGRITY.json'
if target.exists():raise SystemExit('Refuse to overwrite E auditor delivery seal')
expected='17a275828bd5f548b2454cac02c193203c264b8f94936ee99d61f78d5bcd9905'
source=(root/'audit_guard_lag_control.py').read_bytes()
if hashlib.sha256(source).hexdigest()!=expected:raise SystemExit('Final auditor source changed before byte seal')
files={}
for path in sorted(root.iterdir()):
    if path.is_file() and path.name!='INTEGRITY.json':
        blob=path.read_bytes();files[path.name]={'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()}
record={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),
    'source_sha256':expected,'files':files,'production_path':'scripts/audit_guard_lag_control.py',
    'formal_flag':False,'root_owns_promotion_and_execution':True,
    'engineering_evidence':{'original_planning_cases_not_repeated':8,'new_contracts':8,'new_contract_failures':0,
        'directed_metadata_first_harness_failure_preserved':1,'directed_metadata_repair_checks':3,'directed_metadata_repair_failures':0},
    'formal_physics_calls':0,'old_D_or_C_data_reads':0,'old_D_or_C_math_or_audit_reexecutions':0,
    'new_model_or_RLS_updates':0,'complete_fake_archive_matrices':0,
    'seal_semantics':'all plain-file original bytes only; excludes pycache and this index itself'}
target.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'source_sha256':expected,'files':len(files),'integrity_sha256':hashlib.sha256(target.read_bytes()).hexdigest()},allow_nan=False))
