"""Byte snapshots of the two reviewed F drafts, without executing either."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent
workspace=next(p for p in root.parents if (p/'pyproject.toml').is_file())
target=root/'SOURCE_RECORD.json'
if target.exists():raise SystemExit('Refuse to overwrite static review source record')
sources={
    'external/c4_native_context_diagnostic_staging/diagnose_guard_native_context.py':('reviewed_diagnostic.py','037fb78aa17333aaebe4db15b7737b887cb7d1168ce415421777428c51cfcf47'),
    'external/c4_native_context_protocol_staging/F_PROTOCOL_DRAFT.md':('reviewed_protocol.md','a46f036e55d7ffe809d6ff2fdd09aae336b3cc2413578607b87ef69c85d6790e')}
records={}
for relative,(snapshot,expected) in sources.items():
    blob=(workspace/relative).read_bytes();actual=hashlib.sha256(blob).hexdigest()
    if actual!=expected:raise SystemExit('Reviewed source changed before snapshot: '+relative)
    (root/snapshot).write_bytes(blob)
    records[relative]={'sha256':actual,'bytes':len(blob),'snapshot':snapshot}
record={'schema_version':1,'created_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'limited independent static F review only',
    'sources':records,'findings':4,'source_snapshots_original_bytes':True,
    'E_new_data_reads':0,'C_D_raw_reads':0,'mathematical_or_diagnostic_executions':0,'old_full_audit_reexecutions':0,
    'model_predict_calls':0,'RLS_or_other_updates':0,'physics_calls':0,'full_fake_archive_matrices':0,
    'Git_calls':0,'tracked_file_changes':0,'E_gate_changes':0,
    'review_note_sha256':hashlib.sha256((root/'REVIEW.md').read_bytes()).hexdigest(),
    'snapshot_accounting':{'source_file_opens':len(records),'source_bytes_read':sum(x['bytes'] for x in records.values()),
        'scope':'this byte-snapshot operation only; earlier source-text review tool reads are not experimental input reads'}}
target.write_text(json.dumps(record,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'source_files':len(records),'record_sha256':hashlib.sha256(target.read_bytes()).hexdigest()},allow_nan=False))
