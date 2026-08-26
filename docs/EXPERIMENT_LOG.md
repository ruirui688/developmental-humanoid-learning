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

### Pilot 前公平性修正

- 检查发现 Fixed maturation 原先读取环境内部总仿真步数，held-out evaluator 也会推进该计数，从而让评估预算错误地加速 Fixed 阶段切换。
- 现改为独立的 `maturation_schedule_environment_steps`：仅训练 rollout 递增，evaluation 期间暂停；计数随 maturation checkpoint 状态保存和恢复。
- 因此 Fixed 阈值、Adaptive 评估频率与论文横轴都以 PPO RL environment steps 为准，held-out evaluation steps 单独报告。

## 2026-08-26：三组单 seed 短 pilot 与默认姿态诊断

- 共同设置：1,024 env、30 iterations、737,280 RL steps、seed 1；每 5 iterations 用 1,024 个固定评估 episodes。Fixed 临时阈值为 245,760 和 491,520 RL steps。
- Direct：6/6 窗口 survival 0、fall rate 1；episode bank 通常在约 2–8 仿真步内全部终止。
- Fixed：6/6 窗口 survival 0、fall rate 1；保护阶段约 41–55 步，强制开放完整动作后降到约 2–4 步。
- Adaptive A0：6/6 窗口 survival 0、fall rate 1；保持 stage 0，没有不成熟晋级；保护阶段约 34–57 步。最终 checkpoint 为 `stage_index=0`、`windows_in_stage=6`、`schedule_environment_steps=737280`。
- 近零 residual 诊断仍为 survival 0、fall rate 1，episode bank 平均约 43 步终止。这说明短 pilot 的共同失败不能只归因于随机策略 action。
- 随后发现项目继承的 PBHC reset 会把每个关节初始化为默认角度的 0.5–1.5 倍。此前三组因此只标记为随机 reset 诊断，不作方法优劣结论。
- 修正：站立 MVP 将 `reset_dof_scale_range` 显式设为 `[1.0, 1.0]`，先验证 canonical pose 与默认 PD。随机初态范围将在基线成立后作为独立难度/鲁棒性条件预注册。
- canonical pose + 近零 residual 仍在约 50 steps 后全部跌倒，证明默认 PD 不是可独立维持的站立控制器。
- 由此发现阶段 0 的设计死锁：只开放手臂/腰，却要求 survival/upright 晋级；策略没有腿部控制权来学会满足门槛。
- 修正：站立 MVP 三阶段均开放髋、膝、踝、腰和手臂；保护阶段只限制 residual range=0.15、exploration scale=0.25，随后增至 0.35/0.50 和 1.0/1.0。逐关节开放推迟到具备外部支撑或稳定低层控制后的独立消融。
- 修正后的 Adaptive A0 再跑 737,280 RL steps：仍为 survival 0，但固定 episode bank 的完成长度提高到约 76–78 steps，gate 保持 stage 0。这说明解除控制死锁改善了短时存活，尚未达到 20 秒成功标准。
- 下一项 No-Go：当前 gate 初始阶段直接要求完整 1,000-step/20-second episode，且 pooled episode 计数可能让快速失败环境重复贡献。正式 pilot 前将改为每个 reset 每个 bank 只计一次，并预注册 stage 0/1/2 的 50/200/1000-step gate horizon；最终方法比较仍统一使用 1,000-step horizon。

## 2026-08-26：episode-bank 去重、阶段 horizon 与第二次 Adaptive pilot

