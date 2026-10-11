"""Finalize new FR preparation only; never imports a model or runs physics."""
import ast
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
prep = root/'results/cpu_validation/2026-10-12_free_root_pair_prediction_preparation'
assert prep.is_dir() and not (prep/'manifest.json').exists()
def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
def save(name, data):
    path = prep/name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()
runner_path = root/'external/c4_free_learning_candidate/develop_free_root_pair.py'
review_path = root/'external/c4_free_learning_candidate/runner_review_receipt.json'
review = json.loads(review_path.read_bytes())
assert review['status'] == 'review_passed_with_bounded_synthetic_gate_check'
runner_original = runner_path.read_bytes()
assert review['final_runner'] == identity(runner_original)
save('reviewed_originals/develop_free_root_pair.py', runner_original)
runner = runner_original.decode().replace('\r\n', '\n')
pin = identity((root/'docs/FREE_ROOT_LEARNING_PROTOCOL.md').read_bytes())
needle = 'PROTOCOL_PIN = None  # Final published protocol identity must be frozen first.'
assert runner.count(needle) == 1
runner = runner.replace(needle, 'PROTOCOL_PIN = ' + repr(pin))
ast.parse(runner)
production = root/'scripts/develop_free_root_pair.py'
assert not production.exists()
production.write_bytes(runner.encode())
for name, source in (
    ('runner_review_receipt.json', review_path),
    ('runner_before_gate_review.py', root/'external/c4_free_learning_candidate/develop_free_root_pair_before_gate_review.py'),
    ('runner_gate_check.py', root/'external/c4_free_learning_candidate/check_runner_fr1_gate.py'),
    ('runner_gate_check_first.json', root/'external/c4_free_learning_candidate/runner_gate_check_first.json'),
    ('runner_gate_check_stdout.log', root/'external/c4_free_learning_candidate/runner_gate_check_stdout.log'),
    ('runner_gate_check_stderr.log', root/'external/c4_free_learning_candidate/runner_gate_check_stderr.log'),
    ('collector_before_contact_revision.py', root/'external/c4_free_learning_candidate/collector_revision_01/before.py'),
    ('derive_free_root_learning_once.py', root/'external/derive_free_root_learning_once.py'),
    ('revise_free_root_domain_once.py', root/'external/revise_free_root_domain_once.py'),
    ('publish_free_root_learning_once.py', root/'external/publish_free_root_learning_once.py'),
    ('finalize_fr_learning_preparation_once.py', Path(__file__)),
    ('run_fr1_first_once.py', root/'external/run_fr1_first_once.py')):
    save('external_originals/'+name, source.read_bytes())
save('first_collector_checks.json', encoded({
    'command': 'external/cpu_physics_env/Scripts/python.exe -m pytest -q tests/test_free_root_pair_collection.py',
    'PYTHONPATH': 'src', 'first_attempt': True, 'exit_code': 0,
    'tool_output': '...... [100%]\n6 passed in 0.35s\n',
    'tool_wall_seconds': 1.1261831, 'formal_physics_or_models_or_fit_updates': 0,
    'test_source': identity((root/'tests/test_free_root_pair_collection.py').read_bytes()),
    'collector_source': identity((root/'src/developmental_physics/free_root_pair_development.py').read_bytes()),
    'fresh_checks_only': True, 'old_math_or_physics_repeated': False,
}))
save('published_source_mapping.json', encoded({
    'runner': {'reviewed': identity(runner_original), 'published': identity(runner.encode()),
               'changes_after_review': 'LF normalization and exact protocol pin only'},
    'protocol_pin': pin, 'batch_adoption_before_FR1_data': True,
    'new_Physics_or_learning_during_preparation': 0,
    'continuous_goal_stays_active': True,
}))
links = []
for name, target in (
    ('README.md', 'docs/FREE_ROOT_LEARNING_PROTOCOL.md'),
    ('AGENTS.md', 'docs/FREE_ROOT_LEARNING_PROTOCOL.md'),
    ('docs/PROGRESS.md', 'FREE_ROOT_LEARNING_PROTOCOL.md'),
    ('docs/CONTINUOUS_EXECUTION_PLAN.md', 'FREE_ROOT_LEARNING_PROTOCOL.md'),
    ('docs/CPU_VALIDATION_TARGET.md', 'FREE_ROOT_LEARNING_PROTOCOL.md')):
    source = root/name
    text = source.read_text(encoding='utf-8')
    assert ']('+target+')' in text
    resolved = source.parent/target
    assert resolved.is_file(), str(resolved)
    links.append({'source': name, 'target': target, 'exists': True})
save('new_protocol_link_checks.json', encoded({'new_links': links, 'failed': 0,
    'old_raw_or_math_reads': 0}))
files = {}
for path in sorted(prep.rglob('*')):
    if path.is_file():
        files[path.relative_to(prep).as_posix()] = identity(path.read_bytes())
save('manifest.json', encoded({'stage': 'FR1_FR2_frozen_preparation', 'files': files,
    'first_collector_checks_passed': 6, 'first_batch_equivalence_fixtures_passed': 11,
    'runner_gate_check_status': 'passed', 'formal_physics': 0, 'scientific_adoption': False}))
print(json.dumps({'runner': identity(runner.encode()), 'preparation_files_before_manifest': len(files), 'protocol_pin': pin}))
