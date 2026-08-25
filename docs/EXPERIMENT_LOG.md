# 实验与工程进展日志

本文件按时间追加可验证进展。性能结论只有在配置冻结、正式未见种子评估完成后才写入论文结果；smoke test 只证明软件链路可运行。

## 2026-08-26：本机接管复核与 G1 双链路 smoke

- 状态：通过；尚未授权长时间正式训练（No-Go）。
- 硬件：NVIDIA GeForce RTX 4090 24 GB，Intel Core i9-14900K，约 62 GiB RAM。
- 系统：Ubuntu 22.04.5 LTS，NVIDIA driver 560.28.03。
- 仓库基线：`main`，执行时包含尚未提交的 PBHC/G1 接入工作。
- 外部环境：PBHC `ffac5cded61fe78b39b051f09ac2ed0f6a1ccea0`；Isaac Gym Preview 4；Python 3.8.20；PyTorch 2.4.1+cu121。
- CPU 验证：`python -m pytest -q`，12 passed。
- 映射验证：23 个策略 action、23 个 URDF 可动关节、24 个折叠刚体一致；接触脚体为左右 ankle roll link。
- 上游 smoke：`bash scripts/pbhc_smoke.sh`，1 env × 24 steps × 1 PPO iteration，通过。该运行加载 Horse-stance 示例动作，只验证 PBHC 软件链路，属于带动作先验的 smoke，不是实验基线。
- 纯发育 smoke：`bash scripts/pbhc_developmental_smoke.sh`，1 env × 24 steps × 1 Developmental PPO iteration，通过；最终 motion file 为 `null`，阶段 0 开放 11/23 个残差 action，探索标准差为 0.2，Body Schema 完成一次更新并保存 checkpoint。
- 单环境观测：纯发育 smoke 显示约 79 steps/s、0.303 s/iteration。该数字包含极小工作负载开销，不能作为正式吞吐基准。
- 已知警告：30 个 rigid shapes 与 24 个 rigid bodies 不一一对应；正式摩擦随机化统计前需修正上游诊断记录。
- 科研边界：当前只有工程可运行性证据，没有 G1 收敛、样本效率、安全优势、鲁棒性或 Sim2Real 证据。

### 长训练前必须完成

1. 冻结 Direct PPO、Fixed maturation、Adaptive maturation 的公平配置；
2. 实现固定未见 reset/seed bank 的评估器，并只用其指标驱动 Adaptive gate；
3. 记录逐 episode 成功、严重跌倒、冲击、复位、关节/力矩饱和及 time-to-threshold；
4. 完成环境数吞吐阶梯和每组单 seed 非退化短跑；
5. 为 G1 评估建立固定 seed、固定镜头、固定时长的视频 manifest；
6. 接触估计器和扰动评估完成前，不声称完整方法或鲁棒性结果。

### 本次发现并修复的 smoke 问题

- 首次加入累计 environment-step 日志时使用了整数 tensor，PBHC 的均值聚合器在日志阶段拒绝整数求均值；已改为与 action 相同的浮点 dtype。
- `pbhc_developmental_smoke.sh` 原先不透传额外 Hydra override，无法用同一入口验证 Direct/Fixed overlay；已补充 `"$@"` 透传。失败发生在第一个 PPO iteration 的日志阶段，未被计为通过结果。

## 2026-08-26：Direct 与 Fixed maturation 配置 smoke

- 状态：两组均通过 1 env × 24 steps × 1 PPO iteration；只验证配置和阶段切换，不是学习结果。
- Direct 命令：`bash scripts/pbhc_developmental_smoke.sh maturation=dhl_direct`。
- Direct 解析配置：`mode=locked`、`initial_stage=2`、Body Schema loss coefficient 为 0；日志显示完整 23/23 action、normalized stage 1.0、exploration scale 1.0。
- Fixed 命令：`bash scripts/pbhc_developmental_smoke.sh maturation=dhl_fixed_pilot 'maturation.fixed_transition_environment_steps=[8,16]'`。
- Fixed 解析配置：`mode=fixed`、`initial_stage=0`、Body Schema loss coefficient 为 0；24-step smoke 跨越两个预设阈值，阶段均值 0.625，证明按累计 environment steps 的切换接线生效。
- CPU 验证：新增固定时间表边界测试后 `python -m pytest -q` 为 14 passed。
- 公平性说明：Direct 与 Fixed 复用相同环境、奖励、actor/critic 结构和 `tanh` residual action transform；差异只在动作成熟阶段。正式 Fixed 阈值仍须按共同训练预算预注册，pilot 的 32,768/65,536 不作为论文设定。

