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
