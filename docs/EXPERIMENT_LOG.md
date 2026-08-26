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

## 2026-08-26：旧 strict-standing 证据及其审计失效

- 继续用短 episode 反复练习早期恢复：两个 4-second drill 和一个 2-second drill 将强初速度随机化（六维均匀分布 `[-0.5, 0.5]`）下的 20-second survival 从 0.9517 依次提高到 0.9795、0.9839 和 0.9915。该结果是 recovery robustness 诊断，不与 nominal standing 混报。
- 将轻扰动开发条件设为六维 root velocity `[-0.05, 0.05]`、evaluator seed 92003。旧策略达到 8,192/8,192 survival 后，视频审计仍发现躯干通过腰关节明显前倾；因此 survival 100% 被明确否决为“完美站立”。seed 92003 随后被反复用于工程调参，不能再称为未见测试 seed。
- evaluator 增加全程 base height、`sin(tilt)^2`、腰 pitch/roll 相对默认姿态、终点双足支撑，以及每条轨迹的峰值与最后一次越界步。严格 episode 要求 1,000 steps 全程 base height >=0.70 m、`sin(tilt)^2 <=0.01`（约 5.7°）、腰 pitch/roll 各自绝对偏差 <=0.10 rad，并在终点保持双足支撑。
- 新增腰 pitch/roll 二次对齐惩罚。第一轮姿态巩固把终点平均腰偏差降到约 `[0.034, 0.014]` rad，但全程峰值仍约 `[0.291, 0.232]` rad，严格率为 0。进一步定位显示腰部最迟在第 70 步后恢复，但少量 base tilt 在后期仍越界，故没有通过放宽判据掩盖回摆。
- 一个只强调轻扰动与基座稳定的分支虽使 1,024 条轨迹中 975 条全程通过 gravity 阈值，却产生 0.169 rad 的稳定腰偏置，判为退化并弃用。最终从该稳定基座分支以固定 5e-6 学习率、4-second episodes 和腰对齐权重 -100 做 200 iterations 校正。
- 原“最终独立复核”后来审计失效：训练入口在 evaluation 前额外执行了一个 8,192-step PPO update；清单写 `model_3908.pt`，实际指标对应更新后保存的 actor/model 3909；因此 checkpoint、权重和指标未严格绑定。`results/validation/g1_strict_standing_20260826.json` 已标为 superseded，不再作为论文证据。
- 原策略虽满足姿态条件，却有全程 base angular speed 峰值约 5.58 rad/s、腰 pitch velocity 峰值约 7.49 rad/s，以及右肩/腰 yaw 大量 pre-tanh 饱和。旧 evaluator 没有运动学条件，故“strict standing 100%”隐藏了用户指出的回摆问题。
- 最终 8-second H.264 可视化保存为 `results/validation/media/g1_developmental_standing.mp4`；在 1/4/7 s 抽帧目检中躯干保持直立，没有旧视频的明显腰部前倾。录像使用 nominal zero injected root velocity，只用于定性展示；量化结论来自上述 `[-0.05, 0.05]` 轻扰动 episode bank。
- 本轮累计 checkpoint 记录为 767,426,560 RL environment steps 和 197,427,200 competence-evaluation steps。该累计数包含诊断、恢复 drill 及被否决分支，不能当作冻结算法的一次正式训练预算；正式组间样本效率比较必须从统一初始条件重跑并分别报告每个分支预算。
- 科研边界：上述阈值与 seed 均参与了开发选择，不能称为预注册或无偏测试；原工程验收结论撤回。Direct、Fixed、强基线、多 seed 和消融仍须按共同预算运行。

## 2026-08-26：冻结评估、带宽校正与恢复站立开发验收