## 2026-08-26：并行环境吞吐阶梯与 PBHC reset 修复

- 状态：吞吐阶梯完成；选择 8,192 env 作为下一阶段 pilot 起点，正式配置仍需用完整 PPO epoch/minibatch 复核。
- 首次 256-env 运行失败：上游 `LeggedRobotBase._reset_dofs` 将全部环境的 `default_dof_pos` 与仅终止环境的随机缩放矩阵相乘。单环境 smoke 无法暴露该 shape mismatch。
- 修复：`DevelopmentalG1Env._reset_dofs` 只索引本次 `env_ids` 对应的默认关节行；不修改 `external/PBHC`。修复后 1-env 与多环境 reset 都通过。

| 并行环境数 | 每 iteration steps | 观测吞吐 | iteration 时间 | 峰值计算显存 |
|---:|---:|---:|---:|---:|
| 256 | 6,144 | 15,555 steps/s | 0.3950 s | 未测 |
| 1,024 | 24,576 | 49,177 steps/s | 0.4997 s | 未测 |
| 4,096 | 98,304 | 133,227 steps/s | 0.7379 s | 未测 |
| 8,192 | 196,608 | 171,003 steps/s | 1.1497 s | 14,896 MiB |
| 16,384 | 393,216 | 199,507 steps/s | 1.9709 s | 19,808 MiB |

以上均为 Direct overlay、24 rollout steps、1 epoch、1 minibatch、1 iteration 的短测。16,384 相比 8,192 的吞吐提升约 17%，但峰值计算显存增加约 4.9 GiB；8,192 在 24 GiB GPU 上保留更合理余量，因此用于 pilot。该表不是方法性能结果，也不能外推到完整正式训练吞吐。

## 2026-08-26：held-out competence evaluator 与 Adaptive gate smoke

- 状态：最小闭环通过；尚未运行学习 pilot。
- evaluator 定义：固定 seed、确定性 actor；episode 在任务 horizon 内无跌倒完成才计 success，非 timeout 终止计 fall；upright、无严重非足冲击、低力矩饱和与 Body Schema accuracy 按评估步汇总。
- 预算隔离：`competence_windows.jsonl` 分别记录 `rl_environment_steps` 与 `cumulative_evaluation_steps`，评估交互不并入 PPO environment-step 预算。
- 状态隔离：评估前保存 CPU/CUDA RNG，评估后恢复；强制 reset 后才恢复训练，避免使用评估后的陈旧 observation。
- Direct evaluator smoke：训练 24 RL steps 后，固定评估使用 9 steps 完成 1 episode；随机初始策略跌倒，survival 0、fall rate 1。该结果只验证指标输出。
- Adaptive A0 smoke：`maturation=dhl_adaptive_pilot`，训练 24 RL steps 后固定评估使用 15 steps 完成 1 episode；survival 0、fall rate 1，gate 未晋级。checkpoint 保存 `stage_index=0`、`windows_in_stage=1`、`last_score=0.67696`。
- A0 公平性：关闭 Body Schema loss 后，gate 同时将 schema 权重设为 0 并禁用其硬阈值；否则随机且未训练的 schema head 会成为隐藏阻塞。Full 配置仍使用 schema accuracy。
- CPU 验证：episode 计数、信号范围、窗口完整性和无 schema 门控消融共 18 tests passed。
- 科研边界：1 episode smoke 不能估计成功率，也不能用于选择 gate 阈值。pilot 前仍需冻结 episode bank、评估频率、阈值和成功定义。
