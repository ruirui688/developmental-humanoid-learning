# PBHC 上的 G1 发育式任务学习

## 研究边界

这一实现把 PBHC 用作 G1 资产、Isaac Gym 仿真、残差 PD 控制和 PPO 优化底座，不把 PBHC 的动作模仿任务当作本项目方法。纯发育配置明确将 `robot.motion.motion_file` 设为 `null`，环境类不继承 motion/general tracking，也没有动作参考、教师策略或预训练检查点接口。

当前任务是参考无关的姿态稳定学习。它不是 Direct PPO 基线：训练策略使用能力门控动作成熟、随成熟阶段变化的探索噪声、风险度量和 Body Schema 辅助目标。站立相关的高度、竖直、静止和双足接触信号只定义任务结果，不提供参考动作轨迹。

## 已实现机制

`DevelopmentalG1Env` 在 PBHC 的 23 维策略残差进入 PD 控制器前执行：

```text
executed_action = tanh(raw_action) * joint_mask(stage) * action_range(stage)
```

关闭残差的关节仍由 PBHC 的默认姿态 PD 控制；URDF 关节、速度和力矩硬限位保持不变。站立 MVP 的三个默认阶段都允许策略控制全身姿态，但 residual range / exploration scale 依次为 0.90/0.25、1.0/0.50 和 1.0/0.50。PBHC 随后再乘 0.25 的 PD action scale，因此三个阶段的最大 target residual 实际为 0.225、0.25 和 0.25 rad。策略显式观察阶段、关节掩码和动作范围。早期仅开放手臂/腰的版本形成了能力门控死锁：默认腿部 PD 不能独立站稳，而策略又无法控制腿部来满足 survival 晋级条件，因此已在 pilot 中否决。逐关节开放只有在后续加入外部支撑或可证明稳定的低层姿态控制后才重新作为独立消融。

能力门控要求生存、竖直、低风险、低力矩饱和和 Body Schema 准确率同时超过各自阈值，并满足连续窗口、最小驻留时间和最大跌倒率。降级使用独立阈值和滞回。训练 episode 不会直接触发晋级；`DevelopmentalPPO` 按固定间隔运行固定 seed 的确定性 episode bank，从该 held-out 窗口构造 `CompetenceSample` 后调用 `update_competence`，防止训练重置分布污染门控判据。每个 bank 中每个环境只贡献一次，避免快速失败环境自动 reset 后重复投票。stage 0/1/2 分别用 50/200/1000 control-step horizon 测量约 1/4/20 秒能力；这只是内部 curriculum，最终组间比较仍统一使用 1,000-step horizon。评估 steps 与 PPO environment steps 分开记录，评估后 reset 再恢复训练。

最终站立验收不再把“没有触发 termination”直接等同于站稳。每个 1,000-step episode 还必须全程满足 base height >=0.70 m、`sin(tilt)^2 <=0.01`、腰 pitch/roll 相对默认姿态的绝对偏差各自 <=0.10 rad，并在终点保持双足接触。evaluator 同时记录整段峰值和最后一次越界步，以识别 survival 指标隐藏的启动回摆或稳定躯干偏置。轻扰动正式条件使用六维 root velocity `[-0.05, 0.05]`；零扰动录像和 `[-0.5, 0.5]` 强恢复 drill 分开报告。

PBHC 原实现会在 episode reset 后把四帧历史全部清零；这对关节位置和投影重力不是中性观测。当前环境用第一次物理观测填充历史槽，避免策略在第一控制步看到不可物理的空白历史。这个修正属于状态初始化正确性，不使用未来信息或仿真特权信号。

不使用 Body Schema 的 Adaptive A0 消融同时把 schema 权重设为 0 并禁用 schema 硬阈值；不能让未训练的随机辅助头暗中阻止阶段晋级。Full 方法保留该指标。

Body Schema 使用 actor 的共享潜变量和实际执行动作预测下一步 52 维状态：23 维关节位置误差、23 维关节速度、3 维投影重力和 3 维机体角速度。终止步会被 mask，避免把 PBHC reset 后状态当作动力学后继。接触力不进入 actor；仿真接触只用于奖励、风险日志和后续接触估计器教师标签。

Isaac Gym 的刚体 contact-force tensor 是净力，不标识接触对方。PBHC G1 又启用了 self-collision，因此 hip/pelvis/shoulder 有接触力不等价于这些刚体碰到地面。高度审计确认旧 contact termination 会在接触体远离地面时大量误报；当前站立任务只用投影重力和 base height 终止跌倒，非足接触力仍单独记录为风险信号。若后续需要按地面接触终止，必须使用可区分 contact pair 的标签或经过验证的几何过滤器。

## 配置与运行

PBHC/Hydra overlay 全部保存在 `configs/pbhc/`，没有修改 `external/PBHC`。最小 GPU 验证为：

```bash
./scripts/pbhc_developmental_smoke.sh
```

脚本复用 `external/conda/pbhc`、`external/PBHC`、现有 Isaac Gym 和编译缓存，不执行下载。它先验证 G1 的 23 个关节和 24 个折叠刚体映射，再运行 1 个环境、24 个仿真步和 1 次 Developmental PPO 更新。

同一入口可验证公平的 Direct 和 Fixed overlay：

```bash
./scripts/pbhc_developmental_smoke.sh maturation=dhl_direct
./scripts/pbhc_developmental_smoke.sh maturation=dhl_fixed_pilot
./scripts/pbhc_developmental_smoke.sh maturation=dhl_adaptive_pilot \
  algo.config.competence_evaluation.interval_iterations=1
```

Direct 从第一步锁定在完整动作阶段，Fixed 按累计 environment steps 经过相同的三个阶段；两者关闭 Body Schema loss。二者仍使用同一个 `BodySchemaActor` 类以保持 actor 编码器和 action head 容量一致，未启用的辅助 head 不参与动作推理。pilot 的 Fixed 阈值只用于接线验证，正式阈值必须在共同训练预算确定后冻结。

## 当前工程状态与尚未声称完成的部分

- 单个 Adaptive 诊断轨已在未见 seed 的 8,192 个轻扰动 episode 中达到 20-second survival 和 strict standing 均为 100%；这是 G1 软件站立工程验收，不是组间性能结论；
- 该 checkpoint 来自多轮诊断与奖励校正，包含被否决分支的模型选择过程，不能直接用于无偏样本效率比较；
- 接触估计器以及以其验证误差参与完整方法的闭环尚未实现；
- 固定成熟、自适应成熟和完整方法的多 seed 正式对比尚未运行。
