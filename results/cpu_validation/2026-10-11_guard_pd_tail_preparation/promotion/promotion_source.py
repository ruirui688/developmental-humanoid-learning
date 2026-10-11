"""Promote sealed G engineering bytes; no model, math or physics execution."""
import ast
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'external/c4_g_promotion_01'
OUT.mkdir(exist_ok=False)
wall, cpu = time.perf_counter(), time.process_time()
rows = [
    ('external/c4_pd_tail_mpc_staging/pd_tail_pair_mpc.py',
     'src/developmental_physics/pd_tail_pair_mpc.py',
     '6d1af186eb02e033a31fcc294eedd38fa743a418a69d16744350fa02aec3beed',
     'FORMAL_PD_TAIL_CONTROL_ENABLED'),
    ('external/c4_pd_tail_control_runner_staging/pd_tail_control_development.py',
     'src/developmental_physics/pd_tail_control_development.py',
     '47407917ff7ac184ab7f0859a6fb63d30946805e3ad23cc4268d3eae4b115720',
     'FORMAL_CONTROL_ENABLED'),
    ('external/c4_pd_tail_control_audit_staging/audit_guard_pd_tail_control.py',
     'scripts/audit_guard_pd_tail_control.py',
     '38322b00e04782a640f989ddc568d06e27c6fc8e5e18b68bfe0f9807cf38483a',
     'FORMAL_AUDIT_ENABLED'),
]
checks, records, read_bytes = [], [], 0
for original, canonical, expected, flag in rows:
    data = (ROOT / original).read_bytes(); read_bytes += len(data)
    assert hashlib.sha256(data).hexdigest() == expected, original
    checks.append(original + ':sealed_sha')
    source = data.decode('utf-8')
    before = ast.parse(source)
    marker = flag + (' = False' if flag != 'FORMAL_AUDIT_ENABLED' else '=False')
    assert source.count(marker) == 1
    source = source.replace(marker, marker.replace('False', 'True'))
    if flag == 'FORMAL_PD_TAIL_CONTROL_ENABLED':
        source = source.replace('Unselected engineering draft: first-free request with fixed PD tail.',
                                'Frozen G development: first-free request with fixed PD tail.')
        source = source.replace('A formal experiment is not authorized.',
                                'Formal execution follows the byte-bound G protocol.')
    target = ROOT / canonical
    assert not target.exists(), canonical
    result = source.encode('utf-8')
    target.write_bytes(result)
    reread = target.read_bytes(); read_bytes += len(reread)
    assert reread == result
    after = ast.parse(source)
    before.body = before.body[1:]; after.body = after.body[1:]
    for node in after.body:
        if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == flag for n in node.targets):
            assert node.value.value is True
            node.value.value = False
    assert ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)
    checks.extend([canonical + ':exact_copy', canonical + ':formal_only_AST'])
    records.append({'original': original, 'canonical': canonical,
        'original_sha256': expected, 'production_sha256': hashlib.sha256(result).hexdigest(),
        'bytes': len(result), 'formal_flag': flag, 'formal_enabled': True})
draft = (ROOT / 'external/c4_pd_tail_protocol_staging/G_PROTOCOL_DRAFT.md').read_bytes()
read_bytes += len(draft)
text = draft.decode('utf-8').replace(
    '前瞻开发草稿，代码、独立审计和来源尚待冻结提交；当前不放行物理。',
    '冻结开发协议：生产代码、独立审计和原件在首次物理前正常提交推送；仅允许从干净提交执行一次。')
text += '\n## 已封口工程证据\n\n新反馈尾5项数学检查通过；collector44项通过（18项复用、26项新增）；独立auditor首次27项通过。有限来源/API审查无待修项。原工程失败与检查费用保留于[准备归档](../results/cpu_validation/2026-10-11_guard_pd_tail_preparation/manifest.json)，不重跑这些已通过检查。三个正式开关同步开启只是允许本冻结开发矩阵，不表示科学验收通过。\n'
path = ROOT / 'docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md'
assert not path.exists()
path.write_bytes(text.encode('utf-8'))
records.append({'canonical': str(path.relative_to(ROOT)).replace('\\', '/'),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
report = {'checks': len(checks), 'failed': 0, 'check_labels': checks, 'records': records,
    'read_accounting': {'explicit_binary_opens': 8, 'binary_bytes': read_bytes + path.stat().st_size,
       'coverage': 'sealed sources, promoted rereads, draft and frozen protocol; excludes interpreter/OS I/O'},
    'wall_seconds': time.perf_counter()-wall, 'cpu_seconds': time.process_time()-cpu,
    'new_math_model_physics_updates': 0}
(OUT / 'promotion.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
(OUT / 'promotion_source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(report, indent=2))
