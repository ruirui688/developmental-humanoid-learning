"""Promote frozen F source/protocol and seal original preparation; no math rerun."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import time

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-sha256', required=True)
parser.add_argument('--protocol-sha256', required=True)
args = parser.parse_args()
wall, cpu = time.perf_counter(), time.process_time()
read_opens = read_bytes = 0
def read(path):
    global read_opens, read_bytes
    blob = path.read_bytes()
    read_opens += 1
    read_bytes += len(blob)
    return blob
def sha(blob):
    return hashlib.sha256(blob).hexdigest()
source = read(root / 'external/c4_native_context_diagnostic_staging/diagnose_guard_native_context.py')
protocol = read(root / 'external/c4_native_context_protocol_staging/F_PROTOCOL_DRAFT.md')
assert sha(source) == args.source_sha256
assert sha(protocol) == args.protocol_sha256
assert source.count(b'FORMAL_DIAGNOSTIC_ENABLED = False') == 1
promoted = source.replace(b'FORMAL_DIAGNOSTIC_ENABLED = False', b'FORMAL_DIAGNOSTIC_ENABLED = True')
before, after = ast.parse(source), ast.parse(promoted)
def functions(tree):
    return {item.name: ast.dump(item, include_attributes=False) for item in tree.body
            if isinstance(item, (ast.FunctionDef, ast.ClassDef))}
assert functions(before) == functions(after)
compile(promoted, 'scripts/diagnose_guard_native_context.py', 'exec')
target_source = root / 'scripts/diagnose_guard_native_context.py'
with target_source.open('xb') as stream:
    stream.write(promoted)
text = protocol.decode('utf-8')
start = text.index('**前瞻草稿')
end = text.index('## 1.')
text = text[:start] + ('正式开发协议。E 首次物理、独立首审和一次汇总已封口并提交；'
    '本轮源码、来源绑定和描述规则先提交推送，再从 clean 提交首次执行一次。'
    '只复用 E 保存预测与原生观测，不重算 E 审计、不读取 C/D 原始文件，'
    '不引入模型特征、控制动作或科学采用门。\n\n') + text[end:]
text += ('\n## 6. 工程封口与首次执行\n\n'
    '唯一小 fixture 的三项检查通过；随后仅修订读取/失败身份/独立缺失计数和'
    '异常语义，并验证必要新增分支，不重复已通过统计。所有中间原件、'
    '有限静态审查、定向检查及费用见[准备清单]'
    '(../results/cpu_validation/2026-10-11_guard_native_context_preparation/manifest.json)。'
    '生产提升只切换正式开关，函数/类 AST 保持相同；编译只核语法，不执行统计。\n\n'
    '来源绑定为 `configs/cpu/guard_native_context_binding.json`，固定 E 外层清单、'
    '首审、原 raw 清单、一次汇总和本协议的 SHA256。只允许首次执行，'
    '保留异常、缓存、完整派生分母及费用；结果封口、提交推送后继续最早未验收阶段。\n')
protocol_bytes = text.encode('utf-8')
protocol_name = 'docs/GUARD_NATIVE_CONTEXT_DIAGNOSTIC_PROTOCOL.md'
with (root / protocol_name).open('xb') as stream:
    stream.write(protocol_bytes)
base = 'results/cpu_validation/2026-10-11_guard_lag_control'
e_manifest_bytes = read(root / base / 'manifest.json')
e_manifest = json.loads(e_manifest_bytes)
assert e_manifest['failed'] == 0 and e_manifest['source_commit'] == 'dda82b1854d80483d0b16e0532bc414906e6a402'
binding = {'schema_version': 1, 'archive_relative_path': base,
    'e_source_commit': e_manifest['source_commit'], 'source_manifest_sha256': sha(e_manifest_bytes),
    'first_audit_sha256': e_manifest['files']['first_audit.json']['sha256'],
    'summary_sha256': e_manifest['files']['summary_once/summary.json']['sha256'],
    'raw_manifest_sha256': e_manifest['files']['raw/manifest.json']['sha256'],
    'protocol': {'path': protocol_name, 'sha256': sha(protocol_bytes)}}
binding_path = root / 'configs/cpu/guard_native_context_binding.json'
binding_path.parent.mkdir(parents=True, exist_ok=True)
with binding_path.open('x', encoding='utf-8') as stream:
    json.dump(binding, stream, indent=2)
    stream.write('\n')
archive = root / 'results/cpu_validation/2026-10-11_guard_native_context_preparation'
archive.mkdir()
records = {}
copy_checks = 0
def copy(path, destination):
    global copy_checks
    blob = read(path)
    target = archive / destination
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(blob)
    assert read(target) == blob
    copy_checks += 1
    records[destination] = {'sha256': sha(blob), 'bytes': len(blob), 'original_path': path.relative_to(root).as_posix()}
for directory, destination in [('c4_native_context_diagnostic_staging', 'diagnostic'),
        ('c4_native_context_protocol_staging', 'protocol'),
        ('c4_native_context_review_staging', 'review')]:
    for path in sorted((root / 'external' / directory).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            copy(path, destination + '/' + path.relative_to(root / 'external' / directory).as_posix())
for name in ('promote_guard_native_context_once.py', 'run_guard_native_context_once.py',
             'verify_e_result_delivery_once.py', 'c4_e_result_delivery_01.json'):
    copy(root / 'external' / name, 'root_records/' + name)
report = {'source_sha256': args.source_sha256, 'promoted_source_sha256': sha(promoted),
    'staging_protocol_sha256': args.protocol_sha256, 'formal_protocol_sha256': sha(protocol_bytes),
    'functions_and_classes_ast_identical': True, 'formal_switch_only': True,
    'syntax_compilation': True, 'binding': binding, 'copy_checks': copy_checks, 'failed': 0,
    'execution': {'binary_read_opens': read_opens, 'binary_read_bytes': read_bytes,
        'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
        'timing_scope': 'promotion and copying through report assembly; excludes final report/manifest writes',
        'statistics_reruns': 0, 'real_e_trace_reads': 0, 'model_predictions': 0, 'physics': 0, 'updates': 0}}
report_bytes = (json.dumps(report, indent=2) + '\n').encode('utf-8')
with (archive / 'root_records/promotion.json').open('xb') as stream:
    stream.write(report_bytes)
records['root_records/promotion.json'] = {'sha256': sha(report_bytes), 'bytes': len(report_bytes),
    'original_path': 'root-generated during promotion'}
manifest = {'schema_version': 1, 'kind': 'fixed_native_context_diagnostic_preparation', 'files': records,
    'payload_count': len(records), 'payload_bytes': sum(item['bytes'] for item in records.values()),
    'failed': 0, 'new_physics': 0, 'new_model_predictions': 0, 'new_updates': 0,
    'boundary': 'Engineering preparation only; no actual E descriptive execution or scientific adoption.'}
with (archive / 'manifest.json').open('x', encoding='utf-8') as stream:
    json.dump(manifest, stream, indent=2)
    stream.write('\n')
print(json.dumps({'promotion': report, 'payload_count': len(records), 'payload_bytes': manifest['payload_bytes']}, indent=2))
