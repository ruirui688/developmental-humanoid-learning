"""Save first Z2 reporting/check bytes; no physics or metric recalculation."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
out = repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_control/reporting'
out.mkdir(exist_ok=False)
began, cpu = time.perf_counter(), time.process_time()
files = {}
reads = read_bytes = writes = write_bytes = 0
for name in (
    'check_z2_first_contract.py', 'c4_z2_thin_contract_preparation.json',
    'c4_z2_first_contract.json', 'check_z2_saved_metrics_once.py',
    'c4_z2_new_metrics_check.json', 'read_z2_reporting_once.py',
    'c4_z2_report_input.json', 'c4_z2_report.md', 'seal_z2_reporting_once.py',
    'update_z2_navigation_once.py', 'check_navigation_links.py', 'c4_z2_navigation_links.json',
):
    data = (repo / 'external' / name).read_bytes()
    reads += 1
    read_bytes += len(data)
    with (out / name).open('xb') as stream:
        stream.write(data)
    writes += 1
    write_bytes += len(data)
    got = (out / name).read_bytes()
    reads += 1
    read_bytes += len(got)
    assert got == data
    files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
record = dict(status='sealed', files=files,
              reads_before_manifest=reads, read_bytes_before_manifest=read_bytes,
              writes_before_manifest=writes, write_bytes_before_manifest=write_bytes,
              wall_seconds_before_manifest=time.perf_counter()-began,
              cpu_seconds_before_manifest=time.process_time()-cpu,
              model_fit_physics_or_scientific_metric_calls=0,
              old_experiments_repeated=False, automatic_retry=False)
with (out / 'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
print(json.dumps({k: v for k, v in record.items() if k != 'files'}))
