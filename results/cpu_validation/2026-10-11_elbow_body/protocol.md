# C4-B：左肘身体模型与局部控制的开发协议

2026-10-11；在本批左肘身体辨识与控制的真实轨迹执行前冻结。实现、独立审计及相关合成检查完成并提交推送后，从干净源码一次执行。本批使用已见 development0/1/2，属于开发迁移，不能称独立留出或最终验证。

## 固定问题、配方与经典来源

第二关节固定为 **supine / j1 left_elbow**，不因失败更换关节。唯一身体模型配方为 **short / old / hinge5 / endpoint_euler**；沿用肩部保留方案，不在本批追加校准、改变模型结构、积分、MPC参数或选择其他配方。每个seed重新冷启动，不复用肩部theta/P、参数或历史日志。只检验指定左肘条件中的预测及同MPC模型贡献，并与独立开发选择的经典控制比较；闭环自身预测和模型有效域仍须单独报告。

经典PD固定为 **Kp64 / Kd1（candidate8）**，来源是[C4-A左肘开发结果](ELBOW_PD_DEVELOPMENT_RESULTS.md)：

| 来源项 | 冻结值 |
|---|---|
| 正式采集源码commit | `91223b39c86fbeb09f7bc399229789b1e00ce181` |
| 首次独立audit SHA256 | `d84ad31b28f7fcc4ded8003b2503138a3cacc9f9b2fed33bf675758e43100571` |
| 独立summary SHA256 | `5aaefe21d6aa8314673a5560522e8865123acda318e833b4951f4c5d00efc3e8` |
| 选中candidate | `8`，Kp64/Kd1 |
| 全部九候选的实际开发成本 | **7,521控制调用 /75,210子步 /0身体模型更新** |

九候选、失败和前缀都是PD调优成本，不能只计所选候选。Kp和Kd位于有限网格上界，不证明全局最优；本批评价结果不能用于扩大网格。肩部64/0不是本关节的调优基线。本批不读取或复用单肩真实20/21/22轨迹，development0/1/2已见；未来独立评价另冻结未见bank。

## 共同初始信息与物理条件

沿用原MuJoCo CPU身体、baseline接触、理想原生感觉、公共关节索引/限位、原环境保护；控制调用20 ms，每调用10个2 ms子步。目标关节请求权限为0.5 N·m，其余七关节请求恒零。身体资产、原生感觉、基础控制、公共限位、任务目标、零请求前缀和保护均为共享初始条件；现有MPC与PD已有公共目标位置控制能力。

每trial独立reset，保持原 `SeedSequence(seed).spawn(2)[0].generate_state(1)[0]` 派生规则。每trial自己付费执行100步零请求前缀，从自身前缀末encoder q与公共限位一次确定qref及方向s，前缀须精确配对。保持原生肘qref，即使柔性限位下略负也不裁到0，不缓存历史值、不延长等待、不读取肩部qref。

模型只读step前的当前encoder q/v与已知请求u；next encoder v仅作校准标签。实际未来力矩、接触、世界状态、动能和仿真隐藏参数只作诊断，不进入模型特征、控制或方向选择。教师调用、外部演示、预训练任务策略、策略参数更新和在线PD增益更新均为0。

## 校准、共同预测与冻结控制

hinge5初始theta=`[1,0,.02,0,0]`，P=`100I`，lambda=`1`，固定hinge折点0.25 N·m。通用冻结nominal使用原linear4；零hinge初始预测与hinge5相同。每seed一个独立calibrator，只在300个完整20 ms校准转移中各更新一次；prefix、partial和全部评价不更新。校准完成后冻结theta/P/count、积分方式及控制配置；冻结nominal、冻结learned与恒速度持久性按各自定义报告。

```text
A或−A均乘一次性方向s。
A = [.125,.25,.5,.125,.25,.5,.125,.25,.5,.125] N·m
short: 10个30步block，每block 5步+s*A[i] /10零 /5步−s*A[i] /10零。
prediction_low:  五个20步block，幅度[.25,.25,.25,.25,.25]。
prediction_full: 五个20步block，幅度[.125,.25,.375,.5,.375]。
每个prediction block: 7步正 /3零 /7步反 /3零。
```

