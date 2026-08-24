# 24 GB GPU 新电脑接管与执行手册

> 目标：新电脑克隆仓库后，让新的 Codex 会话无需依赖旧聊天记录，也能知道项目边界、下一步任务和验收标准。

## 1. 开始前先读什么

按顺序阅读：

1. 根目录 `AGENTS.md`：当前任务、硬性边界和工作规范；
2. `README.md`：现有二维成果、命令、视频和指标；
3. `docs/DATA_SOURCES.md`：PBHC、Isaac Lab、Unitree 资源分类与许可；
4. `docs/DEVELOPMENTAL_ROBOT_VISION.md`：长期路线；
5. `paper/论文初稿.md`：当前论文基线，不把其中二维结果误写成 G1 结果。

## 2. 新机硬件与系统审计

先记录实际环境，不要根据“24 GB 显存”猜测硬件：

```powershell
nvidia-smi
git --version
python --version
Get-ComputerInfo | Select-Object WindowsVersion, OsBuildNumber, CsTotalPhysicalMemory
Get-PSDrive -PSProvider FileSystem
```

建议同时记录 GPU 型号、驱动版本、CUDA compatibility、CPU、RAM、可用磁盘和操作系统。Isaac Sim / Isaac Lab 对驱动、Python 和系统版本有明确兼容要求；安装时以 NVIDIA 当日官方文档为准。

对于长期 Isaac 工作流，优先考虑官方支持良好的原生 Ubuntu 环境。不要由 Codex 静默重装操作系统、显卡驱动或 CUDA；这类变更必须先获得用户确认。

## 3. 克隆项目并验证已有成果

```powershell
git clone https://github.com/ruirui688/developmental-humanoid-learning.git
Set-Location developmental-humanoid-learning
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m pytest -q
```

验收：现有 CPU 测试全部通过，`git status --short` 无意外改动，README 中 GIF/MP4 和已提交结果可访问。先完成这一检查，避免把新机环境问题误判为 Isaac Lab 问题。

## 4. 外部依赖与数据布局

外部项目不要复制进本仓库的 Git 历史。可在与仓库同级的本机目录管理：

```text
robot-research/
├── developmental-humanoid-learning/  本仓库
├── external/
│   ├── IsaacLab/
│   ├── PBHC/
│   ├── unitree_rl_gym/
│   └── unitree_mujoco/
├── data/raw/                          未转换的动作数据
├── data/processed/                    可重建的重定向数据
└── checkpoints/                       大型模型权重
```

在第一次实际下载前，按 `docs/DATA_SOURCES.md` 建立来源清单，记录精确 commit/tag、license 和 checksum。不要默认使用某个仓库的当前默认分支，因为它会变化。

## 5. 安装 Isaac Lab 的原则

1. 打开 NVIDIA Isaac Lab 官方仓库和安装文档；
2. 根据当前驱动、操作系统和 Isaac Sim 兼容矩阵选择版本；
3. 固定到一个精确 tag 或 commit；
4. 使用独立 Python/Conda 环境，不破坏本仓库二维环境；
5. 先运行官方最小示例和 GPU 环境检查；
6. 记录完整安装命令、版本和已知问题，再开始本项目适配。

官方入口：<https://github.com/isaac-sim/IsaacLab>。

## 6. G1 软件 MVP 的严格执行顺序

### 阶段 A：规范化 G1 映射

从 Unitree 官方资产和配置建立唯一映射表，至少包含：

- articulation joint name 与顺序；
- actuated / passive / locked joint；
- body/link name 与接触分组；
- 关节位置、速度、力矩限位；
- 默认姿态和控制增益；
- 策略 action index 到 G1 joint 的对应；
- 与 PBHC/SMPL 数据重定向之间的对应关系。

验收：程序自动检查名称、数量、顺序和限位，不靠人工目测；所有实验组使用同一映射。

### 阶段 B：Isaac Lab 模型烟雾测试

按以下顺序验证：

1. G1 articulation 能无报错加载；
2. 静止状态下重力方向、质量和默认姿态合理；
3. 每个关节单独施加小动作时方向正确；
4. 关节限位与 actuator 参数和官方配置一致；
5. 双脚、手、膝、躯干等接触体可产生正确标签；
6. 站立 smoke task 能运行；
7. headless 并行环境能稳定运行和复位。

任何一项失败都先修模型/配置，不进入 PPO 调参。

### 阶段 C：直接 PPO 基线

先只做站立或受控起身，不直接做完整行走。固定观测、动作、奖励、终止条件和训练预算，保存逐 seed 结果。这个基线必须可复现，之后的发育式方法共享同一环境。

### 阶段 D：运动成熟机制

依次实现：

1. Full action space from start；
2. Fixed maturation schedule；
3. Competence-gated adaptive maturation；
4. Adaptive maturation + Body Schema；
5. 完整方法和组件消融。

可逐步开放的是控制关节、动作范围、速度、力矩、探索噪声和外部支撑；机械硬限位与安全上限永远不能解除。

### 阶段 E：接触估计

Isaac Lab 的逐刚体接触只作为 teacher label。学生只能读取真机将来可用的历史：关节位置/速度、IMU、电机电流或力矩估计、上一动作和跟踪误差。分别报告接触估计准确率与策略收益，避免两者混为一谈。

## 7. 24 GB 显存使用建议

先小规模正确，再增加并行数：

| 用途 | 建议环境数 | 目的 |
|---|---:|---|
| 单步调试和可视化 | 1–16 | 检查坐标、动作、接触和奖励 |
| 训练流程 smoke test | 64–128 | 检查显存、复位和日志 |
| 接触密集的起身/站立 | 512–1024 | 24 GB 上的保守正式起点 |
| 简单站立任务 | 最多尝试 2048 | 仅在监测显存与吞吐后扩大 |

环境数不是论文贡献。正式实验优先 headless；多个 seed 顺序运行，先保留显存余量，再根据实际峰值调整。OOM 后不要只降低网络而改变不同实验组的模型容量公平性。

## 8. 开始长训练前的 Go / No-Go

只有全部满足才 Go：

- 官方来源、license、commit 和本地校验值已记录；
- G1 joint/body/action 映射有自动测试；
- 接触、关节方向、限位和控制增益已验证；
- 环境可在固定 seed 下复现 reset 和短 rollout；
- Direct PPO smoke run 能学习到非退化行为；
- 日志包含成功、严重跌倒、冲击、力矩饱和、环境交互和墙钟时间；
- 所有实验组的额外数据与预训练状态已经分类。

任一项不满足即 No-Go：继续诊断，不烧长时间 GPU。

## 9. 每次实验必须保存

- 项目 Git commit 与 dirty 状态；
- Isaac Lab / Isaac Sim / robot asset 精确版本；
- 驱动、GPU、Python 和关键依赖；
- 完整配置、seed、环境数、总 environment steps；
- 动作数据量、教师 checkpoint 和预训练预算；
- 逐 seed 原始指标、失败日志、曲线和代表性视频；
- 成功阈值、评估场景和模型选择规则。

## 10. 新 Codex 会话可直接使用的任务描述

> 阅读根目录 AGENTS.md、docs/NEW_MACHINE_BOOTSTRAP.md 和 docs/DATA_SOURCES.md。先审计本机 GPU/驱动和现有 CPU 测试，再按官方文档固定 Isaac Lab 版本；建立可自动验证的 Unitree G1 关节/刚体/action 映射，完成 articulation、接触和站立 smoke test。在这些验收通过前不要开始长训练，也不要把 PBHC 动作或 checkpoint 混入纯发育实验轨。
