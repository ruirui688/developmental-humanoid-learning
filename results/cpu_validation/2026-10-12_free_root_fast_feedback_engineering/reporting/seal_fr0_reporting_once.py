"""Save first FR0 report, checks and delivery bytes without scientific calls."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
out = repo / 'results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering/reporting'
out.mkdir(exist_ok=False)
began, cpu = time.perf_counter(), time.process_time()
files, cost = {}, dict(reads=0, read_bytes=0, writes=0, write_bytes=0)
for name in (
    'check_fr0_first_contract.py', 'c4_fr0_first_contract.json',
    'check_fr0_new_metrics_once.py', 'c4_fr0_new_metrics_check.json',
    'read_fr0_reporting_once.py', 'c4_fr0_report_input.json', 'c4_fr0_report.md',
    'archive_fr0_guarded_once.py', 'fr0_archive_guard.json',
    'check_navigation_links.py', 'c4_fr0_preparation_links.json', 'c4_fr0_results_links.json',
    'update_fr0_results_once.py', 'seal_fr0_reporting_once.py',
):
    data = (repo / 'external' / name).read_bytes()
    cost['reads'] += 1
    cost['read_bytes'] += len(data)
    with (out / name).open('xb') as stream:
        stream.write(data)
    cost['writes'] += 1
    cost['write_bytes'] += len(data)
    verify = (out / name).read_bytes()
    cost['reads'] += 1
    cost['read_bytes'] += len(verify)
    assert data == verify
    files[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
record = dict(status='sealed', files=files, cost_before_manifest_write=cost,
              wall_seconds_before_manifest=time.perf_counter()-began,
              cpu_seconds_before_manifest=time.process_time()-cpu,
              model_fit_physics_or_scientific_metric_calls=0, automatic_retry=False)
with (out / 'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
print(json.dumps({k: v for k, v in record.items() if k != 'files'}))
