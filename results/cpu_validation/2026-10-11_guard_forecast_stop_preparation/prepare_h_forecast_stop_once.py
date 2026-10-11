"""One-time promotion and byte-preserving H preparation archive."""
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
staging = root / 'external/c4_g_forecast_stop_diagnostic_staging'
out = root / 'results/cpu_validation/2026-10-11_guard_forecast_stop_preparation'
started, cpu = time.perf_counter(), time.process_time()
out.mkdir(parents=True, exist_ok=False)
files = {}
reads = 0
read_bytes = 0

def copy(source, relative):
    global reads, read_bytes
    data = source.read_bytes()
    reads += 1
    read_bytes += len(data)
    target = out / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    saved = target.read_bytes()
    reads += 1
    read_bytes += len(saved)
    assert saved == data, relative
    files[relative] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                       'source': str(source.relative_to(root)), 'copy_verified': True}
    return data

for name in ('diagnose_guard_pd_tail_forecast_stop.py',
             'GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_PROTOCOL.md',
             'check_h_minimal.py', 'CHECK_01.json',
             'PREPARATION_FIRST_ISSUE.json', 'INTEGRITY.json'):
    copy(staging / name, 'draft/' + name)
for name in ('check_g_git_payload_paths_once.py', 'c4_g_delivery_paths_01.json'):
    copy(root / 'external' / name, 'g_delivery/' + name)
copy(root / 'external/c4_next_control_direction_review/REVIEW.md', 'method_review/REVIEW.md')
for name in ('REVIEW.md', 'schema_01.json', 'INTEGRITY.json'):
    copy(root / 'external/c4_h_schema_review_staging' / name, 'schema_review/' + name)
copy(root / 'external/run_h_forecast_stop_once.py', 'run_h_forecast_stop_once.py')
copy(Path(__file__), 'prepare_h_forecast_stop_once.py')

draft = (out / 'draft/diagnose_guard_pd_tail_forecast_stop.py').read_bytes()
reads += 1
read_bytes += len(draft)
assert hashlib.sha256(draft).hexdigest() == '0715bf3bfdd123902e47a0c1761f53b81a0c0eae642c051c561d3a5090f5812b'
old, new = b'FORMAL_DIAGNOSTIC_ENABLED = False', b'FORMAL_DIAGNOSTIC_ENABLED = True'
assert draft.count(old) == 1 and b'\r' not in draft
promoted = draft.replace(old, new)
ast.parse(promoted)
script = root / 'scripts/diagnose_guard_pd_tail_forecast_stop.py'
assert not script.exists()
script.write_bytes(promoted)
saved = script.read_bytes()
reads += 1
read_bytes += len(saved)
assert saved == promoted
protocol = root / 'docs/GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_PROTOCOL.md'
assert not protocol.exists()
protocol_data = (out / 'draft/GUARD_PD_TAIL_FORECAST_STOP_DIAGNOSTIC_PROTOCOL.md').read_bytes()
reads += 1
read_bytes += len(protocol_data)
assert b'\r' not in protocol_data
protocol.write_bytes(protocol_data)
assert protocol.read_bytes() == protocol_data
reads += 1
read_bytes += len(protocol_data)

promotion = {'script_sha256': hashlib.sha256(promoted).hexdigest(),
             'protocol_sha256': hashlib.sha256(protocol_data).hexdigest(),
             'only_script_change': 'FORMAL_DIAGNOSTIC_ENABLED False -> True',
             'ast_parse_passed': True, 'committed_execution_pending': True,
             'previous_small_checks_not_repeated': True,
             'model_calls': 0, 'physics_calls': 0, 'actual_G_reads': 0}
blob = (json.dumps(promotion, indent=2) + '\n').encode()
(out / 'promotion.json').write_bytes(blob)
files['promotion.json'] = {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}
manifest = {'schema_version': 1, 'files': files,
            'cost': {'binary_reads': reads, 'binary_read_bytes': read_bytes,
                     'copy_checks': 14, 'copy_failures': 0,
                     'wall_seconds': time.perf_counter()-started,
                     'cpu_seconds': time.process_time()-cpu},
            'scope': 'promotion and original byte copies; no old checks, G data, model or physics'}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'archive': str(out), **promotion, 'cost': manifest['cost']}))