- 修复 pooled episode 偏差：每个 bank 先统一 reset，每个并行环境只贡献一个 episode；环境自然终止后退出指标 active set，不能在自动 reset 后重复投票。指标只聚合 active 轨迹，但 `evaluation_steps` 仍记录 GPU 实际推进的全部环境交互。
- 内部门控 horizon 预注册为 stage 0/1/2 的 50/200/1000 control steps，即约 1/4/20 秒。该 curriculum 只用于 Adaptive 内部晋级，不替代所有方法共同的 1,000-step 最终评估。
- 1,024-env GPU 审计窗口得到恰好 1,024 episodes、51,200 evaluation steps 和 50-step horizon；不存在旧实现中快速失败环境重复计数。随机短训策略 survival 0.1299、fall rate 0.8701。
- 第二次 Adaptive A0 pilot：seed 1、1,024 env、30 iterations、737,280 RL environment steps；每 5 iterations 评估 1,024 个独立 50-step episodes。六个 survival 依次为 0.4521、0.4443、0.4453、0.4414、0.1973、0.4551，未形成上升趋势，stage 保持 0。
- 同期 upright 约 0.72–0.78、low-risk 约 1.0、low-saturation 约 0.82–0.87。训练日志中的 torque-limit reward 从初期约 -0.7 恶化到 iteration 25 的约 -11.7，说明当前主要阻塞已从门控计数错误转向控制/奖励/PPO 优化：策略没有在这个短预算内学到低扭矩稳定姿态。
- 科研边界：阶段 horizon 使“短时能力”可测，但没有产生 G1 站立性能结论；不能通过放宽门槛把约 45% 的 1 秒存活包装成成熟。下一步必须审计饱和关节、action/PD 尺度、终止来源、回报尺度及完整 PPO 更新预算。
- 验证：`python -m pytest -q` 为 20 passed；`git diff --check` 通过。

## 2026-08-26：完整 PPO 更新暴露零系数辅助优化 bug

- 前述 30-iteration pilot 继承 smoke 入口的 1 epoch/1 minibatch；它只有约 14.4 秒/环境的经验和 30 次策略更新，不能代表充分的反复练习。
- 将优化恢复为 PBHC 默认的 5 epochs/4 minibatches，并训练 100 iterations（2,457,600 RL steps）后，未修复版本的 50-step survival 从 0.0898 降至 0.0674。
- 根因之一：Adaptive A0 虽将 Body Schema loss coefficient 设为 0，代码仍在每个 minibatch 执行第二次 Adam step；零梯度也会推进 Adam 动量并改动共享 actor，完整 PPO 设置将错误放大。
- 修复为 coefficient 等于 0 时完全跳过 Body Schema 前向、反向和 optimizer step。相同 seed、预算和 PPO 设置复跑后，前四个窗口 survival 为 0.1357、0.1553、0.1572、0.1582，优于未修复版本，但最终仍回落到 0.0850，尚未形成有效学习。
- 因此“计算不足”是原 pilot 的重要限制，但不能解释全部失败。下一步分别检验实际只有 0.0375 rad 的 stage-0 最大 PD target residual，以及未归一化 torque-limit penalty 主导回报的问题；修正正确性后才扩大到数千万/上亿 environment steps。

### Contact termination 审计

- 将 stage-0 action range 从 0.15 单独扩大到 0.50 后，50-step survival 从 0.0586 降至 0，而 upright 从 0.8714 升至 0.9984、low-saturation 从 0.8634 升至 0.9431；策略学到了被奖励的竖直/低扭矩状态，却几乎总被 contact termination 判死。
- 新增终止接触体高度诊断。1,024-env 随机策略 smoke 中，所有观测到的 termination-body contact 都发生在刚体中心高度大于 0.25 m 时：elevated contact fraction 为 0.0012，ground contact fraction 为 0，但 75% 的终止被归为 contact。
- PBHC G1 资产启用了 self-collision，而 Isaac Gym 的 net contact-force tensor 不提供接触对方；因此此前 hip/pelvis/shoulder 净接触力不能无歧义地当作地面跌倒，属于错误终止标签。
- 修正：关闭 `terminate_by_contact`，保留投影重力和 base height 两个无歧义跌倒终止条件；非足接触与严重冲击继续作为独立风险信号记录。该修改后必须重跑同配置，不能沿用此前任何 survival 数字。

### 回报尺度与控制边界消融

