# 新环境接管与执行手册

> 目标：新电脑克隆仓库后，让新的 Codex 会话无需依赖旧聊天记录，也能知道项目边界、下一步任务和验收标准。

## 1. 最小必读内容

新会话先阅读：

1. 根目录 `AGENTS.md`：当前任务、硬性边界和工作规范；
2. `README.md`：现有二维成果、命令、视频和指标；

其余资料按任务加载：需要选择外部模型或数据时读 `docs/DATA_SOURCES.md`；设计长期路线时读 `docs/DEVELOPMENTAL_ROBOT_VISION.md`；修改论文时再读 `paper/论文初稿.md`。这样避免给每个会话强塞无关背景。

## 2. 新机硬件与系统审计

先识别实际环境，不对 GPU 型号、显存、操作系统或安装方式作预设。下面是 Windows PowerShell 示例：

```powershell
nvidia-smi
git --version
python --version
Get-ComputerInfo | Select-Object WindowsVersion, OsBuildNumber, CsTotalPhysicalMemory
Get-PSDrive -PSProvider FileSystem
```

Linux 环境使用对应的系统命令即可，不要求照抄 PowerShell。只有当环境信息会影响复现或安装决策时，才记录 GPU、驱动、CPU、RAM、磁盘和操作系统等字段。

Isaac Sim / Isaac Lab 对驱动、Python 和系统版本有明确兼容要求；安装时以所选版本的官方文档为准。

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

外部项目不要复制进本仓库的 Git 历史。下面只是可选布局，实际目录名由本机环境决定：

```text
robot-research/
├── developmental-humanoid-learning/  本仓库
├── external/
│   ├── simulator/
│   ├── robot_assets/
│   └── optional_baselines/
├── data/raw/                          仅在实际使用外部数据时创建
├── data/processed/                    可重建的派生数据
└── checkpoints/                       大型模型权重
```

实际引入外部代码、资产、数据或权重时，按 `docs/DATA_SOURCES.md` 记录足以复现和审计的信息。未使用的候选来源不必下载，也不必写入实验依赖。

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
- 与未来可能采用的动作表示或重定向格式之间的接口。

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

## 7. 计算资源自适应

不在文档中预设固定并行环境数。不同 GPU、仿真版本、机器人资产、传感器和任务复杂度的显存占用差异很大，应通过短基准测试确定：

1. 用最少环境完成可视化和单步正确性检查；
2. 用小规模 headless smoke test 测量峰值显存、吞吐和复位稳定性；
3. 逐级增加并行度，记录每档的 steps/s、显存和失败情况；
4. 选择保留安全余量且吞吐收益仍合理的配置；
5. 把最终资源配置和选择依据写入实验元数据。

环境数不是论文贡献。是否 headless、seed 串行还是并行、是否使用混合精度，都由实测资源决定。不得只为某个实验组缩小网络或改变仿真精度，从而破坏方法间公平性。

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

> 阅读根目录 AGENTS.md、README.md 和 docs/NEW_MACHINE_BOOTSTRAP.md。识别当前环境并运行现有 CPU 测试，再为本机选择兼容的 Isaac Lab 版本；建立可自动验证的 Unitree G1 关节/刚体/action 映射，完成 articulation、接触和站立 smoke test。在这些验收通过前不要开始长训练。若实际采用外部动作、教师或 checkpoint，再读取 docs/DATA_SOURCES.md 并明确它们属于哪一实验组。
