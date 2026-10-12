"""Publish own stage facts from the report-writing receipt, without raw reads."""
from pathlib import Path
import argparse
import hashlib
import json
import re

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=('prediction', 'control'), required=True)
parser.add_argument('--gates', choices=('passed', 'failed', 'unavailable'), required=True)
args = parser.parse_args()
stage = 'FR4A' if args.stage == 'prediction' else 'FR4B'
receipt_path = root / f'external/fr4_report_candidate/{stage.lower()}_report_writing_receipt.json'
receipt_bytes = receipt_path.read_bytes()
receipt = json.loads(receipt_bytes)
assert receipt['status'] == 'written'
archive = root / f'results/cpu_validation/2026-10-12_pd_anchor_pair_{args.stage}'
out = archive / 'navigation_update'
assert not out.exists(), 'navigation update already done'
out.mkdir()
base, totals, inc = (receipt[key] for key in ('historical_baseline', 'cumulative_after_stage', 'actual_saved_increment'))
audit = receipt['first_audit_from_root_CLI']
assert all(type(totals[key]) is int for key in ('controls', 'substeps', 'online_scalar', 'offline_scalar'))
assert totals['controls'] == base['controls'] + inc['control_returns']
assert totals['substeps'] == base['substeps'] + inc['confirmed_substeps']
assert totals['online_scalar'] == base['online_scalar'] + inc['online_scalar_commits']
assert totals['offline_scalar'] == base['offline_scalar']
report = f'PD_ANCHOR_PAIR_{args.stage.upper()}_RESULTS.md'
outcome = ('原独立预测门通过' if args.gates == 'passed' else '原独立预测门未通过/不可评') if stage == 'FR4A' else (
          '本域原完整控制门通过' if args.gates == 'passed' else '本域原完整控制门未全部通过/不可评')
continuation = ('提交推送后立即执行在A数据前已冻结的FR4B，19项依赖字节保持相同。' if args.gates == 'passed' else
                'FR4B保持关闭，依据本次证据作唯一有限下一判断。') if stage == 'FR4A' else (
               '随后另冻结对应候选的新留出C4验证；原FR3前置未通过的旧设计不直接启动。' if args.gates == 'passed' else
               '关闭本冻结候选成功依赖，保留负结果后继续有依据的有限开发判断，不扫描增益、权重或网格。')
entry = (f'[{stage}首次PD锚点{ "身体预测" if stage == "FR4A" else "完整控制"}]({report})'
         f'从clean{receipt["source_commit"][:7]}完成，{outcome}；实际新增'
         f'{inc["control_returns"]:,}控制/{inc["confirmed_substeps"]:,}子步/{inc["online_scalar_commits"]:,}在线scalar。'
         f'首新保存核验{audit["status"]}、{audit["checks"]:,}项/{audit["failed"]:,}失败，'
         f'{audit["new_RMSE_vectors"]}个新RMSE向量；完整人口、实际努力与停止原样公开。'
         f'累计{totals["controls"]:,}/{totals["substeps"]:,}，online{totals["online_scalar"]:,}'
         f'+offline{totals["offline_scalar"]:,}={totals["online_scalar"]+totals["offline_scalar"]:,}scalar。'
         f'{continuation} C4最终新留出及C5适应、C6门控、C7综合未验收，持续目标active。')
rooted = entry.replace(f']({report})', f'](docs/{report})')
def first_paragraph(text, marker, replacement):
    index = text.index(marker)
    assert index < 15000, marker
    end = text.find('\n\n', index)
    assert end >= 0
    return text[:index] + replacement + text[end:]
