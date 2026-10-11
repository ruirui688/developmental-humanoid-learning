"""Seal FR3D copies and update current navigation; no experimental raw reads."""
from pathlib import Path
import hashlib
import json
import re
import time
from urllib.parse import unquote

root = Path(__file__).resolve().parents[1]
dest = root/'results/cpu_validation/2026-10-12_full_request_pair_tradeoff'
assert not dest.exists(), 'first archive exists; no rerun'
wall, cpu = time.perf_counter(), time.process_time()
nav = ('docs/PROGRESS.md', 'docs/CPU_VALIDATION_TARGET.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md', 'README.md', 'AGENTS.md')
texts = {name: (root/name).read_text(encoding='utf-8') for name in nav}
label = 'FR3D保存轴与阶段诊断'
report = 'FULL_REQUEST_PAIR_TRADEOFF_RESULTS.md'
entry = (f'[{label}]({report})已一次完成36,000解码/18,000主组active/72轴窗口统计，0失败、物理、模型或更新。'
         '肘A/B误差与两类努力均增加，切换窗误差下降仍有努力增加；learned purePD仅27/600存在。'
         '只作描述，不识别因果或改判FR3原门。下一唯一FR4以当前PD替换最近nominal点、仍81候选；'
         '原H/cost/权限/停止/校准/20%/5%/1.05门保持，新开发8101/8102/8103先检查冻结再首次A→条件B。'
         '累计430,297控制/2,709,970子步，在线94,452+离线7,200=101,652scalar保持；'
         'C4新留出与C5–C7未验收，提交推送后继续active目标。')

def paragraph(text, anchor, replacement):
    start = text.find(anchor)
    assert 0 <= start < 14000, 'current navigation anchor missing: '+anchor
    end = text.find('\n\n', start)
    return text[:start] + replacement + text[end if end >= 0 else len(text):]

text, count = re.subn(r'^## 当前入口:[^\n]*', '## 历史：FR3B完整控制', texts['docs/PROGRESS.md'], count=1, flags=re.M)
if count == 0:
    text, count = re.subn(r'^## 当前入口：[^\n]*', '## 历史：FR3B完整控制', texts['docs/PROGRESS.md'], count=1, flags=re.M)
assert count == 1
texts['docs/PROGRESS.md'] = text.replace('# 开发进度与仓库检查点\n\n', '# 开发进度与仓库检查点\n\n## 当前入口：'+label+'\n\n'+entry+'\n\n', 1)
texts['docs/CPU_VALIDATION_TARGET.md'] = paragraph(texts['docs/CPU_VALIDATION_TARGET.md'], '[FR3B首次完整首请求匹配控制]', entry)
texts['docs/CONTINUOUS_EXECUTION_PLAN.md'] = paragraph(texts['docs/CONTINUOUS_EXECUTION_PLAN.md'], '- **当前入口FR3B：**', '- **当前入口FR3D：** '+entry)
texts['docs/CONTINUOUS_EXECUTION_PLAN.md'] += '\n\n### FR3D零物理保存诊断与唯一下一判断\n\n'+entry+'\n'
rooted = entry.replace(']('+report+')', '](docs/'+report+')')
texts['README.md'] = paragraph(texts['README.md'], '**当前执行入口：**', '**当前执行入口：** '+rooted)
texts['AGENTS.md'] = paragraph(texts['AGENTS.md'], '[FR3B首次完整首请求匹配控制]', rooted)
pairs = [(path, path.relative_to(root/'external/fr3d_first').as_posix())
         for path in sorted((root/'external/fr3d_first').rglob('*')) if path.is_file()]
pairs += [(root/'external/fr3d_candidate/frozen_design.md', 'frozen_design.md'),
          (root/'external/fr3d_candidate/preparation_receipt.json', 'preparation_receipt.json'),
          (root/'external/fr3d_report_receipt.json', 'report_writing_receipt.json')]
for name in ('prepare_fr3d_once.py', 'run_fr3d_first_once.py', 'write_fr3d_report_once.py', 'archive_fr3d_delivery_once.py'):
    pairs.append((root/'external'/name, 'helpers/'+name))
assert all(source.is_file() for source, name in pairs)
dest.mkdir(parents=True)
pins, read_bytes = {}, 0
for source, name in pairs:
    data = source.read_bytes()
    read_bytes += len(data)
    target = dest/name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    pins[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
for name, text in texts.items():
    (root/name).write_text(text, encoding='utf-8', newline='\n')
manifest = {'stage': 'FR3D_first_delivery', 'files_before_manifest': pins,
    'first_archive': True, 'raw_reads': 0, 'model_fit_RLS_physics_or_scientific_gate_calls': 0,
    'actual_physics_cumulative_unchanged': {'controls': 430297, 'substeps': 2709970,
        'online_scalar': 94452, 'offline_scalar': 7200},
    'seed_first_public_search_root_fact': {'seeds': [8101, 8102, 8103], 'head': 'e589c17d1b331b48162c117f9581825ff6fafd54',
        'command': "rg -n '\\b(8101|8102|8103)\\b' AGENTS.md README.md docs scripts src tests -g '*.py' -g '*.md' -g '*.json' -g '*.toml' -g '*.xml'",
        'exit_code': 1, 'stdout': '', 'raw_nonpublic_or_global_history_not_searched': True,
        'first_search_preceded_FR4_sources': True, 'final_holdout_claim': False},
    'copy_input_reads': len(pairs), 'copy_input_bytes': read_bytes,
    'wall_seconds_before_manifest': time.perf_counter()-wall, 'cpu_seconds_before_manifest': time.process_time()-cpu,
    'scientific_adoption': False, 'continuous_goal_stays_active': True}
(dest/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
links = []
for name in ('docs/'+report, *nav):
    text = (root/name).read_text(encoding='utf-8')
    for target in re.findall(r'\[[^\]\n]*\]\(([^)\n]+)\)', text):
        if name != 'docs/'+report and report not in target:
            continue
        if target.startswith(('http:', 'https:', '#', 'codex:')):
            continue
        path = unquote(target.strip('<>').split('#')[0])
        links.append({'source': name, 'target': path, 'exists': (root/name).parent.joinpath(path).exists()})
value = {'links': links, 'missing': [row for row in links if not row['exists']], 'raw_reads': 0}
(dest/'document_link_check.json').write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
assert not value['missing'], value['missing']
print(json.dumps({'first_archive_complete': True, 'payloads': len(pins), 'links_checked': len(links),
                  'new_raw_reads': 0, 'new_physics_or_models': 0}))
