# 2026-10-10：CPU 失效边界实验归档

本批按 [冻结协议](../../../docs/CPU_FAILURE_PROTOCOL.md)运行 8 场景 × 3 种子 × 6 方法，共 144 次无训练诊断。协议先提交为 `28723a5`；实际执行使用干净的源码提交 `357a2799c6329108497d94c73e3bbae7a6dbc97b`，运行期间源码未改变。

计划上限 64,800 步，实际 63,887 步，报告内耗时 69.0788707 s。140 次完成，4 次状态限位退出，没有非有限退出。模型与策略参数更新均为 0，门控与模型的固定参数指纹保持一致。

关键结果：持续 0.60 s 延迟使完整权限规划三个种子全部位置越界；持续失败退级变体使增益下降后的完整目标 RMSE 从 0.031824 增至 0.039735 rad（+24.86%）。变体仅作为诊断对照保留，原门控仍为默认。更多退级、较低权限或没有退出都不能单独解释为控制能力提高。详见 [结果与研究决策](../../../docs/CPU_FAILURE_RESULTS.md)。

## 文件

- [report.json](report.json)：144 个运行、逐窗口与阶段指标、固定配置、真实场景参数、Git/环境版本与指纹。
- [gates.json](gates.json)：原门控和变体的全部真实闭环事件。
- [trace.csv.gz](trace.csv.gz)：63,887 个逐步记录，区分当前命令、历史命令、执行源权限与增益后的有效力矩。
- [source_snapshot.zip](source_snapshot.zip)：运行时 7 个 Python 模块的精确字节。
- [summary.png](summary.png)：派生图；左侧展示 4 个方法的后半段误差及早停缺失，右侧展示增益下降后的表现和权限。所有 6 个方法的完整指标仍在报告中。
- [manifest.json](manifest.json)：文件字节数、SHA-256、源代码校验值和协议校验值。JSON 行尾规范化为 LF；轨迹和源码压缩包保留原始内容。

这是稳定受支撑双关节诊断，没有人形平衡、接触切换或真实机器人。命令限额不等于未知执行器增益下的物理力矩保护，软件退级也不能立即撤销历史延迟命令。

## 复核

在仓库根目录运行以下脚本，验证压缩快照及 Git 中的实际运行版本；无需当前工作区源码始终停留在实验版本。

```powershell
@'
import csv, gzip, hashlib, json, subprocess, zipfile
from pathlib import Path
p = Path('results/cpu_validation/2026-10-10_failure_boundary')
m = json.loads((p / 'manifest.json').read_text(encoding='utf-8'))
for name, info in m['files'].items():
    data = (p / name).read_bytes()
    assert len(data) == info['bytes']
    assert hashlib.sha256(data).hexdigest() == info['sha256']
with zipfile.ZipFile(p / 'source_snapshot.zip') as z:
    for name, expected in m['source_sha256'].items():
        assert hashlib.sha256(z.read(name)).hexdigest() == expected
        committed = subprocess.check_output(['git', 'show', m['source_commit'] + ':' + name])
        assert hashlib.sha256(committed).hexdigest() == expected
protocol = subprocess.check_output(['git', 'show', m['source_commit'] + ':docs/CPU_FAILURE_PROTOCOL.md'])
assert hashlib.sha256(protocol).hexdigest() == m['protocol_sha256']
with gzip.open(p / 'trace.csv.gz', 'rt', encoding='utf-8', newline='') as f:
    assert sum(1 for _ in csv.DictReader(f)) == m['total_executed_steps']
print('Archive, execution commit, protocol and trace counts verified')
'@ | python -
```

## 复现

在对应版本及兼容 Python/NumPy 环境中复现时使用新输出目录，避免覆盖本归档：

```powershell
$env:PYTHONPATH = 'src'
python -m developmental_control.stress --output results/cpu_validation/failure_reproduction
python scripts/plot_cpu_failure_boundary.py results/cpu_validation/failure_reproduction/report.json
```

固定轨迹应可复现；墙钟耗时、动作选择延迟、创建时间和 Git 元数据随机器及提交状态变化。再次运行不包含参数训练，但应保留本批失败记录和协议。
