"""Seal new FR2 audit, report and navigation once; no old raw reads."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
dest = root/'results/cpu_validation/2026-10-12_free_root_pair_control'
assert not (dest/'verification_manifest.json').exists()

def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def save(name, data):
    target = dest/name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)

audit_path = root/'external/fr2_first_audit/result/audit.json'
audit = json.loads(audit_path.read_bytes())
checks = sum(audit['checks'].values())
failed = sum(audit['failed_checks'].values())
assert audit['status'] == 'passed' and failed == 0
links = []
report = root/'docs/FREE_ROOT_PAIR_CONTROL_RESULTS.md'
for target in re.findall(r'\]\(([^)]+)\)', report.read_text(encoding='utf-8')):
    if '://' in target or target.startswith('#'):
        continue
    path = (report.parent/target.split('#',1)[0]).resolve()
    assert path.is_relative_to(root)
    # Audit payloads are copied below; use their first result location until then.
    if target.startswith('../results/cpu_validation/2026-10-12_free_root_pair_control/audit_first/'):
        name = target.split('/audit_first/',1)[1]
        exists = (root/'external/fr2_first_audit/result'/name).is_file()
    else:
        exists = path.is_file()
    links.append({'target': target, 'exists': exists})
assert all(link['exists'] for link in links)
navigation = {'report': str(report.relative_to(root)), 'local_links_checked': len(links),
    'failed': 0, 'links': links, 'models_or_fit_or_physics': 0}
save('delivery_sources/navigation_checks.json', (json.dumps(navigation,indent=2)+'\n').encode())
for path in sorted((root/'external/fr2_first_audit/result').rglob('*')):
    if path.is_file():
        save('audit_first/'+path.relative_to(root/'external/fr2_first_audit/result').as_posix(), path.read_bytes())
for name in ('stdout.log', 'stderr.log', 'first_execution_receipt.json'):
    save('audit_first/'+name, (root/'external/fr2_first_audit'/name).read_bytes())
for name in ('audit_free_root_pair_control.py', 'preparation.json'):
    save('audit_first/'+name, (root/'external/fr2_audit_candidate'/name).read_bytes())
for name in ('run_fr2_audit_first_once.py', 'write_fr2_report_candidate.py',
             'fr2_report_writing_receipt.json', 'finalize_fr2_delivery_once.py'):
    save('delivery_sources/'+name, (root/'external'/name).read_bytes())
base_data = (dest/'manifest.json').read_bytes()
base = json.loads(base_data)
new_files = {}
for path in sorted(dest.rglob('*')):
    if path.is_file():
        relative = path.relative_to(dest).as_posix()
        if relative not in base['files_before_top_manifest'] and relative != 'manifest.json':
            new_files[relative] = pin(path.read_bytes())
save('verification_manifest.json', (json.dumps({
    'first_archive_manifest': pin(base_data), 'new_files': new_files,
    'raw_payloads_not_reread_by_this_helper': True,
    'first_audit_status': audit['status'], 'first_audit_checks': checks,
    'first_audit_failed': failed, 'source_commit': audit['source_commit'],
    'FR2_model_contribution_gate_passed': False, 'C4_C5_C6_C7_validation': False,
    'continuous_goal_stays_active': True,
}, ensure_ascii=False, indent=2)+'\n').encode())
print(json.dumps({'FR2_delivery_sealed': True, 'new_files':len(new_files),
    'audit_checks': checks, 'audit_failed': failed, 'links_checked':len(links),
    'model_or_fit_or_physics_calls':0}))