校准完整计划50正/50反/200零，计划请求绝对/平方努力分别0.55 N·m·s、0.20 (N·m)²·s；实际力矩及实际努力按付费子步重新计量。low/full各100个active转移，nominal/learned/persistence在同一真实预测轨迹上评分，不为不同模型重采，不挑full的某一幅度或block。

四种控制各200个active转移。当前目标active0–99为 `qref+s*.04`，active100–199为 `qref+s*.08`；只给当前目标，不预告切换。目标必须在公共限位0.03 rad内缩内，不可行则失败，不裁剪目标。nominal与learned MPC保留原FixedLocalMPC的H15、9候选、权重、预测域、回退及精确决胜；nominal从自己的付费前缀建立通用冻结模型，learned使用本seed校准后冻结模型。

PD请求为 `clip(64*(target-q)-1*v,-.5,.5)`，只读当前encoder q/v与当前目标。zero_torque全八轴请求恒零，使用相同目标评分，保留被动响应。上述四种控制共享当前目标、权限、物理保护和配对评价长度；不追加支撑或控制权限。

## 固定顺序、预算与失败处理

固定seed顺序 `[0,1,2]`，seed外层；每seed顺序及完整计划如下。总调用已经包含每trial的100步前缀。

| trial | 前缀调用 | active调用 | 总调用 | 身体RLS更新 |
|---|---:|---:|---:|---:|
| calibration | 100 | 300 | 400 | 300 |
| prediction_low | 100 | 100 | 200 | 0 |
| prediction_full | 100 | 100 | 200 | 0 |
| nominal_mpc | 100 | 200 | 300 | 0 |
| learned_mpc | 100 | 200 | 300 | 0 |
| tuned_pd | 100 | 200 | 300 | 0 |
| zero_torque | 100 | 200 | 300 | 0 |

每seed7trial /2,000控制 /20,000子步 /300RLS；三seed **21trial /6,000控制调用 /60,000子步 /900RLS /120 s模拟时间**。phase总数为prefix2,100/21,000，calibration900/9,000，prediction600/6,000，control2,400/24,000，分别以控制/子步计。

相同权限、目标和控制窗口不代表相同方法总成本：学习法每seed另需400次真实校准，PD不需要这一启动阶段；共同预测是额外评价成本。分别报告各方法启动/校准/控制、全部PD调优及既有肩部C2开发成本，不把本矩阵6,000次均分后声称同总交互预算优势。模拟时间、CPU墙钟与真实动物发育时间分开。

所有active返回端点共享StudyAbort：`abs(q-qref)>=.12 rad` 或 `abs(v)>=1 rad/s`，等值触发，只停止，无纠正动作。prefix只采用原环境保护。study flag、environment_terminated、environment_stop_reason及触发值分别保存；共同发生时环境原因可作主reason，但研究停止不能丢失或伪装为环境终止。

完整20 ms terminal转移允许更新/评分并保留；即使最后计划步触发停止也不completed。partial保存已返回原生状态、当前已知target的原始误差、实际付费子步与努力，不更新、不混入主20 ms预测或tracking RMSE。评分端点、计划端点、缺失数、停止与未完成状态分开；零停止不证明安全或真实制动能力。

calibration失败阻塞依赖它的两条共同prediction和learned_mpc；nominal_mpc、tuned_pd、zero_torque从各自付费前缀独立继续。普通停止或非fatal异常继续既定trial，不补跑；中断、IO或trace写入失败fatal，剩余planned记录blocked。所有env.step尝试、返回、已返回未存行、失败快照及真实预算保留；努力在finally按实际付费子步计账，实际历史缺失则报告下界、未知量与缺失子步，不能填零。

正式物理累计基点 **216,371控制 /2,163,710子步 /9,900RLS**；本批若全部完整则 **222,371 /2,223,710 /10,800**。累计必须按实际执行增加，不以计划替代实际。内部规划、失败规划、离线诊断、审计、合成测试与CPU计算均另列，不冒充物理交互。

## 独立一致性与三个分别输出的门

独立标准库审计按真实j1档案核验：源码commit/clean、原字节ZIP与SHA、协议及PD选择来源、全部派生seed/前缀、原生感觉、qref/方向/限位/目标、实际努力、RLS/P及更新数、冻结参数/MPC/PD、phase/trial/batch实际与失败预算、StudyAbort、partial、异常及日志完整性。不导入采集器或模拟器，不把肩部观测重排成肘部档案。Git blob与本批源码清单均须可核验；历史开发锚点复现不算独立seed。只有一致性通过的科学门才可报告为核验通过。

