# 项目优势与技术路线

## 1. 项目定位

**Developmental Humanoid Learning** 研究类人发育式人形机器人运动学习：机器人不是针对每个复杂动作从随机策略开始海量试错，而是先认识自身身体、形成低维运动基元和安全平衡能力，再持续组合和迁移已有技能。

长期研究问题是：

> Can a humanoid robot learn to walk with fewer trials, fewer catastrophic falls, and less dependence on massive simulation?

当前仓库并不直接回答真机问题，而是提供进入该研究路线的第一道可行性检查。

## 2. 与常见训练范式的区别

### 常见单任务路线

```text
Task → Reward → Massive Trial-and-Error → Policy → Sim2Real
```

### 本项目路线

```text
Safe Body Exploration
        ↓
Body Schema / Forward Model
        ↓
Balance and Contact Knowledge
        ↓
Human-inspired Motor Primitive
        ↓
Supported Skill Acquisition
        ↓
Independent and Continual Learning
```

区别不在于是否使用神经网络或强化学习，而在于复杂技能是否建立在已经形成的身体知识和运动能力之上。

## 3. 核心优势

### 3.1 以严重失败成本为核心指标

真实机器人中的跌倒不是免费的负奖励。本项目除成功率和动作误差外，优先统计：

- Environment / real-world interactions；
- Number of catastrophic falls；
- Human intervention and reset；
- Energy and hardware stress；
- Skill transfer efficiency。

当前二维实验已经把训练期严重跌倒和最终测试跌倒纳入标准输出。

### 3.2 从低风险到高风险的课程

课程按照“强支撑 → 弱支撑 → 无支撑”推进：

```text
Body Babbling → Balance → Weight Transfer → Supported Walk → Independent Walk
```

这不是机械复刻婴儿姿势，而是提取发育原则：先简单后复杂、先多支撑后少支撑、先安全后自主。

### 3.3 显式 Body Schema

策略编码器不仅服务于当前奖励，还通过前向模型学习：

$$
(s_t,a_t)\rightarrow\hat s_{t+1}.
$$

它为未来的系统辨识、风险预测、模型式 rollout 和身体变化适应提供统一接口。

### 3.4 可审计的人体运动先验

当前先验由交替步态相位和前庭式髋部反馈构成。其形式、样本数量和损失权重均公开记录。这样可以在后续实验中逐项替换为：

- Human motion capture；
- OpenSim inverse dynamics；
- Muscle synergy / NMF；
- Dynamical Movement Primitives；
- Teacher policy demonstrations。

### 3.5 同一策略的技能连续积累

五个发育阶段复用同一条件策略而非独立训练五个模型。阶段条件进入观测，使策略能够区分目标速度、步态幅度和外部支撑，并降低阶段间相互覆盖。

### 3.6 结论可证伪、结果可复现

代码固定训练预算、未见随机种子、成功阈值和最终无支撑评估条件；逐种子 CSV、统计量、图表和视频与源码一同公开。不利的关节 RMSE 结果也被保留并解释。

## 4. 当前证据

在 5 个未参与调参的训练种子上：

- DHP-PPO：5/5 个策略成功，150/150 个无支撑测试回合成功；
- 直接 PPO：0/5 个策略成功，0/150 个测试回合成功；
- 训练期严重跌倒由 1402.8 降至 63.0，减少 95.51%；
- 两组环境交互均为每种子 76,800 次；
- DHP-PPO 额外使用每种子 8,192 个先验监督样本。

因此当前证据支持的是“完整组合方案在理想二维代理中可行”，尚不能识别单个组件的因果贡献。

## 5. 下一步验证矩阵

### 5.1 因子消融

至少执行以下开关组合：

| Curriculum | Body Schema | Human Prior | 目的 |
|---:|---:|---:|---|
| 0 | 0 | 0 | 直接 PPO 基线 |
| 1 | 0 | 0 | 课程独立贡献 |
| 0 | 1 | 0 | Body Schema 独立贡献 |
| 0 | 0 | 1 | 人体先验独立贡献 |
| 1 | 1 | 0 | 身体表征与课程交互 |
| 1 | 0 | 1 | 先验与课程交互 |
| 0 | 1 | 1 | 先验与表征交互 |
| 1 | 1 | 1 | 完整 DHP-PPO |

每组建议至少 20 个训练种子，并使用留出的环境参数组合进行评估。

### 5.2 信息预算匹配

给直接 PPO 提供等量演示数据，或将先验样本折算进总样本预算，从而区分“更好的信息”与“更多的信息”。

### 5.3 真实接触动力学

迁移到 MuJoCo / Isaac：

- 取消直接速度代理；
- 使用足—地摩擦、冲量与接触切换；
- 加入关节力矩、延迟、噪声和饱和；
- 评估推扰恢复和地形泛化。

### 5.4 真机安全验证

真机初期仅允许吊架或外部支撑下的 Body Babbling、平衡和单步实验。正式记录真实交互、人工复位、能耗、冲击、温度和力矩饱和。

## 6. 项目价值

如果后续消融、刚体仿真和真机实验继续支持该路线，项目价值不只是得到一个新的 Walking Policy，而是建立一套以技能积累、身体认知和失败前安全信号为中心的人形机器人学习范式。