- 关闭错误 contact termination 后，原 0.15 action range 的 100-iteration 运行得到 50-step survival 0.4395→0.4463，low-saturation 0.8400→0.8788；扩大到 0.50 但保持 torque-limit 权重 -1.0 时 survival 0.4541→0.4004。两者都没有学会站稳。
- PBHC `limits_torque` 返回所有关节超过 85% limit 的未归一化 Nm 总和。权重 -1.0 时该项 episode 日志约 -9 至 -15，远大于约 +3 的全部站立正奖励，策略因而优先减少用力而非避免跌倒。
- 因果诊断只把 `limits_torque` 权重改为 -0.05，并使用 0.50 action range；seed 1、1,024 env、200 iterations、4,915,200 RL steps。20 个 50-step 窗口的 survival 从 0.4619 单调趋势上升至 0.5605，upright 0.7280→0.7631，low-saturation 0.8525→0.9231。
- 这是目前首个非退化 G1 学习趋势，但仍低于晋级所需 survival 0.80 和 upright 0.85，不能作为性能结论。基于消融将阶段 action range 固定为 0.50/0.75/1.00（乘 PBHC scale 后为 0.125/0.1875/0.25 rad），并将 torque-limit 权重固定为 -0.05；硬力矩限幅、平方扭矩惩罚、风险日志和 low-saturation 晋级门槛均保留。
- 下一步扩大到 8,192 env × 500 iterations，即 98,304,000 RL environment steps；该预算用于验证能否依能力门控逐步跨越 50/200/1000-step horizon，不与此前 smoke/pilot 混作正式组间结果。

## 2026-08-26：68.8M-step Adaptive continuation checkpoint

- 8,192 env 大规模诊断运行达到 68,812,800 RL environment steps（350 iterations；每 iteration 196,608 rollout steps），评估每 25 iterations 使用 8,192 个去重 episode、50-step stage-0 horizon。
- 50-step survival 序列由 0.4719（4.9M steps）提升到 0.8325（68.8M steps）；upright 由 0.7233 提升到 0.8987；low-saturation 稳定约 0.92–0.925；low-risk 为 1.0。曲线持续改善，说明修正回报尺度后确实需要大规模重复练习。
- 即使 survival 已超过 0.80，gate 仍未晋级：最后 fall rate 为 0.1675，高于预注册最大晋级跌倒率 0.08（且 survival 仍未达到其等价的 0.92）。stage 0 的拒绝是安全门控按设计工作，不是计数或评估 budget 错误。
- 运行产生可续训 checkpoint `model_300.pt`（对应约 58.98M RL steps；最后评估窗口 checkpoint 记录延迟到 iteration 350），以及完整 `competence_windows.jsonl`。进程在 350 iteration 后正常结束，未见 CUDA OOM；下一步从 checkpoint 续训到至少 100M RL steps。

### 续训审计修正

- PBHC 上游只在 save boundary 把 `current_learning_iteration` 设为刚完成的零基 iteration；加载后又从该值开始循环，因此旧 checkpoint 会重复一个 iteration。现于每轮日志完成后保存“已完成 iteration 数”，新 checkpoint 恢复时从下一轮开始。
- `competence_evaluation_steps` 现随 checkpoint 保存/恢复；RL step 日志直接读取环境中随 maturation state 恢复的 `maturation_schedule_environment_steps`，不再用当前进程的 iteration 乘法推算。
- 旧 `model_300.pt` 的首次恢复重复了 iteration 300，属于额外 196,608 RL steps；策略、optimizer 和 maturation gate 状态均成功恢复。该额外预算将在诊断记录中保留，不从横轴删除。

### Stage-0 平台与能力边界诊断

- 续训至 152,764,416 RL steps 后，最近窗口 survival 在 0.8823–0.8861 间平台化，upright 约 0.936–0.938，low-saturation 约 0.959–0.962。由于 fall rate 仍约 0.114–0.118，未满足 0.08 上限，stage 0 没有晋级。
- 原配置继续训练已无明显边际收益，故在 checkpoint `model_750.pt` 后主动停止，而不是消耗完整剩余预算。该 checkpoint 包含 stage 0、累计 maturation schedule steps 和 16 个恢复段 competence windows 的状态。
- evaluator 新增 mean episode steps、raw action 边界占用率和逐关节边界占用率；`abs(raw_action)>2` 表示 `tanh` 已使用超过 96.4% 的当前动作范围。下一项检验是现有策略是否受 stage-0 实际最大 0.125 rad target residual 限制，并在保持 gate 阈值不变时把能力边界扩展到 stage-1 的 0.1875 rad。

