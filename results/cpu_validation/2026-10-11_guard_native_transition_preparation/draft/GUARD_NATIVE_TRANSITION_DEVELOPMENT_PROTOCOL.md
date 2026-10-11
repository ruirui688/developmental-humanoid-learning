# K：固定完整原生状态闭合转移开发协议

本协议先于首次实际输入读取、模型调用与拟合冻结。脚本正式位置为
`scripts/develop_guard_native_transition.py`，本协议正式位置为
`docs/GUARD_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md`。准备草稿置于
`external/c4_native_transition_staging/`；准备阶段不读真实 trace/snapshot、不拟合、不预测、不新增物理。

K 是新的开发子门。表示与转移模型同时改变，不能把任何改善归因于 IMU；不使用 J 分数选择任何参数。
不追认 D 旧独立预测门。无论本开发门通过与否，`scientific_adoption=false`、C4 科学验收及 C5 依赖解除均为 false。
通过后仍需新留出和相同权限的匹配完整控制，不能声称安全、效率、适应或全身技能。

## 固定输入与权限

仅使用 C 的 seed 0/1/2 `calibration_sparse`（每 seed 400 个完整主动区间）拟合，
仅在 C 公共 `prediction`（每 seed 100 个主动区间）评分。C 前缀仅初始化 qref 与连续历史。
不读取 G、审计、旧 rollout/update 日志或 J 结果。读取 C trace 的已保存 JSON 行时，
只消费身份、phase、step、transition ID、原生 before/after、requested torque、完整子步数和停止标志；
不消费 saved predictions、model_update、实际力矩、接触、能量、quaternion 或隐藏动力学。

C 原始 source commit：`5ea8df42b09588845760daf0dc1f270aef2a87f1`。
D 原始 source commit：`f7710c7b048dccab3e436d1fa16432f881a35992`。
脚本固定六个 SHA-256 输入 pins，验证 C flat raw manifest、metadata 的正式身份和 100/400/100 长度，
并验证 D root/raw manifest 与 diagnostics 的绑定。D diagnostics 只恢复每 seed 的 sparse11
`lag11_final_snapshot`，不读其它记录的结果或选择其它模型。

八维 qref **只来自本 seed C sparse calibration trial 的完整 100 步前缀最后 after endpoint**（step99），
并保存该来源 transition ID；要求全部前缀按 0…99 连续、10 子步且无停止，所有八轴 q/v 和六 IMU 通道有限。
不得补零、不取预测未来或其它 trial 的 qref。预测 trial 的前缀必须与该八轴 qref 一致。
两轴公开 ranges 来自 D 已冻结 snapshot 的 public guard mapping；不查询仿真器。
其 qref 前两轴须与 calibration 八维 qref 一致。

完整原生状态顺序固定为
`x22=[q0-qref0,…,q7-qref7,v0,…,v7,gyro_x,gyro_y,gyro_z,accel_x/9.81,accel_y/9.81,accel_z/9.81]`。
每一步特征顺序为
`features29=[x22,G0,G1,h(G0),h(G1),1,v0-previous_v0,v1-previous_v1]`，
`h(G)=sign(G)*max(abs(G)-.25,0)`。
G 使用纯 KnownAngleGuard：已知当前 q 与请求，限幅 .5 Nm、距公开限位 .03 rad 的向外请求归零；
不夹原生 q，零请求不标 blocked。G 是当前起点映射，不是未来实际力矩。

previous_v 必须由同 trial 的两个连续过去完整原生端点建立；
step100 的 current/previous 分别来自 step99/98 after。要求 past 与 current 连续并且 previous after 等于 current before。
未知、部分、缺行、停止后或跨 trial 历史不可用，绝不补零。

## 固定 prior 与学习

cold22 与 learned22 共享同一 prior：八轴 `q_next=q+.02*v_current`；
前两轴 `v_next=v+.02*G`，其余六轴 v 保持；gyro 与归一化 acceleration 保持。
q 的 prior 使用 current v，不能用 predicted next v 替换。

每 seed 构造 `Phi(400,29)` 与 `Ydelta(400,22)=observed_x_next-prior_x_next`。
固定普通 float64 batch ridge，`W=solve(Phi.T@Phi+.01*I29, Phi.T@Ydelta)`，
一次共享 29×29、22 RHS solve；所有列（包括常数）同样正则化。
无归一化/白化/截断、额外特征、超参数搜索或 RLS；learned22=`prior+features29@W`。
每 seed 8,800 scalar 标签、638 系数；共 3 solves /26,400 scalar 标签 /1,914 系数。
这属于复用已付费 C 数据的新增非 RLS 离线学习，与历史在线/离线 RLS 更新分列，物理为零。
保存每个设计、delta 标签、prior、normal/cross 矩阵、权重、训练 transition IDs 与参数指纹。
缺少完整固定 400 或非有限算术为该 seed 拟合失败，不缩减数据补做或重新求解。

