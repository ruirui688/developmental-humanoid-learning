"""Seal first FR4 checks and publish navigation without recomputing science."""
from pathlib import Path
import ast
import hashlib
import json
import re
import time

root = Path(__file__).resolve().parents[1]
destination = root / 'results/cpu_validation/2026-10-12_pd_anchor_pair_preparation'
assert not destination.exists()
contract = json.loads((root / 'external/fr4_first_mapping_contract/contract.json').read_bytes())
assert contract['status'] == 'passed' and not contract['failures']
assert len(contract['checks']) == 58
wall, cpu = time.perf_counter(), time.process_time()
pins = {}
def identity(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
def save(name, data):
    path = destination / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
    pins[name] = identity(data)
def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
destination.mkdir()
runner = root / 'scripts/develop_pd_anchor_pair.py'
original = runner.read_bytes()
assert identity(original) == {'bytes': 29340, 'sha256': '725ca104423c141b8207839b71951fac419735aa3fea2d0087eda0cdd2d890d4'}
normalized = original.replace(b'\r\n', b'\n')
assert ast.dump(ast.parse(original), include_attributes=False) == ast.dump(ast.parse(normalized), include_attributes=False)
save('external_originals/runner_before_EOL_normalization.py', original)
runner.write_bytes(normalized)
sources = ('docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md',
           'scripts/develop_pd_anchor_pair.py',
           'src/developmental_physics/pd_anchor_pair_mpc.py',
           'src/developmental_physics/pd_anchor_pair_development.py')
source_pins = {name: identity((root / name).read_bytes()) for name in sources}
protocol_pin = next(node.value for node in ast.parse(normalized).body
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PROTOCOL_PIN' for t in node.targets))
assert ast.literal_eval(protocol_pin) == source_pins[sources[0]]
for folder, prefix in (('external/fr4_controller_candidate', 'external_originals/controller'),
                       ('external/fr4_first_mapping_contract', 'first_mapping_contract')):
    for path in sorted((root / folder).iterdir()):
        if path.is_file():
            save(prefix + '/' + path.name, path.read_bytes())
for name in ('run_fr4_mapping_first_once.py', 'run_fr4_physics_first_once.py', 'publish_fr4_preparation_once.py'):
    save('root_helpers/' + name, (root / 'external' / name).read_bytes())
save('protocol.md', (root / sources[0]).read_bytes())
entry = ('[FR4 PD锚点协议](PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md)与新控制器、采集器和入口已完成准备。'
         '首次新映射契约58项通过，48,600 pair/97,200 scalar前向，0物理/fit/RLS；'
         'runner仅行尾归一化，AST相同且协议pin匹配。新开发seed8101/8102/8103，'
         '先执行FR4A身体辨识与独立预测，原全部门通过后才执行已冻FR4B完整控制。'
         '候选仍81对，每轴当前PD替换最近原槽；纯PD可表达不保证可行、被选或收益。'
         '保留原任务、H150、权限、努力与20%/5%门。累计430,297控制/2,709,970子步、'
         '101,652 scalar更新保持；C4新留出及C5适应、C6门控、C7综合未验收。'
         '持续目标active，检查、提交、推送后立即首次执行。')
def replace_paragraph(text, start, replacement):
    assert start in text, start
    old = start + text.split(start, 1)[1].split('\n\n', 1)[0]
    assert text.count(old) == 1
    return text.replace(old, replacement, 1)
rooted = entry.replace('](PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md)', '](docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md)')
nav = ('AGENTS.md', 'README.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md', 'docs/CPU_VALIDATION_TARGET.md', 'docs/PROGRESS.md')
for name in nav:
    path = root / name
    text = path.read_text(encoding='utf-8')
    if name == 'AGENTS.md':
        text = replace_paragraph(text, '[FR3D保存轴与阶段诊断]', rooted)
    elif name == 'README.md':
        text = replace_paragraph(text, '**当前执行入口：**', '**当前执行入口：** ' + rooted)
    elif name == 'docs/CONTINUOUS_EXECUTION_PLAN.md':
        text = replace_paragraph(text, '- **当前入口FR3D：**', '- **当前入口FR4：** ' + entry)
        text += '\n\n### FR4准备与连续执行入口\n\n' + entry + '\n'
    elif name == 'docs/CPU_VALIDATION_TARGET.md':
        text = replace_paragraph(text, '[FR3D保存轴与阶段诊断]', entry)
        text = replace_paragraph(text, '新FR3仅检验', '新FR4只检验PD锚点候选包含性修订；预测与控制在新数据前一并冻结。C4开发和新留出验收后，依次进入C5未知动力学适应、C6成熟机制和C7综合验收。')
    else:
        text = text.replace('## 当前入口：FR3D保存轴与阶段诊断', '## 历史：FR3D保存轴与阶段诊断', 1)
        marker = '# 开发进度与仓库检查点\n\n'
        assert text.startswith(marker)
        text = text.replace(marker, marker + '## 当前入口：FR4 PD锚点准备与首次执行\n\n' + entry + '\n\n', 1)
    path.write_text(text, encoding='utf-8', newline='\n')
links = []
for name in (sources[0], *nav):
    path = root / name
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):
            continue
        if name != sources[0] and 'PD_ANCHOR_PAIR_' not in target:
            continue
        exists = (path.parent / target.split('#', 1)[0]).resolve().exists()
        links.append({'document': name, 'target': target, 'exists': exists})
assert all(row['exists'] for row in links)
save('publication.json', encoded({'source_files': source_pins, 'runner_original': identity(original),
     'runner_EOL_only_AST_equal': True, 'protocol_pin_matches': True,
     'first_new_contract_checks': len(contract['checks']), 'first_contract_cost': contract['cost'],
     'new_physics_fit_RLS_or_old_reexecution': 0, 'continuous_goal_stays_active': True,
     'static_review_scope': 'PD-only nearest-slot replacement; scalar/batch decision and original core AST contract',
     'new_development_seed_search_evidence': 'previous FR3D manifest; public source/document integer search only, not all raw/history'}))
save('navigation_checks.json', encoded({'checks': len(links), 'failed': 0, 'links': links}))
save('manifest.json', encoded({'files_before_manifest': pins.copy(), 'published_sources': source_pins,
     'first_mapping_contract_passed': True, 'scientific_adoption': False,
     'continuous_goal_stays_active': True, 'wall_before_manifest': time.perf_counter()-wall,
     'cpu_before_manifest': time.process_time()-cpu}))
print(json.dumps({'source_pins': source_pins, 'new_checks': len(contract['checks']),
     'copied_files_before_manifest': len(pins)-1, 'links_checked': len(links), 'new_physics_fit_RLS': 0}))