**模型贡献门（每seed五trial，三seed15trial）**：calibration、prediction_low、prediction_full、nominal_mpc、learned_mpc全部完整，且无study/env stop、异常、非法请求或非有限状态。low及full的learned速度RMSE分别逐seed `<=0.8*nominal`；200步learned tracking逐seed**严格小于**nominal，三seed原始tracking RMSE算术均值至少降低20%。此门不要求PD或zero完整；它们失败不能抹去独立完整的同MPC比较。

**经典PD比较门（每seed六trial，三seed18trial）**：模型贡献门通过，且三seed的tuned_pd均完整，无study/env stop、异常、非法请求或非有限状态。learned tracking逐seed `<=PD`；三seed原始RMSE算术均值至少低5%；control active实际绝对努力、平方努力各自的三seed算术均值 `<=1.05*PD` 对应均值。若失败，保留PD与learned全部真实误差和努力，不能声称超越强基线。努力门是力矩代理条件，不能称风险下降。

**七trial完整矩阵门（21trial）**：三seed全部七trial完整且无study/env stop、异常、非法请求或非有限状态，包含zero_torque。它与科学优势门独立输出；完整矩阵不自动意味着模型优势，局部门通过也不能掩盖其他trial失败。

零分母的百分比改善保持未定义。速度门使用上述乘法；nominal速度误差0且learned也0可以满足数值门，但不能报告降低20%。tracking均值分母0时均值改善门失败；严格逐seedtracking不以epsilon替代。努力PD=0只允许learned=0。所有门沿用[单肩冻结协议](LOCAL_FROZEN_VALIDATION_PROTOCOL.md)原阈值，不事后改门、追加seed或剔除失败；负结果同样归档。

## 完整诊断、证据边界与接续

共同low/full、校准in-sample、各控制自身及配对轨迹均报告1/5/15/50步q/v端点及路径RMSE，窗口完整/排除/terminal数，block/幅度/切换/保持分箱。未来日志请求仅作离线条件输入，不能在线预知；自由递推不能回灌未来真实状态。完整active输入的q/v支持包络、域外/并集比例与nearest q距离均报；包络不称安全集或准确性保证，闭环自身一步退化与长时域失败不能被共同预测改善遮盖。

报告全身体full/prefix/calibration/prediction/control的子步接触力峰/冲量、动能、最深穿透、八关节端点速度、软限位/屏蔽、饱和、回退及停止。两个目标段与各自最后20个计划端点（active80–99、180–199）的tracking RMSE、平均有符号/最大绝对误差均报。尾窗计划分母20，只有完整20 ms转移参与评分；返回/完整/缺失数和未完成标记分别保留，末端停止不能称无停止窗口。尾窗仅为描述指标，不改收益门；共同prefix峰不掩盖active风险。

依赖精确版本、Python/CPU后端、GPU=null、源commit/dirty、请求/实际努力、所有原始逐seed指标、模型指纹、异常及完整数据SHA清单保留；计算计时范围公开。当前本批尚未执行，不预先声称通过。三seed开发结果只支持冻结协议下的局部开发结论，不证明未见seed/动力学泛化、风险下降、翻身、站立、行走或真机能力。

先完成实现/合成检查、协议及独立审计并提交推送；从clean一次正式执行，独立核验并归档全部成功/失败、更新累计账本，检查提交推送后继续肩—肘协调、未知动力学与成熟门控，不以本批结果结束[持续目标](CONTINUOUS_EXECUTION_PLAN.md)。若后续修订，另编号协议并冻结新的未见评价bank，不复用本批或已见20/21/22声称独立最终验证。

```powershell
$env:PYTHONPATH = 'src'
external/cpu_physics_env/Scripts/python.exe -m developmental_physics.local_frozen_validation `
  --suite elbow_development --output external/elbow_body_20261011_development `
  --protocol docs/ELBOW_BODY_DEVELOPMENT_PROTOCOL.md
```

相关：[左肘PD冻结协议](ELBOW_PD_DEVELOPMENT_PROTOCOL.md)、[左肘PD开发证据](ELBOW_PD_DEVELOPMENT_RESULTS.md)、[原时序配方](LOCAL_COVERAGE_ABLATION_PROTOCOL.md)、[逐关节选择](JOINT_PROBE_PROTOCOL.md)。