## 固定闭合预测与评分

H 固定 `(1,2,5,15)`，每 trial 全部完整窗口起点分别为 `(100,99,96,86)`。
每 horizon 独立从该 origin 的当前完整原生状态和合法历史初始化，分别 rollout cold22、learned22、D11；
不跨 horizon 重用预测，不因为失败减少固定 origin 分母。
K 两组随后闭合生成全部八轴与六 IMU 状态。每次递归后 previous_v 更新为 **old predicted current v**；
D11 同样只递归自己的两轴 q/v 与历史，不接受 K 状态或未来实际状态。

未来已保存 requested sequences 是离线条件输入，只切出对应窗口请求并逐步送入。
不重建真实未来 veto，不声称控制部署时能够预知未来 veto 决策。
未来真实原生状态只在终端评分使用；连续性检查决定窗口是否可用，不注入预测状态。
完整终止区间仍可作为最后评分端点，source stop 后不可继续窗口。

逐 origin/horizon/predictor 保存请求 transition IDs、起点历史 IDs、完整预测路径、可用/失败原因、终端误差。
两轴 q/v 用各方法固定完整分母的 RMSE、MAE、bias；K 两组另报告其余六轴与 gyro/归一化 acceleration 的全部 22 通道。
任何方法缺样则其相应完整比较不可评估，不能用可用子集排名。

新开发门仅比较 learned22 与恢复 D11 的两轴：

- 所有 seed、H、三方法都有固定 `(100,99,96,86)` 个可用终端；源 prediction 每 seed 正好 100 个主动行。
- H1：两轴 v 每 seed 严格改善；每轴三个 seed 算术平均相对 RMSE 改善 ≥20%。
- H15：两轴 q 每 seed 严格改善且每轴平均改善 ≥20%；两轴 v 每 seed 不劣。
- H2/H5：两轴 q 和 v 每 seed 均不劣。

比较分母 D11 RMSE 为零或非有限则相关相对改善未定义，门不可评估而不是通过。
不根据 K 输出改变门、参数、seed、窗口或任务。

## 首次运行、故障与计算计账

正式运行须指定精确 clean HEAD，脚本/protocol 及纯 helper bytes 与该 commit 相同；
helper 列表固定在脚本中，不导入 MuJoCo。只接受新 output 目录，存在则拒绝覆盖，不补跑到成功。
推荐正式命令（SOURCE_COMMIT 替换为真实冻结 commit）：

```powershell
python scripts/develop_guard_native_transition.py --repo . --source-commit SOURCE_COMMIT --output NEW_OUTPUT
```

D 恢复只复制匹配 sparse11 的 2×11 系数、2×11×11 covariance 和400/800更新计数，冻结 trainable=false。
完整 snapshot 与改变 trainable 后的原件一致才返回；逐 seed 恢复 attempt/return 分列，运行前后参数指纹一致。
D 预测重新计算，pair/scalar attempts/returns/failures 按真实已执行调用计账。
K transition、feature、prior、22头残差调用、fit标签/矩阵/solve/发布计数分列；不在所有 seed 成功后补加总计。
预计无故障：每方法每 seed `100×1+99×2+96×5+86×15=2068` 步；
全 seed 每方法6204步，D为6204 pair /12408 scalar头，三方法共3429个 origin/predictor记录。
cold 与 learned 的 prior 和 feature 构造也逐次记录，不能把离线递归称为物理交互。

`run.json` 保存输入真实 reads/hash、冻结 source 绑定、版本、源 C 依赖、耗时与计算分类；
`parameters.json`、`predictions.jsonl`、`metrics.json`、`unavailable.json` 及 manifest 保存可复核原件。
首次失败保留已经产生的参数、预测路径、停止/不可用记录和所有已发生开销；
若 source verifier 未返回，明记 source unknown；已经读过的 pins保留，未返回读取记录的状态明记 unknown。
fit/rollout 的可计数失败不重试；致命异常保存 failure 和 failed manifest 后抛出。
准备工程检查只有经 parent 确认后的必要新合成分支与一次纯合成多输出 ridge数学检查；不重做 J 检查。
