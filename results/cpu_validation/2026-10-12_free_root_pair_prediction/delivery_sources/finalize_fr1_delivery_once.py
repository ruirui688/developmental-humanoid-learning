"""Seal only new FR1 verification/delivery files; do not reread raw payloads."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dest = root/'results/cpu_validation/2026-10-12_free_root_pair_prediction'
assert not (dest/'verification_manifest.json').exists()
def pin(data):
    return {'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
def save(name, data):
    target = dest/name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
for name in ('write_fr1_report_once.py', 'fr1_report_writing_receipt.json',
             'fr1_report_navigation_checks.json', 'run_fr2_first_once.py',
             'archive_fr2_first_once.py', 'prepare_fr2_launchers_once.py',
             'fr2_launcher_preparation.json', 'fr2_archive_label_revision.json',
             'finalize_fr1_delivery_once.py'):
    save('delivery_sources/'+name, (root/'external'/name).read_bytes())
base_bytes = (dest/'manifest.json').read_bytes()
base = json.loads(base_bytes)
new_files = {}
for path in sorted(dest.rglob('*')):
    if path.is_file():
        relative = path.relative_to(dest).as_posix()
        if relative not in base['files_before_top_manifest'] and relative != 'manifest.json':
            new_files[relative] = pin(path.read_bytes())
save('verification_manifest.json', (json.dumps({
    'first_archive_manifest':pin(base_bytes), 'new_files':new_files,
    'raw_payloads_not_reread_by_this_helper':True,
    'first_audit_exit_code':0, 'first_audit_checks':680448, 'first_audit_failed':0,
    'source_commit':'41ccb851d7341afb68ec17d09666fe31d171d484',
    'FR1_prediction_gate_passed':True, 'C4_C5_C6_C7_validation':False,
    'continuous_goal_stays_active':True,
}, ensure_ascii=False, indent=2)+'\n').encode())
print(json.dumps({'FR1_delivery_sealed':True, 'new_files':len(new_files), 'model_physics_fit_calls':0}))
