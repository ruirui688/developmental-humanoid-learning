# CPU E1 局部身体学习归档

2026-10-11；MuJoCo 3.15.0，CPU，无 PPO、任务教师或预训练策略。结论与完整边界见 [结果报告](../../../docs/CPU_LOCAL_BODY_RESULTS.md)。

## 结果与目录

- `selection.json`：按开发探针预定顺序选取仰卧左肩；输入与选择规则 hash 保留。
- `v1_development/`：四参数 RLS 与单剂量校准，预测退化，完整失败版本保留。没有运行 v1 学习留出。
- `v2_development/`、`v2_holdout/`：同一 clean `94ad34e`，五参数固定折点模型、多剂量校准。分别包含原始配置、逐 seed 指标、全部计划/实际 episode、压缩轨迹、源码 ZIP 与原采集清单。
- `v1_development_audit.json`、`v2_development_audit.json`、`v2_audit.json`：独立标准库重算，区分记录一致性与科研门。报告的原始采集路径保留；目录迁移后用内容 hash 核对。
- `v2_secondary_diagnostics.json`：闭环自身轨迹预测、实际努力、动能、接触、限位等不利描述指标；与预定门分开。
- `v2_learning.png`、`v2_probes.png`：静态图，含全部留出 seed、四控制组、负值和付费前缀；PNG 内记录输入/绘图脚本 hash。
- `manifest.json`：覆盖此归档所有成员的外层 SHA256 清单；各原采集清单原字节保留。

v2 留出独立预测误差降低 85.6%–86.7%、同 MPC 跟踪均值降低 28.9%，通过局部初期门。学习后 MPC 自身轨迹上的预测更差、努力及动能更高；尚无多关节/扰动泛化、低风险、翻身、站立或行走结论。固定 PD 未调优，折点与剂量尚未消融。

v1 开发 + v2 开发/留出合计 54 episodes、16,200 控制调用、162,000 子步、2,700 次 RLS 更新。600 次前置探针与此前地面诊断成本另列，正式地面物理研发总账为 174,950 / 1,749,500。每 seed 的 6 s 校准不代表研发或真实机器人学习总成本。

## 只读核查与绘图

在仓库根目录运行，`python` 可使用普通 Python 3.10+；审计与派生诊断无需 MuJoCo、GPU 或新的学习交互。输出用新的 ignored 目录，已有结果不会覆盖。

```powershell
python scripts/audit_local_learning_v2.py `
  results/cpu_validation/2026-10-11_local_learning/v2_development `
  results/cpu_validation/2026-10-11_local_learning/v2_holdout `
  --output external/reproduced_local_learning_v2_audit.json

python scripts/summarize_local_learning_v2_diagnostics.py `
  results/cpu_validation/2026-10-11_local_learning/v2_development `
  results/cpu_validation/2026-10-11_local_learning/v2_holdout `
  --audit results/cpu_validation/2026-10-11_local_learning/v2_audit.json `
  --output external/reproduced_local_learning_v2_diagnostics.json

python scripts/plot_local_learning.py `
  --probes-development results/cpu_validation/2026-10-11_joint_probes/development_profile.json `
  --probes-holdout results/cpu_validation/2026-10-11_joint_probes/holdout_profile.json `
  --learning-development results/cpu_validation/2026-10-11_local_learning/v2_development `
  --learning-holdout results/cpu_validation/2026-10-11_local_learning/v2_holdout `
  --output-prefix external/reproduced_local_learning_v2
```

绘图另需 NumPy、Matplotlib。重复审计的时间、路径与审计脚本 hash 可以变化；原始数据、重算数值和门结论应一致。采集源码仍以 ZIP 和 `94ad34e` Git blob 为准。

## 原正式采集命令

原运行器是 `src/developmental_physics/local_learning.py`；物理依赖装在独立环境，版本完整记录于两个 `metadata.json`。复现采集会产生新的 CPU 物理交互与模型更新，其预算不属于已冻结原始结果；新版本不能再把 seed 10/11/12 当作未见最终留出。

```powershell
$env:PYTHONPATH = 'src'
external/cpu_physics_env/Scripts/python.exe -m developmental_physics.local_learning `
  --output external/reproduced_local_learning_v2_development `
  --pose supine --joint 0 --seeds 0 1 2 --split development `
  --variant hinge --protocol docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md

external/cpu_physics_env/Scripts/python.exe -m developmental_physics.local_learning `
  --output external/reproduced_local_learning_v2_holdout `
  --pose supine --joint 0 --seeds 10 11 12 --split holdout `
  --variant hinge --protocol docs/LOCAL_BODY_LEARNING_V2_PROTOCOL.md
```
