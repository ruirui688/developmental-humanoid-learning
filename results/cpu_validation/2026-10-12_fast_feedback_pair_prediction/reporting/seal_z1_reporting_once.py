"""Seal only new Z1 reporting receipts; leave raw and root manifests untouched."""
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
stage = repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_prediction'
out = stage / 'reporting'
out.mkdir(exist_ok=False)
began, cpu = time.perf_counter(), time.process_time()
files = {}
cost = dict(reads=0, read_bytes=0, writes=0, write_bytes=0)
names = ['read_z1_reporting_once.py', 'c4_z1_report_input.json', 'check_z1_saved_metrics_once.py', 'c4_z1_new_metrics_check.json', 'check_z1_first_contract.py', 'c4_z1_contract_design_receipt.json', 'c4_z1_report_preparation.json', 'update_z1_result_navigation_once.py', 'seal_z1_reporting_once.py']
for name in names:
    data = (repo / 'external' / name).read_bytes()
    cost['reads'] += 1
    cost['read_bytes'] += len(data)
    with (out / name).open('xb') as stream:
        stream.write(data)
    cost['writes'] += 1
    cost['write_bytes'] += len(data)
    files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
data = (repo / 'external/z1_first_contract/c4_z1_first_contract_receipt.json').read_bytes()
cost['reads'] += 1
cost['read_bytes'] += len(data)
with (out / 'c4_z1_first_contract_receipt.json').open('xb') as stream:
    stream.write(data)
cost['writes'] += 1
cost['write_bytes'] += len(data)
files['c4_z1_first_contract_receipt.json'] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
record = {'status': 'sealed', 'files': files, 'cost_before_manifest': cost.copy(), 'wall_seconds': time.perf_counter()-began, 'cpu_seconds': time.process_time()-cpu, 'scientific_recomputations_in_sealing': 0, 'model_fit_physics_calls': 0, 'raw_or_root_manifests_modified': False}
with (out / 'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
print(json.dumps({'files': len(files), **cost}))
