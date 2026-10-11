# C2-C：同剂量命令的时序重排与身体模型覆盖

> 2026-10-11；采集前冻结，development0/1/2 / supine / left_shoulder。新最终20/21/22不读取或执行。

## 1. 固定配方与问题

C2-B从clean `7a2462f2e5c9809f954ae49f3b34cc8411b5f4cc`完成27trial；独立审计SHA256 `d6cd7583ce0ddcc6dc73c457eb2980a537d581f0b88ec594f088f88d0743200d`，1,319,376 checks零失败，12历史锚点精确复现，选择保留old_hinge5。新hinge tracking均值仅改善0.9383%，位置域外仍96.5%–97%，没有解决部署覆盖。

本批固定 **old剂量 / hinge5 / endpoint_euler**，只重排300个校准命令的时序。模型结构、冷启动、RLS、身体、接触、权限、保护、目标与MPC均不变；不按本批结果换配方、追加脉冲或调参数。研究的是时序配方的总效果；重排也改变速度、接触和数据相关性，不能把收益只归因于位置覆盖。

共享公开身体、关节顺序/限位、理想原生感觉、通用初始速度模型、方向选择及MPC目标能力；不使用教师、预训练任务策略或示范。模型仅读当前encoder q/v和step前已知请求u；下一encoder v仅作校准标签。未来实际力矩、接触、世界状态和隐藏参数只作诊断。没有驱动到某个任务姿态再返回的探索反馈控制。

## 2. 两条校准与共同条件

每trial独立reset，原派生seed、supine/joint0，100步真实零请求前缀计账。qref及一次性方向s沿用前缀末encoder/公开限位规则；所有前缀精确配对，不缓存或延长等待。控制20 ms/子步2 ms，共同.5 N·m上限、其余七关节请求0，baseline接触与原环境保护不改。

```text
A = [.125,.25,.5,.125,.25,.5,.125,.25,.5,.125]
short: 10×30步block，每block 5步+s*A[i] / 10零 / 5步−s*A[i] / 10零
reordered active k:
  0..49    +s*A[floor(k/5)]
  50..149  0
  150..199 −s*A[floor((k−150)/5)]
  200..299 0
```

两者各50正/50反/200零，逐幅度/符号计数完全相同，完整计划请求绝对/平方努力均为.55 N·m·s / .20 (N·m)²·s。含active首命令相对prefix零的切换次数40→22；连续同向不保证位置达到.075 rad。实际力矩与实际努力可能不同，必须重新计量。

各自一个五参数模型独立冷启动theta=[1,0,.02,0,0]、P=100I、lambda=1、固定折点.25，特征和对称化沿用原实现。各完整20 ms校准转移只更新一次，部分间隔不更新；不从B参数或历史数据warm start。每seed600真实标签/600 RLS，全批1,800；所有评估冻结theta/P/count/积分与MPC。

## 3. 所有active段共享研究停止规则

原环境保护始终有效。另设只使用当前原生目标关节信号的StudyAbort：每次active step返回后，若 `abs(q−qref)>=.12 rad` 或 `abs(v)>=1.0 rad/s`，立即结束该trial；等值触发。两校准、两预测及全部控制都采用同一规则，prefix不适用新规则。

它只停止，不选择纠正动作、不返回起点、不放宽原限位/速度/能量保护；研究停止不是硬件安全证明。保存触发值、phase、index与独立study flag；env.terminated可false，不能冒充环境停止。完整末端转移允许评分/校准更新并存行，partial不更新；部分间隔原生状态及已知目标误差单列，不混入20ms预测/完整跟踪RMSE。即使最后计划步触发也completed=false，不能截短后算成功。完整terminal可作为离线窗口末端，不跨stop；单列study/env原因。

## 4. 预测、控制、预算与失败

共同low/full各100前缀+100active，幅度分别[.25,.25,.25,.25,.25]与[.125,.25,.375,.5,.375]，每20步7正/3零/7反/3零。short/reordered冻结模型、共同nominal和恒速度持久性在同一真实轨迹上评价，不为每模型重采。full两.375 block都保留，禁止挑段。

short_mpc、reordered_mpc、nominal_mpc各100前缀+200active，H15/9候选/原权重、范围、回退、精确决胜不变；当前目标前100为qref+s*.04，后100为qref+s*.08，无切换预告。不裁剪不可行目标、不增加权限或支撑。

