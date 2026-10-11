# C4 G：固定 PD 反馈尾的单项控制结构开发

前瞻开发草稿，代码、独立审计和来源尚待冻结提交；当前不放行物理。
本候选在 E 失败和 F 保存描述之后选择，不将这些已见开发数据称为新留出。

## 问题与唯一改动

E 的学习组全部在104active肘速度停止；其一步预测在PD完整轨迹上较好、
在自身控制轨迹上较差。F没有识别遗漏上下文的因果，学习trial目标段B仅4点。
继续增加模型维度没有充分依据；先检验一个控制结构假设：H15常向量预测
改为第一步自由请求、其后有固定反馈的预测尾，是否帮助完整执行原任务？

只改变预测尾动作规则。h0为原81个网格候选b之一；h1..14为
`u_h=clip(Kp*(target_t-predicted_q_h)-Kd*predicted_v_h,-.5,.5)`，
`Kp=(64,64), Kd=(0,4)`。每candidate独立初始化和递推自身q/v/history，
模型先预测、previous_v再更新为旧current_v；只消费当前target，不预览切换。
实际只执行h0，20ms后重新观察并规划；不保证重规划后的未来动作与PD尾相同。

PD增益来自已公开的九候选×三seed开发，是先验和经典控制能力，不能称作
本轮身体模型学得或隐藏为任务教师。两MPC组共享该尾，PDbaseline不改。
没有人体动作、预训练策略、教师轨迹、gain调优或额外模型拟合。

保留H15、每轴9候选、原forecast位置.15rad/速度1.5rad/s、target bounds、
原position/velocity/effort/change权重、tie与zero fallback。stage effort按
该stage请求u_h计算；change只计算h0的b相对上一实际已知请求。forecast与
真实study stop .12rad/1rad/s的不一致继续披露，本轮不同时修改它来凑完整。

## 固定矩阵与来源

seed0/1/2依次cold11、learned_sparse11、PDselected、zero共12trial。
各fresh仰卧baseline，100零prefix+200active；肩肘最终权限各.5Nm，
其他六轴请求0；`.04→.08rad`目标、逐子步guard与真实study stop不改。
每组完整200active才eligible；环境停止、研究停止、异常、blocked分别公开，
停止前RMSE不参与方法排名，不补跑到成功或改已揭晓旧验收标准。

学习组仅恢复原D该seed完整sparse11 snapshot（400双轴更新的原final状态）
并冻结，cold11保持同prior/qref/ranges与lag0。D原calibration、离线拟合与
PD开发费用不归零；G不重放拟合，不用PD轨迹训练，不读取F分层作为模型输入。
fresh prefix必须精确匹配D绑定qref/public ranges/物理条件；失配保存付费prefix，
不自动修配。所有模型、planner、gain和gate全程冻结。

history来自同trial连续完整过去两个native endpoint；active0用prefix98/99。
不跨trial、补零或读未来实际状态。四组所有active起点都在动作返回前用
cold11与learned_sparse11独立一步诊断，当前已知final requested torque为输入；
未来actual/特权接触和qpos/qvel仅供离线风险核查，不进入部署模型。

源ZIP保存新planner、collector、独立auditor、独立数学支持、原身体/guard/
物理/asset/config源码、正式协议及D/PD来源链；working bytes必须等于clean
committed bytes。F/E结果仅是公开假设选择依据，不重跑它们的物理或审计。

## 冻结开发判据

沿用E的四键与完整优先定义，结果仍仅是新开发控制子假设：

- `control_hypothesis`：cold11与learned_sparse11全部seed完整200active且实际
  effort完整才evaluated。每seed joint/两axis RMSE严格降低；逐seed原joint
  RMSE算术均值改善≥20%，每axis的原均值改善也≥20%；实际absolute/squared
  effort两轴合计各自均值均≤cold11的1.05倍。
- `pd_reference`：control_hypothesis已passed，PD与学习组全seed完整、实际
  effort完整；每seed joint/axis不劣于PD，joint原均值改善≥5%，两种实际
  effort各自均值均≤PD的1.05倍。不能用控制子门取代旧独立预测门。
- `matrix_complete`：12trial全部completed、原200active及2000子步完整。
- `c4_scientific_validation`固定evaluated=false/passed=false：D所选sparse11
  共同脉冲预测未过旧20%门，G仅开发控制结构；不因此解除C5依赖。

不pooled seed端点、不以prefix稀释active tracking；完整与部分风险、请求/
实际努力、饱和、动能与冲击/穿透全部逐seed报告。tracking baseline均值0时
不产生百分比优势；effort baseline0时仅candidate也0才不增加。zero全报但
没有新zero采用门。不额外事后加权或新增风险采用门。

## 上限与实际费用

| 上限 | 量 |
|---|---:|
| 新trial | 12 |
| 控制调用 / 物理子步 | 3600 / 36000 |
| 计账prefix | 1200 / 12000 |
| 模型/策略/gain/gate更新 | 0 |
| 独立诊断pair / scalar预测 | 4800 / 9600 |
| MPC规划pair / scalar预测 | 1458000 / 2916000 |
| 首步candidate请求评估 | 97200 |
| 反馈尾向量请求评估 | 1360800 |

每完整decision保留81个candidate的原请求/成本/reason/实际预测attempts，
selected decision新增逐stage `trajectory_requested_torque`，与q/v轨迹对齐。
独立auditor重建全部candidate和selected tail；不要求在线保存所有candidate
H15请求来扩大日志。完整decision的first为81，tail为各candidate
`max(pair_prediction_attempts-1,0)`之和；包含拒绝预测的尾stage。
无完整decision的planning异常、record缺失或_tail_request自身异常，actual
尾计账为unknown或已知总量下界，绝不写成0。异常通知/返回未写端点的保存
decision去重；动作物理失败之前已经完成的规划仍计费。预测attempt/scalar
未知下界、部分物理、未返回/未保存、缺失actual effort分别公开。

clone、来源读取/解压、snapshot/hash、guard、tail反馈与独立audit均为非零
计算，分开报告wall/CPU与实际字节，0更新不表示0计算。正式物理累计基点
249662/2496620；在线22452+离线7200=29652scalar计算，不因新候选归零。

## 工程与首次执行

planner预期`src/developmental_physics/pd_tail_pair_mpc.py`；collector预期
`src/developmental_physics/pd_tail_control_development.py`；独立标准库入口预期
`scripts/audit_guard_pd_tail_control.py`。新suite为`pd_tail_control_development`。
既有E恢复/原生history/支付/failure主体仅作来源/API/AST检查；已过5尾数学、
E小fixture和F统计不重复。只做新增wire、独立tail数学和异常账必要小检查。
formal整个MPCConfig保持默认，工程H1/H2仅用于必要新分支人工检查。

代码与检查原件封口、正式协议及来源清单提交推送后，从clean源码首次物理
一次、首次独立audit一次、保存指标汇总一次，再封口/提交/推送。若仍失败，
保留有依据修订；若控制子门通过，仍另需冻结新独立预测/必要身体模型开发及
完整C4验收。不停止持续目标，不将G局部通过称为全身技能、风险或真机成功。