nav = ('AGENTS.md', 'README.md', 'docs/CONTINUOUS_EXECUTION_PLAN.md', 'docs/CPU_VALIDATION_TARGET.md', 'docs/PROGRESS.md')
for name in nav:
    path = root / name
    text = path.read_text(encoding='utf-8')
    previous = '[FR4 PD锚点协议]' if stage == 'FR4A' else '[FR4A首次PD锚点身体预测]'
    if name == 'AGENTS.md':
        text = first_paragraph(text, previous, rooted)
        pattern = r'正式物理累计 \*\*([\d,]+)控制调用 /([\d,]+)子步\*\*；'
        match = re.search(pattern, text)
        assert match and tuple(int(v.replace(',', '')) for v in match.groups()) == (base['controls'], base['substeps'])
        text = text[:match.start()] + f'正式物理累计 **{totals["controls"]:,}控制调用 /{totals["substeps"]:,}子步**；{stage}新增{inc["control_returns"]:,}/{inc["confirmed_substeps"]:,}/{inc["online_scalar_commits"]:,}在线scalar；' + text[match.end():]
        scalar_pattern = r'当前在线([\d,]+)\+离线([\d,]+)=([\d,]+)scalar更新'
        match = re.search(scalar_pattern, text)
        assert match and tuple(int(v.replace(',', '')) for v in match.groups()) == (base['online_scalar'], base['offline_scalar'], base['online_scalar']+base['offline_scalar'])
        text = text[:match.start()] + f'当前在线{totals["online_scalar"]:,}+离线{totals["offline_scalar"]:,}={totals["online_scalar"]+totals["offline_scalar"]:,}scalar更新' + text[match.end():]
    elif name == 'README.md':
        text = first_paragraph(text, '**当前执行入口：**', '**当前执行入口：** ' + rooted)
    elif name == 'docs/CONTINUOUS_EXECUTION_PLAN.md':
        current = '- **当前入口FR4：**' if stage == 'FR4A' else '- **当前入口FR4A：**'
        text = first_paragraph(text, current, f'- **当前入口{stage}：** ' + entry)
        pattern = r'当前累计 \*\*([\d,]+) 控制调用 / ([\d,]+) 子步 / ([\d,]+) 在线scalar及([\d,]+)离线重放scalar\*\*，scalar计算合计(\d+)'
        match = re.search(pattern, text)
        assert match and tuple(int(v.replace(',', '')) for v in match.groups()) == (base['controls'], base['substeps'], base['online_scalar'], base['offline_scalar'], base['online_scalar']+base['offline_scalar'])
        text = text[:match.start()] + f'{stage}实际新增{inc["control_returns"]:,}/{inc["confirmed_substeps"]:,}/{inc["online_scalar_commits"]:,}在线scalar；当前累计 **{totals["controls"]:,} 控制调用 / {totals["substeps"]:,} 子步 / {totals["online_scalar"]:,} 在线scalar及{totals["offline_scalar"]:,}离线重放scalar**，scalar计算合计{totals["online_scalar"]+totals["offline_scalar"]}' + text[match.end():]
        text += f'\n\n### {stage}首次结果与立即继续\n\n' + entry + '\n'
    elif name == 'docs/CPU_VALIDATION_TARGET.md':
        text = first_paragraph(text, previous, entry)
    else:
        marker = '# 开发进度与仓库检查点\n\n'
        assert text.startswith(marker)
        text = text.replace('## 当前入口：', '## 历史：', 1)
        text = text.replace(marker, marker + f'## 当前入口：{stage}首次结果与持续推进\n\n' + entry + '\n\n', 1)
    path.write_text(text, encoding='utf-8', newline='\n')
facts = {'stage': stage, 'only_input_receipt': {'path': str(receipt_path), 'bytes': len(receipt_bytes),
         'sha256': hashlib.sha256(receipt_bytes).hexdigest()}, 'root_transcribed_gate_state': args.gates,
         'baseline': base, 'actual_increment': inc, 'cumulative': totals,
         'scientific_recomputations_or_raw_reads': 0, 'continuous_goal_stays_active': True}
(out / 'receipt.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
(out / 'source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(facts, ensure_ascii=False))
