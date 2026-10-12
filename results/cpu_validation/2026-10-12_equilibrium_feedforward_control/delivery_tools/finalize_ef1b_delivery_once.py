"""Attach the completed first audit and delivery tools; do not replay checks."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

repo = Path(__file__).resolve().parents[1]
base = repo / 'results/cpu_validation/2026-10-12_equilibrium_feedforward_control'
audit_dir = repo / 'external/ef1b_saved_audit_first'
audit = json.loads((audit_dir / 'audit.json').read_bytes())
assert audit['status'] == 'passed' and audit['checks'] == 443 and audit['failures'] == 0
files = {}
def copy(path, name):
    data = path.read_bytes()
    assert len(data) < 100_000_000
    target = base / name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
    files[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
for path in sorted(audit_dir.iterdir()):
    if path.is_file():
        copy(path, 'audit_first/' + path.name)
for name in ['audit_ef1b_first_saved.py', 'deliver_ef1b_results_once.py', 'publish_ef1b_summary_once.py', 'finalize_ef1b_delivery_once.py']:
    copy(repo / 'external' / name, 'delivery_tools/' + name)
receipt = {'completed_utc': datetime.now(timezone.utc).isoformat(), 'status': 'first_audit_attached',
    'files': files, 'audit_source_commit': audit['source_commit'], 'audit_result': {'status': audit['status'],
    'checks': audit['checks'], 'failures': audit['failures']}, 'new_physics': 0, 'new_model_calls': 0,
    'audit_replayed': False, 'source_copy_reads_and_writes_bytes_each': sum(row['bytes'] for row in files.values()),
    'unmeasured_internal_filesystem_IO': 'unknown_not_zero'}
with (base / 'finalization.json').open('xb') as stream:
    stream.write((json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode())
report = repo / 'docs/EQUILIBRIUM_FEEDFORWARD_CONTROL_RESULTS.md'
report.write_bytes(report.read_bytes() + (
    '\n## 首次新保存核验\n\n'
    '[首次核验](../results/cpu_validation/2026-10-12_equilibrium_feedforward_control/audit_first/audit.json)'
    'passed，443项/0失败/0不可评。只读新原件及精确Git源码blob，核对新来源、分片、六fresh/六reused、'
    '完整性、原接触资格与模型指纹；独立核对6个新tracking axis向量/6个joint标量、18,000新努力端点、'
    '120个新自身RMSE向量。\n\n'
    '新核验读取22文件/108,060,281stored bytes、577,437,612decoded bytes，解析65,772 JSONL记录；'
    '其中trace18,000、predictions11,772、paid journal36,000。23个source.zip成员及23个精确Git blob分别444,332bytes；'
    '未读取旧轨迹/预测/付费日志，未重跑旧审计/旧指标或科学门，0物理/model/fit。核验成本与正式物理分列。\n'
).encode())
print(json.dumps({'status': receipt['status'], 'payloads': len(files)}))
