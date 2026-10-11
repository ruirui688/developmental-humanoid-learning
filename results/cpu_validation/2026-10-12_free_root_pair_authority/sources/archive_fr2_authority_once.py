"""Archive first new authority projection and write its descriptive report."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[1]
dest = root/'results/cpu_validation/2026-10-12_free_root_pair_authority'
assert not dest.exists()
data = (root/'external/fr2_authority_first/description.json').read_bytes()
r = json.loads(data)
assert r['status'] == 'saved_FR2_described' and not r['failures']
dest.mkdir()
pins = {}
def save(name, content):
    target = dest/name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(content)
    pins[name] = {'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
save('description.json', data)
for name in ('stdout.log','stderr.log','first_execution_receipt.json'):
    save('first_execution/'+name, (root/'external/fr2_authority_first'/name).read_bytes())
for name in ('describe_fr2_authority_once.py','STATISTICAL_CONTRACT.md','preparation_receipt.json'):
    save('sources/'+name, (root/'external/fr2_authority_candidate'/name).read_bytes())
for name in ('run_fr2_authority_first_once.py','archive_fr2_authority_once.py',
             'fr2_control_authority_diagnostic_draft.md','fr2_control_authority_diagnostic_receipt.json',
             'fr3_control_design.md'):
    save('sources/'+name, (root/'external'/name).read_bytes())
report = root/'docs/FREE_ROOT_PAIR_AUTHORITY_RESULTS.md'
assert not report.exists()
lines = ['''# FR2：保存动作作用范围的有限诊断

[原完整控制结果](FREE_ROOT_PAIR_CONTROL_RESULTS.md)的模型贡献门仍失败，C4及C5–C7未验收。本次仅对其已保存请求和决策做一次描述，不新增物理、模型调用、辨识或科学门重算。

第一次执行完整读取36,000行、1,200个决策、97,200个候选记录，0失败；manifest/run/trace各读一次，共52,365,398 bytes，内部wall/CPU为7.5490434/7.46875秒。原始数据身份、全部12组的A/B/full统计及缺失分母见[完整JSON](../results/cpu_validation/2026-10-12_free_root_pair_authority/description.json)，首次stdio、源码和[统计契约](../results/cpu_validation/2026-10-12_free_root_pair_authority/sources/STATISTICAL_CONTRACT.md)一并保留。

## 新保存的描述

下表转录各完整模型组全2,000起点统计；PD饱和率仅以保存PD已知点为分母，cold每条10个fallback点没有保存PD，保持缺失。边界选择以保存的非fallback macro为分母，最终请求反向不等同于实际力矩反向。

| seed/方法 | PD已知起点 | 肩/肘PD饱和计数 | residual效果已知起点 | 肩/肘平均绝对请求修正Nm | 肩/肘零效果非零delta计数 | 非fallback决策 | 肩/肘选±.125边界次数 | fallback决策 |
|---|---:|---|---:|---|---|---:|---|---:|
''']
def pair(value):
    return '/'.join(f'{x:.8g}' if isinstance(x,float) else str(x) for x in value)
for row in r['matrix']:
    if row['method'] not in ('cold','learned'):
        continue
    s=row['phases']['full']; e=s['residual_effect']; m=s['macro']
    lines.append(f"| {row['seed']}/{row['method']} | {s['saved_PD']['known_origins']} | {pair(s['saved_PD']['counts_axis'])} | {e['known_nonfallback_origins']} | {pair(e['mean_absolute_effect_axis_nm'])} | {pair(e['direction_counts_axis']['nonzero_delta_zero_effect'])} | {m['selected_residual_known']} | {pair(m['selected_boundary_counts_axis'])} | {m['fallback_true']} |\n")
lines.append('''
三个learned组全部200个macro的81候选均可行；肩179/182/182次、肘各198次选到残差边界。肩的公共PD在359/370/372个起点饱和，对应这些非零修正被clip为零；肘仅16个起点PD饱和，残差平均效果为.12375Nm。因此不能把收益不足统称为“双轴一直饱和”，也不能把不同行为人口作为反事实比较。

全部六条模型轨迹两轴q起点均有1995/2000落在各自校准轴向范围之外；速度越域与其他方法/phase完整统计见JSON。这是保存范围的转录，范围盒不代表接触或预测有效域，本轮不筛选起点或按越域重拟合。

## 决策与限制

现有结构只允许在clip后的PD上叠加±.125Nm。当|PD|>.125时不能通过非fallback修正反转当前请求；很多保存决策选择边界，支持检验这个函数类限制，但不证明它导致原20%门失败。相同首请求的候选在后续反馈中可能分叉，旧81候选不按首请求去重。

下一唯一候选采用九点完整首请求网格[-.5,.5]，spacing=.125Nm，按当前PD换算held delta；最终权限保持±.5Nm，首10步反馈/后140步PD尾、成本、原预测/20%贡献/5%强PD/努力门保留。它扩大函数类、改变分辨率且通常不包含纯PD候选，须披露，并另用固定新开发bank辨识、独立预测和完整控制。此处不预告收益，不修改旧结果，不做网格/权重/seed扫描。

阶段检查、提交推送后继续active目标；FR3即使通过仍需C4最终新留出、C5适应、C6门控、C7综合验收。
''')
report.write_text(''.join(lines), encoding='utf-8', newline='\n')
manifest={'status':r['status'],'files':pins,'raw_not_reread_by_archive_helper':True,
    'new_physics_or_models_or_fit':0,'science_gates_unchanged':True,
    'continuous_goal_stays_active':True}
save('manifest.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'authority_archived':True,'payloads_before_manifest':len(pins)-1,
    'report':str(report),'raw_or_model_or_fit_or_physics':0}))
