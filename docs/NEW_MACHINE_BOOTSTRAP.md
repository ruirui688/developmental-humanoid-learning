# 新环境接管与执行手册

> 目标：新电脑克隆仓库后，让新的 Codex 会话无需依赖旧聊天记录，也能知道项目边界、下一步任务和验收标准。
> 当前研究路线更新：2026-10-10，优先验证在线身体建模、局部预测控制与能力门控；PPO 保留为比较基线。

## 1. 最小必读内容

新会话先阅读：

1. 根目录 `AGENTS.md`：当前任务、硬性边界和工作规范；
2. `README.md`：现有二维成果、命令、视频和指标；

开始后续开发时读取 [项目推进路线](DEVELOPMENT_ROADMAP.md)，按阶段验收选择任务。历史二维 DHP-PPO 成果与新候选算法分别管理。

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

### 3.1 没有可用 GPU 时继续什么

当前用户要求仅 CPU、暂不训练时，先运行 [CPU 无训练验证](CPU_VALIDATION.md) 的固定模型仿真和门控测试，不运行 PPO、监督拟合或在线辨识更新。

先做推进路线中的协议与代码可信度、独立低维身体模型和局部控制原型。优先验证自监督在线系统辨识及冻结/更新模型的闭环对比，使用可在 CPU 上运行的任务。当前火柴人的速度代理只能用于旧结果复现或接口调试，不能替代新方法的物理控制实验。

G1 资产与仿真部署等待确认具备兼容 GPU 的主机，不凭项目目录位置推断硬件。新引入的原型或模拟器依赖使用独立包/可选依赖，保持二维 CPU 测试可运行。

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

> 既有 GPU 环境实现说明（2026-08-26）：项目已按 PBHC 上游实际支持锁定 PBHC
> `ffac5cde`、Isaac Gym Preview 4 与其 Unitree G1 资产，并完成双 GPU smoke。
> 这是当前可复现的 G1 工程后端，不应称为 Isaac Lab 结果。以下 Isaac Lab 内容仍是
> 后续迁移原则；迁移前不得把两套后端的结果放入同一公平对照表。实际记录见
> `docs/PBHC_INTEGRATION.md` 和 `docs/EXPERIMENT_LOG.md`。

2026-10-10 的当前会话仅使用 CPU，不具备上述 GPU 环境。先读取已记录的资产映射、组件和测试，保留既有成果；CPU 无训练原型与历史 G1 PPO 实验分别报告。以下 G1 步骤用于新机器复核或后端迁移，不表示已有工作需要全部重做。

1. 打开 NVIDIA Isaac Lab 官方仓库和安装文档；
2. 根据当前驱动、操作系统和 Isaac Sim 兼容矩阵选择版本；
3. 固定到一个精确 tag 或 commit；
4. 使用独立 Python/Conda 环境，不破坏本仓库二维环境；
5. 先运行官方最小示例和 GPU 环境检查；
6. 记录完整安装命令、版本和已知问题，再开始本项目适配。

官方入口：<https://github.com/isaac-sim/IsaacLab>。

## 6. G1 软件 MVP 的前置验证与开发顺序

阶段 A、B 是所有 G1 学习与控制候选的共同前置条件。阶段 C 先冻结任务与初始控制条件；其中的 PPO 对照可与阶段 D、E 的在线学习和成熟机制并行建立，主方法不必等待 PPO 训练完成。阶段 F 按接触任务的实际需要引入。

### 阶段 A：规范化 G1 映射

现有 PBHC/Isaac Gym 映射已有静态检查与历史动态审计，应先复用；更换资产或后端时从实际采用的 Unitree 资产和配置复核唯一映射表，至少包含：

- articulation joint name 与顺序；
- actuated / passive / locked joint；
- body/link name 与接触分组；
- 关节位置、速度、力矩限位；
- 默认姿态和控制增益；
- 策略 action index 到 G1 joint 的对应；
- 与未来可能采用的动作表示或重定向格式之间的接口。

验收：程序自动检查名称、数量、顺序和限位，不靠人工目测；所有实验组使用同一映射。

### 阶段 B：对应仿真后端的模型烟雾测试

当前后端为 PBHC + Isaac Gym Preview 4。恢复动态验证或迁移到 Isaac Lab 等新后端时，按以下顺序复核：