- 实现真正 evaluation-only 路径：checkpoint 加载后直接运行 episode bank，不收集 PPO rollout、不执行 optimizer step、不保存新模型；运行前后逐一断言 checkpoint 文件、actor、critic SHA256 不变，RL schedule steps 与 maturation state 不变。评估记录精确 checkpoint/config/hash、源码与 PBHC revision、注入速度、reset warm-up、RL/evaluation budgets。入口为 `scripts/pbhc_evaluate_standing.sh`。
- reset 有一个未计入 RL/evaluation budget 的 zero-action warm-up control step；注入 root velocity 与 warm-up 后第一次观测速度现分开记录。此前 first-observation z velocity 约 0.195 m/s 是该步重力结果，不是隐藏注入。
- 增加一阶 residual target 带宽模型，最终开发配置 `action_smoothing_alpha=0.50`。旧 checkpoint 直接使用 α=0.20 会全部跌倒；α=0.80→0.50 的逐步适应训练把恢复后的平均最大 base angular speed 降至约 0.33 rad/s。直接把 α 降到 0.40/0.30 分别退化到约 94.6%/57.2%，α=0.40 适应训练也继续退化，均否决。
- 新增 base motion、腰速度与 raw-action peak 代价。强权重分支让 1,024/1,024 跌倒，否决；微小权重与小学习率分支保住 survival，并降低可见回摆。训练 episode 从 4 秒扩到与评估一致的 20 秒后，训练平均 episode 一度达到 1,001-step 上限；说明此前第 4–20 秒迟发漂移确有 train/eval horizon mismatch。
- 将训练扰动扩大到 `[-0.10, 0.10]` 的能力边界分支没有改善 8,192 条目标分布尾部，且继续训练退化，早停否决。计算量本身不是充分条件；必须对齐 horizon、带宽和验收信号，并保留退化分支。
- “任意一个 20 ms 样本越阈即整条失败”的零容忍运动指标随 horizon 墅长必然趋向失败，不能表达近无限站立。新开发验收保留全部峰值，同时区分：(1) 全程安全包络：height >=0.65 m、gravity error <=0.04、腰偏差 <=0.20 rad；(2) 3 秒扰动恢复后紧姿态：height >=0.70 m、gravity error <=0.01、腰偏差 <=0.10 rad；(3) 动态阈值：drift <=0.10 m、水平速度 <=0.20 m/s、base angular speed <=0.50 rad/s、腰速度 <=0.50 rad/s，允许至多 1% 样本越界且连续不超过 5 步；(4) 终点双足支撑。3 秒恢复窗和占空阈值均由开发 seed 确定，明确属于 post-hoc engineering acceptance，不能冒充预注册。
- 开发 checkpoint 为 `20260826_130236-adaptive_long_horizon_correction_20260826-.../model_4260.pt`，SHA256 `d9a8a24b1077432352089afebf254f2d2e9fb8161f63df599564550f7410cc9f`。冻结开发评估 seed 92003、8,192 env × 1,000 steps：0 跌倒；全程安全、恢复后紧姿态、动态占空与恢复站立均为 8,192/8,192。恢复后运动越界平均 0.00427 步/episode，最坏 2 步且最长连续 2 步（40 ms）；恢复后最大 base angular speed 0.5714 rad/s，平均逐轨迹最大值 0.3264 rad/s。零容忍旧口径仍只有 8,101/8,192，作为敏感性指标保留，不包装为 100%。
- 当前开发 checkpoint 仍有约 9.96% aggregate pre-tanh boundary occupancy，尤其 waist yaw 与 left hip pitch；这不是跌倒或可见持续回摆，但提示控制余量仍需在后续 action-distribution 消融中报告。
- 下一步冻结源码和 checkpoint 后，使用从未参与调参的 seeds 93001–93005 各跑 8,192×1,000 evaluation-only；再以 seed 93101 跑 8,192×5,000 的 100 秒长期审计。只有新种子结果才能升级为冻结工程测试证据。

## 2026-08-26：冻结新种子与 100 秒长期测试