每seed固定顺序calibration_short、calibration_reordered、prediction_low、prediction_full、short_mpc、reordered_mpc、nominal_mpc。共 **21 trials / 6,300控制调用 /63,000子步 /1,800 RLS**：prefix2,100/21,000，cal1,800/18,000，pred600/6,000，control1,800/18,000；126 s模拟时间，策略/教师/演示0。数学规划、测试、离线重放及wall/CPU另报。

任一cal失败仅阻塞自己的learned MPC，并阻塞依赖两cal完整的共同预测；另一cal/自己的MPC和nominal独立继续。nominal从自己的付费前缀建立通用模型，不依赖学习。普通异常/环境或研究停止保留，不补跑；中断/IO/日志fatal，剩余计划blocked。请求努力按真实付费子步计费，已返回未存行、失败规划与部分更新计账；缺失实际遥测/指标标下界或不可重算，不填零。

## 5. 独立一致性与两个开发门

源码commit/clean/原字节ZIP、依赖、全部计划/结果/更新/原生trace与SHA清单完整。独立标准库重算RLS、冻结参数、MPC、1/5/15/50自由递推、跟踪/努力/风险、所有phase/trial/batch上限、异常和StudyAbort。short校准、low预测、short/nominal控制应与B对应原生轨迹精确复现，额外StudyAbort若改变合法轨迹则明确记录；不得把复现算新独立seed。

**覆盖门**：三seed两条校准及short_mpc/reordered_mpc两条参考控制均须完整且无study/env stop、异常、非法请求或非有限状态；部分轨迹不能单独获得coverage_pass。校准样本为完整active转移的输入q/v，控制也取完整active输入；分别严格小于min或大于max为域外，等值域内。在每seed的short_mpc和reordered_mpc两条共同参考控制轨迹上，reordered校准的q域外比例都须≤10%且≤short校准；v域外比例都须≤short。两条校准×三条控制（含nominal）的q/v各自和并集比例、最近q距离`min_i abs(q−q_i)`的均值/最大均报告。共同轨迹支持比较不同校准暴露；包络不是安全集或准确性保证。

**性能门**：三seed全部7trial完整且无任何study/env stop、异常、非法请求或非有限状态；两共同预测的reordered速度RMSE逐seed≤short；200步tracking逐seed≤short，原始RMSE均值相对short至少降低5%；控制实际绝对/平方努力均值各≤1.05×short。零分母比例保持未定义；努力short=0只允许candidate=0。覆盖与性能门分别输出，只有两者及独立一致性都通过才采用reordered；否则保留short/old_hinge5，不改门、不追加动作或挑seed。

## 6. 完整诊断与接续

全部模型在两预测、最终模型校准in-sample、各自及配对控制轨迹上报告1/5/15/50端点/路径q/v，合法/排除/完整terminal窗口数、block/幅度及切换/保持分箱。未来日志请求仅为离线条件输入，不回灌未来真实状态，重叠窗口不是独立seed；50步退化、零段偏置与不利位置预测保留。

报告full/prefix/cal/pred/control全身体子步接触峰/冲量、动能峰、最深接触距离、八关节原生端点速度、软限位/屏蔽、饱和/回退/停止。共同前缀峰不掩盖active风险；同命令努力不等于同实际努力，零停止和采用门不授予安全结论。

本批不新增PD，九组经典开发成本保留。完成后统一冻结局部最终方案并一次评价新20/21/22；随后执行左肘及肩—肘协调、未知动力学与成熟门控。负结果也归档提交推送，不在单肩或单个实验后结束持续目标。

```powershell
$env:PYTHONPATH = 'src'
external/cpu_physics_env/Scripts/python.exe -m developmental_physics.local_coverage_ablation `
  --output external/local_coverage_20261011_development `
  --protocol docs/LOCAL_COVERAGE_ABLATION_PROTOCOL.md
```

实现、协议、审计与相关测试先提交推送，再从clean执行一次。相关：[B协议](LOCAL_DOSE_ABLATION_PROTOCOL.md)、[C1](MODEL_DOMAIN_RESULTS.md)、[连续目标](CONTINUOUS_EXECUTION_PLAN.md)。