1. G1 articulation 能无报错加载；
2. 静止状态下重力方向、质量和默认姿态合理；
3. 每个关节单独施加小动作时方向正确；
4. 关节限位与 actuator 参数和官方配置一致；
5. 双脚、手、膝、躯干等接触体可产生正确标签；
6. 站立 smoke task 能运行；
7. headless 并行环境能稳定运行和复位。

任何一项失败都先修模型/配置，不进入学习算法调参或大规模采样。

### 阶段 C：共同任务与控制基线

先做受支撑站立、小幅重心控制或受保护的局部姿态调整。固定默认姿态、支撑、观测、动作、成功标准、终止条件和预算，保存逐 seed 结果。先测底层控制和经典反馈/系统辨识控制的学习前水平；如果它们已解决任务，后续实验应评估未知载荷、延迟或扰动下的适应收益，或明确增加任务难度。

在同一环境中建立 Direct PPO 的短基线，并选择适用的强基线；这些对照可与阶段 D、E 并行开发。PPO 训练不构成在线身体模型原型的前置条件；大规模对比前须分别确认所有参与方法能完成短运行、保存日志和正确复位。

### 阶段 D：在线身体模型与局部控制

学习模型仅使用部署可用的观测历史与动作，优先从局部线性模型或已知模型的残差辨识开始。比较：

1. 经典反馈或系统辨识/预测控制；
2. 相同初始化的冻结身体模型；
3. 在线更新身体模型与短时域预测控制。

记录一步/多步预测、闭环任务误差、更新成本、控制延迟与超时回退。冻结/更新组使用相同初始数据；所有校准与探索动作计入各自预算。测试可在冻结评估和明确允许在线适应两种协议下进行，不能在冻结评估中更新模型。

### 阶段 E：运动成熟与探索机制

在身体模型和局部控制能够工作的条件下，对比完整权限、固定成熟与能力门控；再对比受约束随机探索与主动探索。能力门控同时检查模型误差、不确定性、闭环成功、风险与小扰动恢复，并记录每次权限变化的依据。不能只用预测误差下降决定减少外部支撑。

可逐步开放的是控制关节、动作范围、速度、力矩、探索噪声和外部支撑；机械硬限位与安全上限永远不能解除。

### 阶段 F：按任务需要增加接触估计

经审计的仿真接触标签只作为 teacher label。现有 Isaac Gym 净接触力不直接说明接触对方，需先验证地面/自碰撞的标签语义；迁移后端也须重新检查。学生只能读取真机将来可用的历史：关节位置/速度、IMU、电机电流或力矩估计、上一动作和跟踪误差。分别报告接触估计准确率与策略收益，避免两者混为一谈。

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
- 经典控制和在线建模/控制候选能完成短运行，模型失效或规划超时有可验证的回退行为；
- 开始 PPO 长训练前，其 smoke run 能学习到非退化行为；
- 日志包含成功、严重跌倒、冲击、力矩饱和、环境交互和墙钟时间；
- 学习前表现、控制权限、支撑量、数据切分与评估期间是否更新模型已固定；
- 所有实验组的额外数据与预训练状态已经分类。

任一项不满足即 No-Go：继续诊断，不烧长时间 GPU。

## 9. 每次实验必须保存

- 项目 Git commit 与 dirty 状态；
- 实际仿真后端、上游项目和 robot asset 精确版本；
- 驱动、GPU、Python 和关键依赖；
- 完整配置、seed、环境数、总 environment steps；
- 初始化数据量、在线校准/探索量、适应交互量、控制器配置和模型更新次数；
- 动作数据量、教师 checkpoint 和预训练预算；
- 逐 seed 原始指标、失败日志、曲线和代表性视频；
- 成功阈值、评估场景和模型选择规则。

## 10. 新 Codex 会话可直接使用的任务描述

> 阅读根目录 AGENTS.md、README.md、docs/NEW_MACHINE_BOOTSTRAP.md 和 docs/DEVELOPMENT_ROADMAP.md。识别当前环境并运行现有 CPU 测试，遵守当前仅 CPU、暂不训练的执行范围，先验证固定模型控制和能力门控。复用 PBHC/Isaac Gym G1 来源、canonical 映射和已有审计；兼容 GPU 可用且执行范围允许时复核变更部分，完成对应 articulation、接触和 smoke test，Isaac Lab 仅为可选迁移。验收通过前不要开始 G1 长训练或大规模采样。真实机器人操作需用户明确授权和现场安全条件。若实际采用外部动作、教师或 checkpoint，再读取 docs/DATA_SOURCES.md 并明确它们属于哪一实验组。