- 在源码提交 `20022e36fe6911468310bf8dfd0e117f31fc0f77`、checkpoint SHA256 `d9a8a24b...0cc9f` 和 `results/validation/g1_frozen_test_protocol_20260826.json` 均冻结后才首次运行 seeds 93001–93005；评估期间没有修改阈值或选择 checkpoint。五个 run 的 checkpoint/actor/critic hash 前后均一致，policy updates=0，RL steps 与 maturation state 均不变。
- 20 秒结果：每个 seed 8,192/8,192 recovery-standing，合计 40,960/40,960；0 跌倒；全程安全、3 秒后紧姿态、动态占空和终点双足支撑全部为 40,960/40,960。各 seed 零容忍旧口径为 8,101、8,079、8,107、8,114、8,108/8,192，合计 40,509/40,960（98.899%），因此仍保留“存在稀少瞬时纠偏”的敏感性结论。
- 五 seed 的恢复后逐轨迹最大 base angular speed 均值为约 0.3257–0.3269 rad/s，全局最坏峰值为 0.6146 rad/s；运动阈值越界平均仅 0.00293–0.00464 步/episode，最坏 3 步且最长连续 3 步（60 ms）。全局最晚紧 gravity 越界为第 109 步，低于冻结 150-step 恢复窗。
- 100 秒长期测试使用此前未见 seed 93101、8,192 env × 5,000 steps，共 40,960,000 evaluation steps。8,192/8,192 均站满且全程安全，0 跌倒，动态占空 8,192/8,192；但 1 条轨迹到第 186 步才回到紧 gravity 阈值内，超过冻结 150-step 恢复窗，因此 recovery-standing 为 8,191/8,192（99.9878%），不能写成 100%。
- 100 秒运动越界平均 0.01831 步/episode，最坏 3 步、最长连续 3 步、最坏占比 0.0619%，仍远低于 1%/5-step 验收边界。零容忍旧口径为 7,990/8,192（97.534%），说明 horizon 增大时“从未有单样本过阈”的概率按预期下降，而持续性回摆指标仍保持通过。
- 完整逐 seed 指标、config hashes 和本机 evaluator JSON 路径记录在 `results/validation/g1_frozen_standing_test_20260826.json`。该证据支持固定动力学、轻初速度扰动下的有限时域软件工程结论；它仍不证明无限稳定、动力学/外力鲁棒性、Sim2Real 或相对 Direct PPO 的样本效率。
- 新增固定帧数 Isaac Gym recorder callback，并用同一 model 4260 在零注入初速度下录制 8.02 秒、1600×900、50 fps H.264 视频 `results/validation/media/g1_motion_aware_standing.mp4`。1/4/7 秒抽帧目检未见明显腰部回摆；视频 SHA256 `01cc6100...4683`。它是定性可视化，不替代多环境轻扰动量化，也不展示最坏 seed。

## 2026-08-26：论文图表与 G1 多媒体证据包

- 新增 `scripts/plot_g1_frozen_results.py`，只读取冻结清单 `g1_frozen_standing_test_20260826.json`，生成 PNG/SVG 四面板：有限 horizon 验收、瞬时纠偏占用、恢复后角速度尾部和累计 robot-hours。图中并列 recovery-standing 与零容忍敏感性，避免把 98.899% 误写为实际站立存活率。
- 新增通用抽帧工具 `scripts/make_g1_video_contact_sheet.py`。零注入录像生成 1/3/5/7 秒时间序列图和 800 px GIF；轻初速度扰动录像使用可视化 seed 93201、单环境、初始六维 root velocity `U[-0.05, 0.05]`、600 control steps，生成 12.02 秒 H.264、GIF 与 0.5/1.5/4/8/11 秒时间序列图。
- 轻扰动视频逐帧抽查未见跌倒、明显腰部前倾或持续可见回摆。它只有一条轨迹，明确标为机制可视化而非鲁棒性统计；没有用它替换冻结多环境状态日志。
- 新增 `g1_multimedia_manifest_20260826.json`，绑定源码 `dedd7558`、PBHC `ffac5cde`、model 4260 SHA256、全部媒体 SHA256、录像条件和证据边界。论文附录加入图 4–6 与三类 G1 视频说明；`docs/PAPER_COMPLETION_PLAN.md` 给出投稿前 P0/P1/P2 对照、消融、扰动与视频规范。

## 2026-08-26：路线偏差审计与能力前沿重启

- 用户否决了从近站立 reset 开始、只能维持姿态的 G1 展示，理由成立：它没有展示躺姿身体适应、局部承重、翻身、支撑和起身过程，也没有共同地面初态的 Direct 对照，因此不能支持原始“类婴儿学习更高效”命题。
- 配置审计确认旧 Standing MVP 的 root reset 为 `[0, 0, 0.8]` 和直立四元数，低高度与大倾斜立即终止，奖励从第一步强调站立。该任务按定义排除了地面探索；model 4260、对应图表和累计训练预算降级为末端控制/评估基础设施审计，不再作为核心方法优势。
- 第一版修正尝试使用四种地面 reset 和固定的 0.28→0.38→0.50→0.68→0.76 m 阶段目标。GPU 24-step smoke 可运行，实际 base height 均值约 0.212 m且未被低高度终止；但进一步科研审查认为固定高度阶梯仍由工程师预先规定能力路径，尚不等于机器人发现自身边界，因此在长训练前暂停。
- 核心方法改为 held-out capability frontier：先用零/随机策略标定可达状态分布，再把目标冻结在当前高度与直立度分位数之外一个小 margin；只有目标成功、安全承重、低饱和和 Body Schema 准确性连续通过时才移动前沿。新增 simulator-independent `CapabilityFrontier` 和测试，风险较高或饱和的“进步”不会解锁更难目标。
- 可复用成果仅包括 G1/动作/刚体映射、执行器和接触审计、风险计账、evaluation-only、GPU 并行与录制工具。近站立奖励和 checkpoint 不能迁移为 ground-start 论文结果；新三组必须从共同地面初态和随机初始化重新训练。

