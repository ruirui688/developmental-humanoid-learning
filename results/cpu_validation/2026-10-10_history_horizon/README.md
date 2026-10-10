# 2026-10-10：CPU 指令历史与预测时域实验归档

按 [冻结协议](../../../docs/CPU_HISTORY_PROTOCOL.md)运行 8 场景 × 3 种子 × 5 方法，共 120 次 CPU 无训练诊断。协议和实现先提交为 [`9829e6b`](https://github.com/ruirui688/developmental-humanoid-learning/commit/9829e6ba7f6e7ea149b1e15188bf6275b5443c84)；实际执行工作区干净，运行期间源码、协议及 Git 状态未改变。

实际执行 53,179 步（上限 54,000），报告内耗时 168.4671654 s，116 次完成、4 次位置限位退出、0 次非有限退出。模型、策略及声明延迟更新次数为 0。规划内部推进 73,283,420 次，诊断单步预测 159,537 次，分别计账。CPU 为 Intel Core i5-11320H，4 核 8 线程；Python/NumPy 版本与操作系统见报告。

在相同 H50 时域中，已知初始延迟的历史预测使恒定 0.60 s 延迟场景的全目标 RMSE 从 0.032391 降至 0.023457 rad，约降低 27.58%。短时域历史组在延迟 15、30 和 15→30 场景全程零命令；H50 在名义和增益下降场景又比 H20 更差。不能将低预测残差、较长时域或无退出单独当作控制收益。声明初始延迟是提供的先验，实验没有辨识或更新它。详见 [结果与研究决策](../../../docs/CPU_HISTORY_RESULTS.md)。

## 文件

- [report.json](report.json)：120 个运行、逐阶段/半程指标、96 组共同前缀对照、固定配置、Git/环境版本与指纹。
- [trace.csv.gz](trace.csv.gz)：53,179 条逐步记录，包括当前命令、自有历史长度、推断/实际作用命令、三类预测残差、真实场景参数及有效力矩。
- [gates.json](gates.json)：空列表，本批固定全权限，没有运行门控。
- [source_snapshot.zip](source_snapshot.zip)：运行时 9 个 Python 模块的精确字节，逐字节匹配实际执行提交。
- [summary.png](summary.png)：冻结数据派生图，保留逐种子误差、不利结果和早停计数。
- [audit.json](audit.json)：另一位审查智能体编写独立实现后产生的离线核验摘要；未导入控制代码或重跑规划器。
- [manifest.json](manifest.json)：文件字节数、SHA-256、源码与协议校验值、后处理脚本和版本。JSON 行尾规范化为 LF；CSV gzip 和源码 ZIP 保留原始内容。

这是稳定受支撑双关节模型，没有重力失稳、接触切换、G1 或真机结果。增益 0.25 的静态目标仍在最高权限内；增益 0.125 所需命令超过硬命令限额。静态可达性只作离线计算，没有传入控制器。更低残差不代表身体模型已经学习，更低误差也不能消除初始先验和计算成本。

## 复核

在仓库根目录验证归档字节与实际运行版本：

```powershell
@'
import csv, gzip, hashlib, json, subprocess, zipfile
from pathlib import Path
p = Path('results/cpu_validation/2026-10-10_history_horizon')
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
protocol = subprocess.check_output(['git', 'show', m['source_commit'] + ':docs/CPU_HISTORY_PROTOCOL.md'])
assert hashlib.sha256(protocol).hexdigest() == m['protocol_sha256']
with gzip.open(p / 'trace.csv.gz', 'rt', encoding='utf-8', newline='') as f:
    assert sum(1 for _ in csv.DictReader(f)) == m['total_executed_steps']
print('Archive, execution commit, protocol and trace counts verified')
'@ | python -
```

若要重新手算动力学、三类预测、历史索引、阶段/共同前缀指标和计时聚合，可使用 [独立离线审计脚本](../../../scripts/audit_cpu_history_archive.py)：

```powershell
python scripts/audit_cpu_history_archive.py results/cpu_validation/2026-10-10_history_horizon
```

该脚本不执行控制矩阵；审计者是另一位代码智能体，不构成外部团队复现实验。

## 复现

在对应执行版本和兼容 Python/NumPy 环境中使用新的输出目录。绘图和审计脚本属于结果分析提交，原执行提交只含仿真与测试。

```powershell
$env:PYTHONPATH = 'src'
python -m developmental_control.history --output results/cpu_validation/history_reproduction
python scripts/plot_cpu_history_summary.py results/cpu_validation/history_reproduction/report.json
```

固定数值轨迹应可复现；墙钟耗时、动作选择延迟、创建时间和 Git 元数据随机器及提交状态变化。运行器拒绝覆盖非空输出目录。复现仍没有参数训练，不应覆盖本归档或删除失败记录。
