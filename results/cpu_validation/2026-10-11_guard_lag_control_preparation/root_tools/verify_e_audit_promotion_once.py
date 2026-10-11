"""Source-only independent-auditor promotion; original sixteen cases not rerun."""
import ast
import hashlib
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
stage=root/'external/c4_lag_control_audit_staging'
old=(stage/'audit_guard_lag_control.py').read_bytes()
new=(root/'scripts/audit_guard_lag_control.py').read_bytes()
expected=old.decode('utf-8').replace('Formal execution is disabled in ignored staging until root freezes this source.', 'Formal execution requires this canonical source and the frozen E archive.').replace('FORMAL_AUDIT_ENABLED=False','FORMAL_AUDIT_ENABLED=True').encode('utf-8')
old_test=(stage/'test_lag_control_audit_contract.py').read_text(encoding='utf-8')
expected_test=old_test.replace("SOURCE=Path(__file__).with_name('audit_guard_lag_control.py')", "SOURCE=Path(__file__).resolve().parents[1]/'scripts/audit_guard_lag_control.py'").replace("        with self.assertRaises(RuntimeError):m.audit(Path('never-read-existing-or-original-archive'))", "        prior=m.FORMAL_AUDIT_ENABLED\n        try:\n            m.FORMAL_AUDIT_ENABLED=False\n            with self.assertRaises(RuntimeError):m.audit(Path('never-read-existing-or-original-archive'))\n        finally:\n            m.FORMAL_AUDIT_ENABLED=prior")
tree=ast.parse(new)
imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
names=[a.name for n in imports for a in n.names] + [n.module or '' for n in imports if isinstance(n,ast.ImportFrom)]
checks={'final_delivered_source_identity':hashlib.sha256(old).hexdigest()=='17a275828bd5f548b2454cac02c193203c264b8f94936ee99d61f78d5bcd9905',
    'only_release_flag_and_description_changed':new==expected,
    'canonical_test_only_path_and_guarded_rejection_fixture':(root/'tests/test_guard_lag_control_audit.py').read_text(encoding='utf-8')==expected_test,
    'no_numpy_physics_or_online_imports':not any(name.startswith(('numpy','mujoco','developmental_physics')) for name in names),
    'original_D_auditor_unchanged':hashlib.sha256((root/'scripts/audit_guard_lag_offline.py').read_bytes()).hexdigest()=='bede59d0984edddf6d7384b6d11c0beddae711dfcc616571f4bfd9ee8ce3211b'}
for path in ('scripts/audit_guard_lag_control.py','tests/test_guard_lag_control_audit.py'):
    compile((root/path).read_bytes(),path,'exec');checks['compiled/'+path]=True
report={'checks':checks,'passed':sum(checks.values()),'failed':sum(not x for x in checks.values()),
        'source_sha256':hashlib.sha256(new).hexdigest(),'new_imports':0,'new_predictions':0,'updates':0,'physics':0,'old_math_reexecutions':0,'D_raw_reads':0}
with (root/'external/c4_e_audit_promotion_01.json').open('x',encoding='utf-8') as f:
    json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
raise SystemExit(int(report['failed']!=0))
