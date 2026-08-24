# 外部资源选择与使用原则

> 本文件不指定项目必须使用哪些外部数据或仓库。它只规定：一旦引入外部代码、机器人资产、动作数据或预训练策略，应如何保证许可合规、实验公平和结果可复现。

## 1. 候选来源示例

以下项目与当前 G1 / Isaac Lab 路线相关，可在确有需要时评估，不是强制依赖，也不是固定的数据清单：

| 来源 | 官方地址 | 本项目用途 | 当前已知许可说明 |
|---|---|---|---|
| NVIDIA Isaac Lab | <https://github.com/isaac-sim/IsaacLab> | G1 刚体仿真、接触标签、并行训练 | GitHub 标识 BSD-3-Clause；实施时复核所固定版本 |
| Unitree RL Gym | <https://github.com/unitreerobotics/unitree_rl_gym> | G1 配置、训练/部署参考、预训练示例 | BSD-3-Clause；单独检查资产和依赖许可 |
| Unitree MuJoCo | <https://github.com/unitreerobotics/unitree_mujoco> | G1 模型、跨仿真验证 | BSD-3-Clause；单独检查模型资产说明 |
| Unitree SDK2 | <https://github.com/unitreerobotics/unitree_sdk2> | 后期真机通信与状态接口 | BSD-3-Clause；真机前固定兼容版本 |
| PBHC | <https://github.com/TeleHuman/PBHC> | G1 描述、SMPL 动作处理/重定向、模仿基线、部署参考 | README 标注 CC BY-NC 4.0，要求署名且限制非商业用途 |

上表只是候选入口，不替代各仓库的 LICENSE、README、模型或数据集条款。采用时必须按实际选定版本重新核对；未采用的来源不进入实验配置、依赖或论文数据预算。

## 2. 三类来源不能混为一谈

### A. 机器人资产与公共配置

包括 URDF/USD/MJCF、mesh、关节名称、质量、限位、控制增益和碰撞体。它们定义共同实验环境，可在许可允许时由所有算法共享。

使用要求：所有实验组共享同一版本和 canonical G1 mapping；记录来源 commit 和任何本地修订。

### B. 人体或机器人参考动作

包括 MoCap、SMPL/SMPL-X、重定向后的 G1 轨迹、关键帧和参考状态。它们向方法提供了任务相关的额外先验信息。

使用要求：披露原始数据集许可、动作数量、帧数/时长、筛选与重定向方法、使用哪些实验组。不能只报告 RL environment steps 而隐藏动作数据预算。

### C. 预训练 checkpoint / teacher policy

包括 PBHC、Unitree 示例策略或其他已经会模仿、站立、行走的权重。它们包含训练后的任务知识。

使用要求：只能作为 teacher、初始化方法或强基线明确标注。使用后不能把该实验称为“No Pretrained Task Policy”或纯从零发育。

## 3. 以 PBHC 为例的可选用法

如果后续选择 PBHC，它可帮助减少以下重复工作：

- 了解 G1 humanoid description 和 joint mapping；
- 参考人体动作采集、SMPL 处理和 G1 retargeting 流程；
- 构建 motion-imitation / teacher 强基线；
- 参考 Isaac Gym、MuJoCo 和真机部署接口的组织方式。

这不意味着项目必须采用 PBHC。无论选择 PBHC 还是其他来源，都应区分两类实验条件：

| 实验轨 | 可用来源 | 可以回答的问题 |
|---|---|---|
| Pure developmental | 官方 G1 资产、环境参数；无预训练任务策略 | 运动成熟和自主探索本身是否有效 |
| Human-prior | 选定的动作数据或 teacher，完整披露预算 | 人体先验与发育机制组合是否进一步提高性能 |

任何外部 checkpoint 若作为教师，应与 direct PPO 和本项目方法并列为强基线或单独的 teacher-assisted 条件，不能只把它的能力计入本项目结果。

## 4. 公平对比规则

所有方法必须共享：

- 相同的 G1 articulation、joint/body/action mapping；
- 相同观测中真机可用信号；
- 相同控制频率、actuator、仿真步长和 domain randomization；
- 相同任务、成功标准、终止条件和评估场景；
- 相同 RL environment step 预算和模型选择规则。

另外分别报告：

- human motion samples / duration；
- teacher queries；
- offline pretraining steps；
- 总 GPU 时间和 GPU 型号；
- 环境交互、严重跌倒、复位、冲击和力矩饱和；
- 均值、离散度、全部 seed 和失败 seed。

这样才能区分“更好的学习结构”“更多的外部信息”和“更多的计算”。

## 5. 来源清单最小字段

对实际使用且会影响复现的外部来源，至少记录：

```yaml
name: <selected-resource>
type: robot_asset | motion_data | checkpoint | source_code
official_url: <upstream-url>
revision: <exact-tag-or-commit>
retrieved_at: <YYYY-MM-DD>
license: <verified-license>
upstream_dataset_license: <if-applicable>
sha256: <archive-or-file-checksum>
local_path: <outside-git-or-ignored-path>
transformations:
  - <retarget/filter/convert step>
used_by_groups:
  - <experiment group>
notes: <attribution and restrictions>
```

建议将不含大型文件的来源清单、转换配置和脚本纳入 Git；原始数据、外部源码副本和 checkpoint 留在 Git 外或使用专门的 artifact storage。

## 6. 下载与执行安全

1. 只从官方组织 URL 开始，检查 owner、commit、release 和 license；
2. 先阅读安装脚本，不直接运行未知 shell/PowerShell 下载器；
3. 使用隔离环境；不要让外部安装修改本项目二维环境；
4. 对归档、动作数据和 checkpoint 记录 SHA-256；
5. 不提交凭据、机器人网络地址、私钥或带身份信息的原始人体数据；
6. 外部仓库的代码变更不得冒充本项目原创贡献。

## 7. 第一阶段具体取舍

第一阶段只需要：

- 官方 Isaac Lab；
- 可追踪的 Unitree G1 模型与配置；
- Direct PPO 站立基线；
- 固定与能力门控的运动成熟机制；
- Isaac Lab 特权接触标签和可部署学生估计器。

动作数据、retargeting 工具和预训练 checkpoint 只有在能回答明确研究问题时才引入。它们不是纯软件 MVP 的默认依赖；全身压力传感器和真机硬件改造同样不是第一阶段依赖。
