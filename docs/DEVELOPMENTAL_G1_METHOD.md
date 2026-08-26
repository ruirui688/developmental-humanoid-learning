# PBHC 上的 G1 发育式任务学习

## 研究边界

这一实现把 PBHC 用作 G1 资产、Isaac Gym 仿真、残差 PD 控制和 PPO 优化底座，不把 PBHC 的动作模仿任务当作本项目方法。纯发育配置明确将 `robot.motion.motion_file` 设为 `null`，环境类不继承 motion/general tracking，也没有动作参考、教师策略或预训练检查点接口。

当前任务是参考无关的姿态稳定学习。它不是 Direct PPO 基线：训练策略使用能力门控动作成熟、随成熟阶段变化的探索噪声、风险度量和 Body Schema 辅助目标。站立相关的高度、竖直、静止和双足接触信号只定义任务结果，不提供参考动作轨迹。

## 已实现机制

`DevelopmentalG1Env` 在 PBHC 的 23 维策略残差进入 PD 控制器前执行：

```text
executed_action = tanh(raw_action) * joint_mask(stage) * action_range(stage)
```

关闭残差的关节仍由 PBHC 的默认姿态 PD 控制；URDF 关节、速度和力矩硬限位保持不变。站立 MVP 的三个默认阶段都允许策略控制全身姿态，但 residual range / exploration scale 依次为 0.15/0.25、0.35/0.50 和 1.0/1.0。策略显式观察阶段、关节掩码和动作范围。早期仅开放手臂/腰的版本形成了能力门控死锁：默认腿部 PD 不能独立站稳，而策略又无法控制腿部来满足 survival 晋级条件，因此已在 pilot 中否决。逐关节开放只有在后续加入外部支撑或可证明稳定的低层姿态控制后才重新作为独立消融。

能力门控要求生存、竖直、低风险、低力矩饱和和 Body Schema 准确率同时超过各自阈值，并满足连续窗口、最小驻留时间和最大跌倒率。降级使用独立阈值和滞回。训练 episode 不会直接触发晋级；`DevelopmentalPPO` 按固定间隔运行固定 seed 的确定性 episode bank，从该 held-out 窗口构造 `CompetenceSample` 后调用 `update_competence`，防止训练重置分布污染门控判据。每个 bank 中每个环境只贡献一次，避免快速失败环境自动 reset 后重复投票。stage 0/1/2 分别用 50/200/1000 control-step horizon 测量约 1/4/20 秒能力；这只是内部 curriculum，最终组间比较仍统一使用 1,000-step horizon。评估 steps 与 PPO environment steps 分开记录，评估后 reset 再恢复训练。

不使用 Body Schema 的 Adaptive A0 消融同时把 schema 权重设为 0 并禁用 schema 硬阈值；不能让未训练的随机辅助头暗中阻止阶段晋级。Full 方法保留该指标。

Body Schema 使用 actor 的共享潜变量和实际执行动作预测下一步 52 维状态：23 维关节位置误差、23 维关节速度、3 维投影重力和 3 维机体角速度。终止步会被 mask，避免把 PBHC reset 后状态当作动力学后继。接触力不进入 actor；仿真接触只用于奖励、风险日志和后续接触估计器教师标签。

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

## 尚未声称完成的部分

- smoke 和 737,280-step 单 seed pilot 均不等于策略已经收敛；当前 50-step survival 约 45%，尚未晋级；
- held-out gate 已完成逐环境去重和阶段 horizon GPU 审计，但正式 episode bank、频率与阈值仍须在长训练前冻结；
- 接触估计器以及以其验证误差参与完整方法的闭环尚未实现；
- 固定成熟、自适应成熟和完整方法的多 seed 正式对比尚未运行。