### 首次晋级、探索噪声失稳与策略分布正则

- stage-0 action range 由 0.50 扩到 0.75 后，survival 从约 0.884 提升到最高 0.917，但仍有约 71% raw actions 位于 `abs(raw)>2`。进一步扩至 0.90 后，连续三个窗口 survival 为 0.9279、0.9408、0.9442，fall rate 最终为 0.0558；iteration 1075 首次按预注册 gate 自动晋级到 stage 1。
- stage 1 使用 200-step horizon，首五个 survival 为 0.6196、0.5693、0.5836、0.5547、0.6132；第五个窗口按滞回规则自动降回 stage 0。降级证明 gate 能撤销不成熟扩展，而不是只会单向开放。
- 失稳时 pre-tanh mean absolute action 达 6.62，94.9% raw actions 超过边界阈值；同时未经约束的 Gaussian effective std 随训练增大，晋级时 exploration scale 翻倍又进一步放大噪声。策略在 `tanh` 饱和区失去可辨控制分辨率。
- 修正：effective Gaussian std 限制在 `[0.05, 0.50]`，并加入 `-0.02` 权重的 mean-squared pre-tanh action regularizer。该项不改变关节/力矩硬限位或 gate，只约束策略分布保持在可学习区。必须从晋级前 checkpoint 重新验证 50→200-step 迁移。

## 2026-08-26：4 秒晋级与首个 20 秒站立窗口

- 从 iteration 1050 的 stage-0 checkpoint 重训后，噪声上限将 stage-1 effective std 从失稳时约 2.58 限制为 0.50；第一轮 200-step survival 为 0.6635–0.7231，pre-tanh mean absolute action 由约 4.36 降至 4.26，但旧 gate 在 fall rate 超过 0.25 时退级。
- 第二轮 200-step survival 从 0.7454 变化到 0.7426，raw-action boundary fraction 从 0.845 降至 0.828。诊断表明 `forced_demotion_fall_rate=0.25` 会把刚进入四倍 horizon 后的正常练习当作能力退化；将其改为 0.50 后允许策略在 survival 高于 0.45 时继续练习，晋级的 maximum fall rate 仍保持 0.08。
- PBHC 会把所有 reward scale 乘控制步长 0.02。原 `termination=-20` 因而每次跌倒只有 -0.4；改为与上游 locomotion 配置一致的 -200 后，200-step survival 新高由 0.7950 逐步提高到 0.8806。
- adaptive-KL 学习率在相邻 checkpoint 间从 2.25e-5 摆到 1.139e-4，性能随之回摆。固定为 5.0625e-5 后，200-step survival 依次达到 0.8821、0.8873、0.9003、0.9125，并在 iteration 2200 首次达到 0.9208。再从该 checkpoint 以实际写入 Adam 参数组的 2e-5 巩固，后两窗为 0.9265、0.9309，结合恢复的 promotion streak 自动晋级 full-body。
- 首个 1,000-step/20-second held-out 窗口为 survival 0.9301、upright 0.9990、mean episode steps 936.6；后续新高为 0.9517（396/8,192 失败，mean episode steps 956.1）。按成功轨迹站满 1,000 步反推，失败轨迹平均约在前 91 步终止，当前瓶颈是随机初始姿态/速度的早期恢复，而非多数轨迹的长期维持。
- final-stage effective exploration std=0.50 时 20-second survival 从 0.9418 回落到 0.9131；因此 full-body consolidation 将 exploration scale 从 1.0 固定为 0.50，并以 1e-5 小步长继续。该修改不改变动作 authority、初始随机化或评估 horizon。
- 新增可选 `resume_learning_rate`：加载 optimizer state 后同时覆盖 PPO 属性与所有 Adam param groups。第一次实现只改属性、checkpoint 实测仍为 5.0625e-5，已标为无效分支；修复后保存 checkpoint 反向核验为 2e-5 和 1e-5。CPU tests 为 21 passed。
- 科研边界：0.92 只是在内部课程中进入更长练习的 readiness threshold，不是“学会站立”。最终标称条件验收改为独立未见 seed 的 8,192 个 1,000-step episodes 中 0 次跌倒，并额外硬检全程/终点 base height、upright 与双足支撑；扰动和动力学随机化成功率单独报告。当前最好 0.9517 尚不满足该标准，不能写成完整 G1 站立成功或方法优于 PPO。