## 2026-08-26：地面起点、可撤除搀扶与持续事件验收

- 四类地面 reset（仰卧、俯卧、左侧卧、右侧卧）已经接入 G1，root 高度均为 0.34 m；躺卧、翻滚和安全地面接触不再触发低高度/倾斜终止。策略从随机初始化训练，不加载翻身、起身或站立动作、教师策略及旧 model 4260。
- 能力前沿首次校准使用与 PPO steps 分开计账的 held-out 随机策略轨迹。修正后的 Body Schema 指标是相对 persistence baseline 的预测增益 `clip(1-model_MSE/persistence_MSE,0,1)`；64-env 审计中随机网络 accuracy 为 0.00465（model MSE 0.04197，persistence MSE 0.00368），否决了旧绝对误差指标给出的虚假 0.859。
- 同一审计在 6,400 个 evaluation steps、0 个 RL steps 上得到 80% 可达分位数：base height 0.33211 m、upright score 0.00727。首个冻结挑战因此设为 0.36211 m 和 0.04727，而不是由工程师假定机器人应一步达到固定起身高度。
- 新增可撤除“家长/学步车”式外力：只对 pelvis 施加有界竖直和水平支撑，不给任何关节目标；机器人先自行抬高至 0.32 m 后才介入，0.55 m 达到阶段上限，最终独立站立阶段严格为 0 外力。每条轨迹分别累计 assistance fraction、力峰值、冲量、绝对机械功和介入时长。stage-2 GPU smoke 实测 mean force 0.485 N、impulse 0.401 N·s、absolute work 0.066 J、peak 8.61 N；数值很小是因为未训练机器人绝大部分时间没有越过介入高度。
- 新增持续事件而非单帧 success：相对初态转向超过 60° 持续 0.5 s 才计 rolling；由肘/足形成至少两个低位支点且 pelvis 高于 0.25 m 持续 0.5 s 才计 bracing；base 高于 0.45 m 持续 0.5 s 才计 raised；高于 0.72 m 且 upright score 至少 0.95 持续 1 s 才计 upright；最终 independent standing 还要求双足、base speed 不超过 0.20 m/s、外力严格为 0，并连续满足完整 1,000 control steps/20 s。已达事件保留到 episode 结束，瞬时越界会清零连续计数。
- held-out evaluator 现输出五个事件的 episode fraction，以及每条轨迹平均 assistance impulse/work/peak force。4-env GPU smoke 的未训练策略五项均为 0，辅助预算也为 0；这只是接线正确性，不是学习性能结果。
- 保存随机初始化、0 PPO update、seed 94000、0 assistance 的 8.02 s H.264 起点视频 `results/validation/media/g1_ground_start_untrained.mp4`，SHA256 `4f53e179...f46c396`；接触表 `results/validation/g1_ground_start_untrained_contact_sheet.png` 明确显示机器人落地后保持仰卧。首帧仍包含 reset/物理落地过渡，素材只证明任务从地面开始，不能被标注为发育进步。
- 验证：CPU `39 passed`，`git diff --check` 通过；地面事件与 held-out 计量分别完成 4-env GPU smoke。下一项是在冻结这些口径后运行 8,192-env Adaptive early-development pilot，先检验 rolling/bracing/raised 和身体模型是否真实上升；在出现证据前不启动对外声称“学会起身”的组间比较。

## 2026-08-26：地面发育阶段 0 通过与阶段 1 逐姿态审计

