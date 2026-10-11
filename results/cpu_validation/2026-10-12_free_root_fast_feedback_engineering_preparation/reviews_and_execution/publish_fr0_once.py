"""Publish FR0 after Z2 archival; normalize LF and bind only final protocol pin."""
import ast
import hashlib
import json
from pathlib import Path
import time

repo = Path(__file__).resolve().parents[1]
assert (repo / 'results/cpu_validation/2026-10-12_fast_feedback_pair_control/manifest.json').is_file(), 'archive first Z2 result before publication'
origin = repo / 'external/c4_free_feedback_candidate'
receipt = repo / 'external/fr0_publication.json'
if receipt.exists():
    raise FileExistsError(receipt)
mapping = {
 'free_root_fast_feedback_environment.py': 'src/developmental_physics/free_root_fast_feedback_environment.py',
 'validate_free_root_fast_feedback_engineering.py': 'scripts/validate_free_root_fast_feedback_engineering.py',
 'test_free_root_fast_feedback_engineering.py': 'tests/test_free_root_fast_feedback_engineering.py'}
protocol_path = 'docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md'
assert not any((repo / name).exists() for name in [*mapping.values(), protocol_path])
began, cpu = time.perf_counter(), time.process_time()
def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
protocol_original = (repo / 'external/FR0_ENGINEERING_PROTOCOL_CANDIDATE.md').read_bytes()
assert identity(protocol_original) == {'bytes': 9381, 'sha256': '41e9c323c51e4c3bc0e1f6cf4ea7e47c72b2c60777f3d8f2762839a0ff9011d3'}
protocol_text = protocol_original.decode('utf-8').replace('\r\n', '\n')
lines = protocol_text.splitlines()
assert lines[2].startswith('状态：事前外部候选')
lines[2] = '本协议在首次FR0数据产生前确定，参数不依赖Z2揭晓结果。生产源码与必要新纯检查先冻结，正常提交推送后从干净提交首次执行一次；Z2首次结果须先完成归档。本阶段不使用学习模型、fit、MPC或教师。'
protocol = ('\n'.join(lines).rstrip()+'\n').encode('utf-8')
pin = identity(protocol)
with (repo / protocol_path).open('xb') as stream:
    stream.write(protocol)
files = {protocol_path: {'original': identity(protocol_original), 'published': pin, 'change': 'status header only; thresholds/budget/conditions unchanged'}}
preparation = json.loads((origin / 'preparation_receipt.json').read_bytes())
def without_pin(tree):
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PROTOCOL_PIN' for t in n.targets))]
    return ast.dump(tree, include_attributes=False)
for basename, destination in mapping.items():
    original = (origin / basename).read_bytes()
    assert identity(original) == preparation['files'][basename]
    normalized = original.replace(b'\r\n', b'\n')
    if basename.startswith('validate_'):
        text = normalized.decode('utf-8')
        assert text.count('PROTOCOL_PIN = None') == 1
        text = text.replace('PROTOCOL_PIN = None', 'PROTOCOL_PIN = '+repr(pin))
        normalized = text.encode('utf-8')
        assert without_pin(ast.parse(original)) == without_pin(ast.parse(normalized))
    else:
        assert ast.dump(ast.parse(original), include_attributes=False) == ast.dump(ast.parse(normalized), include_attributes=False)
    path = repo / destination
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(normalized)
    files[destination] = {'original': identity(original), 'published': identity(normalized), 'CRLF_to_LF_count': original.count(b'\r\n'), 'AST_equivalent_except_publication_pin': True}
record = {'status': 'published_before_first_new_checks', 'files': files, 'wall_seconds': time.perf_counter()-began, 'cpu_seconds': time.process_time()-cpu, 'external_originals_modified': False, 'model_fit_physics_or_test_calls': 0, 'automatic_retry': False}
with receipt.open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2, allow_nan=False)
print(json.dumps(record))
