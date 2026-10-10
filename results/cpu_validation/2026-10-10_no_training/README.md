# 2026-10-10：CPU 无训练机制验证归档

本归档保存固定模型控制、动作权限与能力门控的工程验证，不是学习效率实验。没有 PPO、监督拟合或递推辨识更新；模型与策略参数更新均为 0。

## 内容与结果

- [report.json](report.json)：完整配置、45 个逐场景/seed/方法记录及各自的统一权限评估、环境版本、源码与参数指纹。
- [gate_events.json](gate_events.json)：每个门控窗口的证据、决策与计数。
- [trace.csv.gz](trace.csv.gz)：原始 CSV 字节流的 gzip 压缩，包含 14,625 个仿真步；压缩时间戳固定为 0。
- [source_snapshot.zip](source_snapshot.zip)：运行时五个 Python 源文件的精确字节，保留原始源码 SHA-256。
- [manifest.json](manifest.json)：文件字节数、SHA-256、源码 SHA-256 和运行/整合的 Git 基点。

3 个初态 seed × 3 个场景 × 5 种控制模式，共 45 个机制运行和 45 个统一权限评估，耗时 13.1442613 s。九个门控运行共晋级 18 次、退级 0 次。本批没有状态超限或非有限退出；夹具本身稳定，不能由此推出机器人安全性或门控降低风险。实际失配下的退级尚未观察到，退级逻辑仅通过合成证据测试。

两个受支撑弹簧阻尼关节不包含人形平衡或接触切换。控制器已有固定标称模型、目标和手设规则；三种规划模式的统一权限评估完全相同，是模型没有更新的预期结果。完整解释见 [CPU 验证说明](../../../docs/CPU_VALIDATION.md)。

## 实验与提交的时间关系

原始运行基于本地 `6abcf26b5bd50e1ebfd21071db21ed45aa5ce503` 加当时未提交的 CPU 模块。报告的 `git` 字段保留该状态，不改写历史。

准备提交时发现远端已有 21 个后续提交，随后快进同步到 `7363880486262fbd8e2aafe102981a782989aa86`，并保留原有 PBHC/Isaac Gym G1 代码与结果。提交前为通过空白检查，仅删除 `__init__.py`、`joints.py`、`planning.py` 末尾的多余空行，没有改变算法或参数。原始 `source_sha256` 对应 ZIP 中的精确源码；`committed_source_sha256` 对应清理后的仓库源码，两组校验值分别保存。

JSON 行尾规范化为 LF，清单记录归档文件的校验值；压缩轨迹保留原始 CSV 字节。未压缩输出与精确源码副本也保留在运行机器的 `results/cpu_validation/final/`。

同步前 CPU 测试为 44 项；整合后的 CPU 回归检查为 101 项全部通过。此处的历史 G1 数据来自其他环境，没有在本轮 CPU 会话中复现。

## 复核与复现

在仓库根目录复核文件与源码：

```powershell
@'
import hashlib, json, zipfile
from pathlib import Path
p = Path('results/cpu_validation/2026-10-10_no_training')
m = json.loads((p / 'manifest.json').read_text(encoding='utf-8'))
for name, info in m['files'].items():
    data = (p / name).read_bytes()
    assert len(data) == info['bytes']
    assert hashlib.sha256(data).hexdigest() == info['sha256']
for name, expected in m['committed_source_sha256'].items():
    assert hashlib.sha256(Path(name.replace('\\', '/')).read_bytes()).hexdigest() == expected
with zipfile.ZipFile(p / m['source_archive']) as z:
    for name, expected in m['source_sha256'].items():
        assert hashlib.sha256(z.read(name.replace('\\', '/'))).hexdigest() == expected
print('Archive and source checksums match')
'@ | python -
```

解压到忽略的本地文件：

```powershell
@'
import gzip
from pathlib import Path
p = Path('results/cpu_validation')
(p / 'recovered_trace.csv').write_bytes(gzip.decompress((p / '2026-10-10_no_training/trace.csv.gz').read_bytes()))
'@ | python -
```

使用新目录复现，避免覆盖本归档：

```powershell
$env:PYTHONPATH = 'src'
python -m developmental_control.validate --output results/cpu_validation/reproduction
```

固定轨迹与控制指标应可复现；墙钟耗时、动作选择延迟和 Git 元数据随机器及提交状态变化。当前源码与归档原版仅有上述末尾空白差异；需要字节完全一致的原版时使用 ZIP 快照。