- 前一节的 0.34 m reset 与 0.362 m 首目标已被后续物理审计替代：0.34 m 会制造一次不必要的落地瞬态。四种 reset 现统一为 0.12 m；held-out 逐姿态 80% 分位数取最弱姿态而非总体平均，首个保守高度边界约为 0.14235 m。早期 action scale 继承站立任务的 0.25 后，stage-0 实际最大 residual 只有约 0.0875 rad，不能表达地面支撑几何；地面三组现共同使用 1.0 rad 基础 scale，再由成熟阶段限制实际权限。
- Body Schema 的绝对误差指标再次修正为相对 persistence 的逐样本技能，并把预测头改为预测状态增量；专用 optimizer 只更新 schema head，避免第二次 Adam 修改共享策略。门控只聚合关节速度和基座角速度两类动态量。stage-0 从 9.8M 延长到 59.0M RL environment steps 后，最后窗口 dynamic schema skill=0.10675、safe=0.93076、low-saturation=0.97613，连续第三窗满足 0.10/0.90/0.90 条件，自动从身体模型阶段晋级到翻身/支撑阶段。0.10 是本轮开发门槛，不是预注册性能阈值。
- 阶段 1 首次总体评估显示 rolling 62.2%、bracing 31.1%，但逐姿态拆分为：仰卧 100%/88.6%、俯卧 0%/0%、左侧 99.5%/2.5%、右侧 51.7%/35.3%。因此总体均值被明确禁止用于晋级，所有后续事件门控取四种姿态中的最小 fraction。原 bracing 同时要求 pelvis>=0.25 m，把地面支撑错误地变成起身测试；现改为 pelvis>=0.11 m、肘/足至少两个支点、相对初态改变至少 20°并持续 25 步，独立的 raised 门槛仍为 0.45 m。
- 新增困难姿态练习分配：评估 bank 始终保持均匀采样，训练 reset 根据逐姿态缺口增加练习，但以均匀复习为主体、平滑更新且随 checkpoint 保存。未加限制的第一版在仰卧/俯卧/左右侧卧间发生灾难性遗忘，最弱翻身率在 1.8%–25.1%间摆动；该失败分支保留，不作为优势结果。限制困难采样幅度并把翻身与支撑改成不可相互补偿的联合目标后，冻结 model 530 的四姿态 rolling/bracing 为 100/100%、57.5/96.4%、93.3/94.9%、27.9/99.6%；最弱仍只有 27.9%，不允许晋级。
- 高探索分支的训练 rolling 可达约 60%，但 deterministic held-out 策略在姿态间回摆；effective Gaussian std 长期顶在 0.50。地面配置将 entropy coefficient 降至 0.001、std 上限降至 0.25，并把冲击、基座角速度和峰值力矩作为技能奖励的乘法安全前提。低噪声分支消除了接近 0 的快速遗忘，但右侧 deterministic rolling 仍约 17%–23%，且 low-risk 一度只有约 0.80；这仍是阶段 1 未解决问题。
- 进一步发现奖励以“相对本回合起始姿态的转角”定义，但四步历史滑出后 actor 不再知道初态，任务形成部分可观测问题。现加入回合开始时缓存的三维 IMU gravity 作为 actor/critic 输入；它不读取接触力或仿真特权，真实部署可在 reset 时从 IMU 保存。旧 checkpoint 第一层插入三个全零权重列，迁移瞬间 action/value 输出保持不变，optimizer 不跨形状迁移。GPU evaluation-only 已验证旧 model 630 可无更新加载；随后从该点继续训练。
- 辅助支撑仍未被拿来解释阶段 1 进展：其 0.20 配置在 0.32 m 介入高度以下基本不工作。只有进入 supported-rise 阶段后才允许可计量 pelvis 外力；最终 independent-standing 仍要求连续 1,000 步严格 0 assistance。
- 当前验证：CPU `51 passed`，`git diff --check` 通过。上述均为单 seed 方法开发和失败诊断，不是 Direct/Fixed/Adaptive 样本效率结论；当前状态为 stage 1 继续训练，尚未学会起身、直立或独立站立。

## 2026-08-26：阶段 1 安全瓶颈、逐执行器审计与力矩反馈

