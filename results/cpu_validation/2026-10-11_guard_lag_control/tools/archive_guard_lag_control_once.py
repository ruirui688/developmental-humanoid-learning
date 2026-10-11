"""Seal existing first E evidence byte-for-byte; no prediction or audit replay."""
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
target = root / 'results/cpu_validation/2026-10-11_guard_lag_control'
assert not target.exists(), 'exclusive first archive'
target.mkdir(parents=True)
wall, cpu = time.perf_counter(), time.process_time()
records = {}
read_opens = read_bytes = checks = 0

def copy(source_name, destination_name):
    global read_opens, read_bytes, checks
    source, destination = root / source_name, target / destination_name
    original = source.read_bytes()
    read_opens += 1
    read_bytes += len(original)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(original)
    saved = destination.read_bytes()
    read_opens += 1
    read_bytes += len(saved)
    checks += 1
    assert saved == original, destination_name
    records[destination_name] = {'sha256': hashlib.sha256(saved).hexdigest(),
        'bytes': len(saved), 'original_path': source_name}

for path in sorted((root / 'external/guard_lag_control_20261011_first').iterdir()):
    assert path.is_file()
    copy(path.relative_to(root).as_posix(), 'raw/' + path.name)
for source, destination in [
    ('guard_lag_control_20261011_first_audit.json', 'first_audit.json'),
    ('guard_lag_control_20261011_first_audit_stdout.txt', 'first_audit_stdout.txt'),
    ('guard_lag_control_20261011_first_audit_execution.json', 'first_audit_execution.json'),
    ('guard_lag_control_20261011_first_stdout.txt', 'collection_stdout.txt'),
    ('guard_lag_control_20261011_first_execution.json', 'collection_execution.json'),
    ('guard_lag_control_20261011_first_runtime_source_freeze.json', 'runtime_source_freeze.json'),
    ('guard_lag_control_20261011_summary_01/summary.json', 'summary_once/summary.json'),
    ('c4_e_first_audit_pins_01.json', 'root_records/first_audit_pins.json'),
    ('c4_e_freeze_links_01.json', 'root_records/freeze_links.json'),
    ('c4_e_staged_bytes_01.json', 'root_records/staged_bytes.json'),
    ('check_e_preparation_links_once.py', 'tools/check_e_preparation_links_once.py'),
    ('verify_e_staged_bytes_once.py', 'tools/verify_e_staged_bytes_once.py'),
    ('run_guard_lag_control_once.py', 'tools/run_guard_lag_control_once.py'),
    ('run_guard_lag_control_first_audit_once.py', 'tools/run_guard_lag_control_first_audit_once.py'),
    ('summarize_guard_lag_control_saved_once.py', 'tools/summarize_guard_lag_control_saved_once.py'),
    ('archive_guard_lag_control_once.py', 'tools/archive_guard_lag_control_once.py'),
]:
    copy('external/' + source, destination)

manifest = {'schema_version': 1, 'kind': 'first_explicit_history_pair_control_development_evidence',
    'source_commit': 'dda82b1854d80483d0b16e0532bc414906e6a402', 'files': records,
    'payload_count': len(records), 'payload_bytes': sum(row['bytes'] for row in records.values()),
    'checks': checks, 'failed': 0,
    'boundary': '9 complete / 3 learned elbow velocity stops at 104 active; no scientific adoption.',
    'preparation_archive': 'results/cpu_validation/2026-10-11_guard_lag_control_preparation/manifest.json',
    'execution': {'source_and_copy_binary_reads': read_opens, 'source_and_copy_binary_bytes': read_bytes,
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'scope': 'byte copying and equality checks through manifest assembly; excludes final manifest writing',
        'new_physics': 0, 'new_predictions': 0, 'new_fits_or_updates': 0,
        'first_audit_reexecutions': 0, 'summary_reexecutions': 0}}
with (target / 'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(manifest, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({k: manifest[k] for k in ('payload_count', 'payload_bytes', 'checks', 'failed', 'execution')}, indent=2))