## 2026-08-26：从 survival 100% 到全程严格直立 100%

- 继续用短 episode 反复练习早期恢复：两个 4-second drill 和一个 2-second drill 将强初速度随机化（六维均匀分布 `[-0.5, 0.5]`）下的 20-second survival 从 0.9517 依次提高到 0.9795、0.9839 和 0.9915。该结果是 recovery robustness 诊断，不与 nominal standing 混报。
- 将正式轻扰动条件固定为六维 root velocity `[-0.05, 0.05]`、未见 evaluator seed 92003。旧策略达到 8,192/8,192 survival 后，视频审计仍发现躯干通过腰关节明显前倾；因此 survival 100% 被明确否决为“完美站立”。
- evaluator 增加全程 base height、`sin(tilt)^2`、腰 pitch/roll 相对默认姿态、终点双足支撑，以及每条轨迹的峰值与最后一次越界步。严格 episode 要求 1,000 steps 全程 base height >=0.70 m、`sin(tilt)^2 <=0.01`（约 5.7°）、腰 pitch/roll 各自绝对偏差 <=0.10 rad，并在终点保持双足支撑。
- 新增腰 pitch/roll 二次对齐惩罚。第一轮姿态巩固把终点平均腰偏差降到约 `[0.034, 0.014]` rad，但全程峰值仍约 `[0.291, 0.232]` rad，严格率为 0。进一步定位显示腰部最迟在第 70 步后恢复，但少量 base tilt 在后期仍越界，故没有通过放宽判据掩盖回摆。
- 一个只强调轻扰动与基座稳定的分支虽使 1,024 条轨迹中 975 条全程通过 gravity 阈值，却产生 0.169 rad 的稳定腰偏置，判为退化并弃用。最终从该稳定基座分支以固定 5e-6 学习率、4-second episodes 和腰对齐权重 -100 做 200 iterations 校正。
- 最终独立复核：checkpoint `20260826_113206-adaptive_waist_bias_correction_20260826-.../model_3908.pt`；训练 seed 4，评估 seed 92003，8,192 env × 1,000 steps。结果为 survival 8,192/8,192、fall 0/8,192、strict standing 8,192/8,192；height/gravity/waist 全程合格与终点双足支撑均为 8,192/8,192。全局最坏 gravity error 0.009769，最坏腰 pitch/roll 偏差 `[0.044185, 0.029554]` rad，双足支撑步比例 0.999673，raw-action boundary fraction 0.09446。
- 可提交的证据清单和精确指标保存在 `results/validation/g1_strict_standing_20260826.json`；完整 evaluator JSONL 与 checkpoint 保留在上列本机 PBHC run directory，不把大型模型纳入 Git。
- 最终 8-second H.264 可视化保存为 `results/validation/media/g1_developmental_standing.mp4`；在 1/4/7 s 抽帧目检中躯干保持直立，没有旧视频的明显腰部前倾。录像使用 nominal zero injected root velocity，只用于定性展示；量化结论来自上述 `[-0.05, 0.05]` 轻扰动 episode bank。
- 本轮累计 checkpoint 记录为 767,426,560 RL environment steps 和 197,427,200 competence-evaluation steps。该累计数包含诊断、恢复 drill 及被否决分支，不能当作冻结算法的一次正式训练预算；正式组间样本效率比较必须从统一初始条件重跑并分别报告每个分支预算。
- 科研边界：这证明单个 Adaptive 诊断轨在当前 Isaac Gym G1、固定动力学和轻初速度扰动下达到了预注册的 20-second strict-standing 工程验收；不证明无限时域稳定，不证明动力学/推扰鲁棒性，也不证明 Adaptive 比 Direct PPO 样本高效。Direct、Fixed、强基线、多 seed 和消融仍须按共同预算运行。