- 用初态 IMU 记忆、固定学习率、0.30 动作平滑和自策略巩固后，阶段 1 的四姿态最弱 rolling/bracing 联合指标连续达到 0.506、0.512、0.546；但 low-risk 约 0.897–0.898、low-saturation 约 0.892，未满足二者均至少 0.90 且连续三窗的门控。技能过线不能补偿安全未过线，因此没有晋级。
- 将地面冲击代价从 -2 加到 -4、绝对力矩越界代价从 -0.10 加到 -0.15 后，6 个 held-out 窗口的技能最弱值为 0.514–0.552，但 low-risk 仍为 0.896–0.899、low-saturation 为 0.891–0.892，确认单纯延长计算不会越过门槛。把阶段 1 巩固回拉从 0.30 降到 0.20、绝对力矩代价加至 -0.30 后，low-risk 连续达到 0.901–0.904，low-saturation 提高到约 0.895–0.896；继续训练则最弱技能在 iteration 940 降至 0.487，故早停并保留 model 930 作为最接近的分支点。
- evaluator 新增逐关节、前 10 步和后 190 步的力矩饱和率。model 930 的诊断窗口为联合技能 0.522、low-risk 0.9002、low-saturation 0.8949。后 190 步主要饱和为左肩偏航 0.621、左肩俯仰 0.445、左肘 0.368、腰俯仰 0.271、腰侧倾 0.203；并非腿部承重或仅复位冲击造成。
- 上游 `limits_torque` 按绝对 N·m 计算，会低估额定力矩较小的肩肘电机。新增按额定力矩比例计算的连续二次 headroom 代价，并以单元测试确认 10 N·m 与 100 N·m 电机在相同相对负载下代价一致。该分支的 low-saturation 仍约 0.894，且最弱技能下降到 0.462–0.498，已否决；奖励可观测性不足，不能靠更大权重修复。
- 更关键的接口审计发现，actor 虽然具备 IMU、关节状态与动作历史，却没有论文路线所要求的力矩/电流历史，因此无法从反馈识别自身执行器边界。现加入 4 帧×23 关节的有符号归一化力矩历史，actor/critic 维度由 426/429 变为 518/521；旧 checkpoint 与巩固 anchor 在历史块末尾插入 92 个零权重列，迁移瞬间不改变旧策略输出。GPU 已验证 model 930 与 anchor 可完成迁移并开始训练。
- 首次力矩历史分支因整体巩固仅 0.20，最弱技能从 0.502 降到 0.446，已早停。下一修正是选择性巩固：旧感知/动作通路恢复 0.30 回拉，新增力矩输入列不回拉到零，使旧技能保留与新反馈学习不再互相排斥。阶段 2 另已修复明确目标缺失：进入 supported-rise 后将连续优化 0.50 m 高度目标，0.32 m 前不介入、之后只给可计量 pelvis 外力；阶段 2–4 的巩固率降为 0.05/0.05/0.02。
- 当前验证为 CPU `53 passed` 和 `git diff --check` 通过。所有数值仍是单 seed 开发证据；阶段 1 尚未连续通过，起身、站立和组间优势仍均未成立。

## 2026-08-26：阶段 1 正式晋级与阶段 2 小台阶起身诊断

