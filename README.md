# Developmental Humanoid Learning

> Human-inspired developmental motor learning for safer and more sample-efficient humanoid locomotion.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0%2B-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Status](https://img.shields.io/badge/status-concept%20validation-14b8a6)](#项目阶段)
[![Tests](https://img.shields.io/badge/tests-4%20passed-22c55e)](#快速开始)

本项目研究一个区别于“海量仿真试错 → 单任务策略”的人形机器人运动学习方向：机器人先通过安全身体探索形成 **Body Schema**，再逐步获得平衡、重心转移、辅助行走和独立行走能力，并将已有知识迁移到更复杂的技能中。

当前仓库提供第一阶段可复现成果：一个二维理想火柴人环境，以及融合人体运动先验、下一状态预测与发育课程的 **DHP-PPO（Developmental Human-Prior PPO）**。

> [!IMPORTANT]
> 当前结论仅来自透明的二维理想动力学代理，不是刚体仿真或真机结论。项目公开不利结果、额外先验数据和实验限制，避免把概念验证包装成 Sim2Real 成果。

## 演示

### 发育式策略：无支撑行走

![DHP-PPO learned walking](results/validation/media/developmental_walk.gif)

### 相同 PPO 环境交互预算：同步对比

![Direct PPO versus DHP-PPO](results/validation/media/ppo_vs_developmental.gif)

左侧直接 PPO 在约 2.36 s 后跌倒并停留在失败状态；右侧 DHP-PPO 在关闭外部支撑后继续完成 12 s 测试回合。

- [完整无支撑行走视频（Supplementary Video S1）](results/validation/media/developmental_walk.mp4)
- [直接 PPO 与发育式策略同步对比（Supplementary Video S2）](results/validation/media/ppo_vs_developmental.mp4)
- [中文论文初稿](paper/论文初稿.md)

## 为什么做这个项目

现有运动学习系统能够借助 PPO、人体动作模仿和大规模并行仿真实现高动态动作，但将大量失败搬到真实机器人上会带来摔倒、冲击、磨损、能耗和人工复位成本。

人类学习行走并不是从随机动作直接跳到连续步态，而是经历低风险探索、多接触支撑、平衡、站立、重心转移和辅助行走。这个项目希望验证：

> 机器人能否少摔、少试、少依赖大规模仿真，同时通过身体知识和技能积累逐渐学会复杂运动？

## 项目优势

| 维度 | 直接任务强化学习 | 本项目的发育式路线 |
|---|---|---|
| 学习起点 | 随机策略或单任务初始化 | 人体运动先验与身体预测表征 |
| 技能组织 | 直接学习最终 Walking | 探索 → 平衡 → 重心转移 → 辅助行走 → 独立行走 |
| 风险管理 | 跌倒后惩罚并复位 | 从强支撑逐步解除支撑，并惩罚失稳前状态 |
| 知识使用 | 新任务经常重新训练 | 同一条件策略持续迁移先前能力 |
| 优化目标 | 容易只关注 Reward | 同时报告成功、跌倒、交互、距离和动作误差 |
| 可解释性 | 端到端策略较难拆解 | 人体先验、Body Schema 和课程均可单独消融 |

更完整的技术定位、优势边界与研究假设见 [项目优势与技术路线](docs/PROJECT_OVERVIEW.md)。

## 当前验证结果

未参与调参的训练种子为 10–14。每个方法、每个种子使用 76,800 次环境交互，最终统一关闭外部支撑并测试 30 回合。

| 指标 | 直接 PPO | DHP-PPO |
|---|---:|---:|
| 无支撑成功率 | 0.000 ± 0.000 | **1.000 ± 0.000** |
| 测试跌倒率 | 1.000 ± 0.000 | **0.000 ± 0.000** |
| 训练期严重跌倒 | 1402.8 ± 47.5 | **63.0 ± 7.0** |
| 平均前进距离 | 1.899 ± 0.318 m | **9.400 ± 0.266 m** |
| 关节跟踪 RMSE | **0.273 ± 0.027** | 0.316 ± 0.003 |
| 环境交互 / seed | 76,800 | 76,800 |
| 额外人体先验样本 / seed | 0 | 8,192 |

训练期严重跌倒减少 **95.51%**。与此同时，DHP-PPO 的关节 RMSE 略差；这说明短时动作相似性不等于长期闭环稳定，也说明不能只展示有利指标。

![Training falls](results/validation/training_falls.png)

逐种子数据见 [`metrics_by_seed.csv`](results/validation/metrics_by_seed.csv)，统计量见 [`statistics.json`](results/validation/statistics.json)。

## 方法概览

```text
Synthetic Human Motor Prior
              │
              ▼
       Conditioned Policy ◄──── Body Schema / Forward Prediction
              │
              ▼
Body Babbling → Balance → Weight Transfer → Supported Walk → Independent Walk
      100% support                                         0% support
```

DHP-PPO 包含三个核心组件：

1. **可审计的人体运动先验**：使用左右交替步态相位和类似前庭反馈的髋部平衡修正，不把先验隐藏在不可追踪的数据处理中；
2. **Body Schema 辅助目标**：策略表征同时预测下一时刻关节、躯干与速度状态；
3. **条件化发育课程**：同一策略从低风险身体探索逐步过渡到完全无支撑行走，阶段切换不重置参数。

## 快速开始

### 环境

- Python 3.10+
- NumPy
- PyTorch 2.0+
- Matplotlib
- pandas / SciPy
- FFmpeg（仅重新导出 MP4 时需要）

### 安装与测试

```powershell
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m pytest -q
```

### 复现实验

```powershell
$env:PYTHONPATH = "src"
python -m robot_rl.experiment `
  --seeds 10 11 12 13 14 `
  --updates 40 `
  --num-envs 24 `
  --rollout-steps 80 `
  --eval-episodes 30 `
  --output results/validation
```

### 导出论文视频

训练检查点默认不纳入 Git；重新训练后可执行：

```powershell
$env:PYTHONPATH = "src"
python -m robot_rl.video `
  --developmental results/validation/developmental_seed10.pt `
  --traditional results/validation/traditional_seed10.pt `
  --output results/validation/media

ffmpeg -i results/validation/media/ppo_vs_developmental.mp4 `
  -vf "fps=12,scale=960:-1:flags=lanczos" `
  results/validation/media/ppo_vs_developmental.gif
```

## 项目结构

```text
developmental-humanoid-learning/
├── src/robot_rl/
│   ├── env.py            # 二维火柴人动力学、课程与奖励
│   ├── ppo.py            # PPO、人体先验和 Body Schema
│   ├── evaluate.py       # 无支撑评估与轨迹记录
│   ├── experiment.py     # 多随机种子对照实验
│   └── video.py          # MP4 / GIF 导出
├── tests/                # 环境和先验单元测试
├── results/validation/   # 未见种子结果、图表与视频
├── docs/                 # 项目定位与研究路线
├── paper/论文初稿.md      # 中文论文初稿
└── pyproject.toml
```

## 项目阶段

- [x] 理想二维火柴人环境
- [x] 直接 PPO 基线
- [x] 发育课程、人体运动先验与 Body Schema
- [x] 5 个未见种子的正式验证
- [x] 论文图表、检查点和补充视频
- [ ] 课程 / Body Schema / 人体先验的因子消融
- [ ] 在可用 GPU 环境中选择兼容的 Isaac Lab 和 Unitree G1 资产版本
- [ ] 建立统一 G1 关节/刚体/action 映射并完成模型与接触 smoke test
- [ ] Isaac Lab G1 直接 PPO 站立基线
- [ ] 固定成熟与能力门控运动成熟的公平对比
- [ ] 使用原生传感器和特权接触标签蒸馏，不改机器人硬件
- [ ] MuJoCo 平面双足刚体接触环境
- [ ] 噪声、延迟、摩擦和执行器随机化
- [ ] Pre-Failure 预测与主动恢复
- [ ] 吊架保护下的真实机器人低风险实验

## 科学边界

本仓库当前不能证明：

- 已经解决真实人形机器人行走；
- 发育课程单独导致了全部性能提升；
- 在相同总信息预算下优于所有传统算法；
- 当前解析运动先验等同于真实人体肌肉协同；
- 已经实现低样本 Sim2Real。

我们将这些边界视为项目可信度的一部分，而不是需要隐藏的弱点。

## 文档

- [新环境接管与执行手册](docs/NEW_MACHINE_BOOTSTRAP.md)
- [外部资源选择与使用原则](docs/DATA_SOURCES.md)
- [Codex / 智能体项目级工作说明](AGENTS.md)
- [项目优势与技术路线](docs/PROJECT_OVERVIEW.md)
- [真实机器人发育式运动学习：研究愿景与系统设计](docs/DEVELOPMENTAL_ROBOT_VISION.md)
- [研究讨论记录：从二维概念验证到真实机器人发育](docs/RESEARCH_DIALOGUE.md)
- [中文论文初稿](paper/论文初稿.md)
- [实验运行元数据](results/validation/run_metadata.json)
- [统计分析](results/validation/statistics.json)

## License

仓库当前尚未选择开源许可证。在正式添加许可证之前，源代码默认保留全部权利。如需开放复用，建议后续根据项目计划选择 MIT、Apache-2.0 或其他许可证。