- 选择性巩固解决了“学习新增力矩反馈时遗忘翻身”的冲突：旧 encoder/action 通路以 0.30 回拉，新增 92 维力矩历史输入列不向零列 anchor 回拉。iteration 940–990 的四姿态最弱 rolling/bracing 从 0.536 提升到最高 0.619 后回落；model 970 是技能与力矩余量较好的分支点。
- 逐时段冲击审计显示 model 970 的严重冲击并非只来自 reset：旧 250 N 阈值下前段/后段 unsafe fraction 分别约 0.142/0.104。随后核对 G1 XML 各刚体质量总和为 31.693 kg、静重约 310.9 N；250 N 低于整机静重，会把普通单刚体承重误标为严重冲击。地面轨 post-hoc 改用 650 N（约 2.1 倍体重）作为 severe-impact 标签，220 N 舒适承重 shaping、原始接触力与落地速度仍保留。该校正属于方法开发，不得写成预注册阈值。
- 从 model 970 以 1e-6 学习率确认，iteration 980/990 的最弱联合技能为 0.6112/0.6132，low-risk 0.99473/0.99471，low-saturation 0.90102/0.90241。第三窗第一次运行已触发晋级，但晋级后对含非叶 autograd 缓存的 actor 整体 `deepcopy` 崩溃，记录和新 checkpoint 未落盘，故没有把该次算作证据。
- 锚点刷新改为复用干净网络并只加载 actor `state_dict`。从崩溃前 model 995 重放后，iteration 1000 得到最弱联合技能 0.60517、low-risk 0.99472、low-saturation 0.90289；门控连续第三次确认并正式从阶段 1 晋级到阶段 2。`model_1000.pt` 保存的 maturation state 为 stage 2，累计 RL environment steps 为 196,804,608。该结果只证明地面翻身/支撑门通过，不是起身成功。
- 第一版阶段 2 固定追逐 0.50 m sigmoid 目标，搀扶到 0.32 m 才介入。100 iterations/19,660,800 新 RL steps 后两个 400-step held-out 窗口的持续 raised 均为 0，最弱高度约 0.232→0.234 m，总体 80% 高度约 0.374→0.375 m，证明这是梯度/辅助断层而不是计算量不足。
- 第二版将高度改为从 0.12 m 到目标的线性必要因子，并让搀扶从 0.18 m 渐进介入、0.45 m 达到设定比例。阶段 2 的 0.55 assistance fraction 对应最大上托约 99 N，远低于 310.9 N 体重，不能独自吊起机器人。100 iterations 后最弱姿态高度由 0.231 升至 0.262 m，右侧卧达到约 0.424 m，但总体高度平台约 0.395 m，10 个窗口持续 raised 仍全为 0；说明连续梯度有效但单个 0.50 m 目标仍跨度过大。
- 当前加入阶段 2 内部能力小台阶：首目标 0.20 m；每个 held-out 窗口按四姿态最弱成功率更新，至少 40%、low-risk 至少 0.90、low-saturation 至少 0.90 且连续确认后，每次最多提高 0.03 m，最高 0.50 m。最终阶段晋级标准不变，仍要求四姿态最弱 sustained-raised 至少 0.50、双安全指标至少 0.90、连续三窗。早期错误的 0.28 m 首台阶仅有 0–1% 最弱成功率，已否决；0.20 m 分支首两窗约 42% 成功，但力矩余量约 0.892–0.895，故仍正确拒绝移动。
- 当前验证为 CPU `59 passed` 和 `git diff --check` 通过。正在从 stage-1 晋级 checkpoint 重跑修正后的 3 cm 小台阶课程；尚无阶段 2 起身通过结果，更无 Direct/Fixed/Adaptive 组间优势结论。

## 2026-08-26：阶段 2 小台阶推进与辅助消融

- 高度前沿按 `0.20→0.23→0.26→0.29 m` 连续推进，每次最多 3 cm；0.32 m 当前约 0.307–0.310 m，持续 raised 仍 0.1–0.5%。
- 当前高度缺口采样使仰卧采样约 31%；困难采样、0.65/0.75 权限和原 0.45 m full-support 曲线的消融均保留并按安全指标否决。提前 full-support 到 0.32 m 后，0.29 m 最弱成功率约 44–56%，辅助冲量约 388–534 N·s、机械功约 24 J/episode。
- 当前从 model 1400 续训的 0.32 m 分支尚未形成 raised；不是成功结论。CPU `59 passed`、`git diff --check` 通过。
- 该续训最终到约 294.9M RL environment steps；最新 400-step held-out 窗口最弱保守高度 0.3062 m、0.32 m 目标成功率 0.0042、raised 0，low-risk 0.9976、low-saturation 0.9115。逐姿态高度为 supine 0.306、prone 0.337、left-side 约 0.40、right-side 0.427 m；仰卧是明确瓶颈。该分支已停止，避免把无进展预算误当作计算量证据。

## 2026-08-26：阶段 2 支撑比例版本 1

- 从 model 1500 分叉，将 supported-rise assistance fraction 从 0.65 提高到 0.80，最大上托约 144 N（仍低于约 311 N 体重），动作权限保持 0.72，最终 raised 门槛不变。
- 前两窗最弱高度达到 0.325–0.326 m，0.32 m 目标成功率 40.5%/37.1%，low-saturation 91.15%；辅助冲量约 679 N·s、机械功约 40.7 J/episode。
- 继续至 iteration 1560 后成功率回落到 26.3%，高度 0.321 m，raised 仍为 0。该版本改善了卸载高度但未产生稳定起身，作为辅助过强/策略退化风险诊断保留。
- 因此训练默认已恢复为 0.65 支撑比例（最大约 117 N）；0.80 不进入下一主线 checkpoint。合并 iteration 1080–1560 的 49 个 held-out 窗口生成 `g1_ground_frontier_progress.png`，并保存仅含绘图指标的冻结 JSON。曲线明确显示 0.20→0.29 m 的证据门控推进、0.32 m 平台和 0.80 分支的先升后退，未形成起身成功结论。
