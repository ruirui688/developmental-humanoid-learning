# PAR1：相同仿真状态的有限动作响应诊断

状态：**事前有限协议，尚未执行。** 只开放下述一个诊断，不开放控制候选或学习分支。最终源码、输入身份、必要新合成检查与此协议须先冻结到干净提交，再首次执行一次；任何失败保留，不能补跑到成功。

## 1. 问题与证据边界

EF1D 完整保存 2,400 H1 模型记录 / 1,200 配对 origin。learned 的 1,200 条记录覆盖六个来源组，其最小范数误差映射在原局部盒内可评数均为 0。这个模型内部事实不能证明真实动作 Jacobian 错误，也不说明换一个 nullspace 解就会成功。

PAR1 仅回答：在原双关节域的相同当前仿真状态下，对已知请求作固定小幅单轴干预，实际下一速度的有限变化与冻结 cold/learned 模型的有效输入响应是否相符。它使用新的动作干预，不重算旧预测、旧 RMSE、科学门或已完成的来源审计。三 seed 已用于开发，**本批不是新留出、控制优势或样本效率验收**。

完整状态反事实复制是仿真诊断额外资源，必须计费。它不代表真实机器人能够复位到相同微观状态，也不能把 fork 响应当成无成本学习样本。

## 2. 固定来源与原生信息边界

唯一模型来源是首次 EF1B 的 `raw/models.json` 原件：**60,924 bytes / SHA256 `3cfbd871c275a8f5d8a07615a239ee9e8192b5e93dcf35104cf61a01f6a6a992`**，来源 EF1B 执行提交 `f9f5007`，模型形成源 FR4A 提交 `f4fca3f`。冻结 manifest 须写明原件实际路径和完整提交 SHA；路径变化不能替代字节身份。六个 seed×cold/learned 模型共 108 个 theta scalar，只恢复，不 fit、不更新。模型结构必须为原冻结 2 ms `coupled_hinge9`，公开范围、qref 与本批 fresh 来源精确相同，否则全批停止。

部署模型的可用输入仍只有原生双轴 q/v、已知请求、公开关节范围和固定参数。完整 `MjData`、root/接触、积分内部量和 Python 环境状态仅由 evaluator 用于复制与资格核验；不进入模型、控制目标、特征选择、拟合或标签修订。不能以特权状态帮助选择响应较好的 origin、动作侧或 seed。

## 3. 新来源轨迹与固定 population

开发 seed 固定为 **8101、8102、8103**，各执行一条 fresh 公共 PD 来源：

1. 原自由 root/仰卧身体、底层保护、原 2 ms 物理与原感觉条件不变；每 seed 构造一次源环境并显式 reset 一次，隐含构造/reset/forward 另计。
2. 双轴已知请求均为 0 的前缀恰好 1,000 步。`qref` 只取第 1,000 步完成后的 fresh native 位置前两轴，必须与该 seed 两个冻结模型的 qref 逐项精确相同；公开范围也精确匹配。不得用旧 qref 覆盖 fresh 状态。
3. active 恰好 2,000 步：A/B 各 1,000 步，目标分别为 `qref + direction*.04` 与 `qref + direction*.08` rad。direction 沿用原公开 `direction_targets` 规则：比较正/负公开限位余量，选较大一侧，平局选正；不扫描符号或目标。目标须满足原公开合法性要求。
4. 每个 active 步仅按当前目标形成公共双轴 PD64/Kd4 原请求，随后一次公共 ±.5 Nm clip，记为 `u0`；没有保持补偿、任务教师、模型选动作或切换预览。安全与底层 guard 仍执行原规则。

三条完整来源固定 **9,000 control / 9,000 physics substep**。干预 origin 为每 seed 的 active index **0、500、1000、1500**，共 12 个 origin。index k 明确指源第 k 个 active 动作执行前的状态；当前目标按 k 的 A/B 阶段确定，不读取下一步目标。不能按响应强弱更换 origin。

每个 origin 的计划人口固定：一个同 `u0` 资格 fork，加四个动作侧，顺序为 **axis0 −.125、axis0 +.125、axis1 −.125、axis1 +.125 Nm**。共 12 个资格 fork / 48 个计划侧。侧请求 `u_side=u0+delta*e_axis`：如果任何请求分量超出原 ±.5 Nm 权限，记录权限外 NA，**不 clip、不 step、不替换侧**。权限内侧一律执行，包括当前 angle guard 阻断的侧，不按投影或实际结果筛选。权限外 NA 是完整计划人口中的固定类型，不是失踪记录。

## 4. 完整复制资格与执行顺序

每个 origin 按以下顺序执行，基准 endpoint 只由一次新源动作获得，不再付费重做：

1. 在原源动作前保全完整 pre `MjData`，使用 **`mj_copyData`**，同时保全 evaluator 的 Python 上一请求、step_id、physics_steps、reset 状态/计数、terminated 与 reason 状态。至少包括实际环境对下一步有影响的全部 Python 状态；最终 runner 明列这些字段。不用只写回 qpos/qvel 的近似 clone。
2. 原 source 对 `u0` 执行一完整 2 ms 步，保存实际 base endpoint、完整 `mjSTATE_INTEGRATION` 与 Python endpoint 状态。原 source 的真实 endpoint/data 对象与状态始终保留。
3. 从原 pre 完整数据复制同 `u0` 资格 fork：**执行前** `mjSTATE_INTEGRATION` 与 Python 状态必须与 pre 精确相同；执行同一动作后，其 integration vector、原生 q/v 和 Python endpoint 状态必须与新 source base endpoint 精确相同。采用逐项精确比较，不用误差容差；非有限不视为相等。复制 API 不可用或资格失败时不降级、不继续动作侧。
4. 资格通过后，各权限内动作侧都独立从同一原 pre 完整复制，执行前作同样的精确 pre 核验，然后只 step 一次。每侧之后恢复/保留源真实 endpoint 及其 Python 状态，后续源 PD 轨迹不能继承 fork 请求、计数或失败状态。

opaque state 只用于 evaluator 的复制和一致性判断，不从其中生成新的控制信息。若 runner 临时切换 wrapper 的 data/状态，必须保全并恢复真实 source endpoint；失败时仍保留原 source、当前分支和已付费费用。全局累计费用不能随着 Python 状态恢复而回退。

最多 **60 个 stepped fork**：12 个资格和 48 个合法侧，故整批上限 **9,060 control / 9,060 substep**。pre 保全本身不是 fork step：12 次 pre 快照 copy 与最多 60 次 fork copy 各自另计，不把 `mj_copyData`、data 分配、构造、reset、forward 或状态提取费用隐藏在这 60 次内。不得多步试探、重新复位或重新复制后补跑资格。

## 5. 有限响应与唯一模型代数

对每个权限内且完整的动作侧，实际有限响应固定为：

`actual_delta_v = actual_side_endpoint_v - actual_base_endpoint_v`。

base 与 side 来自相同原 pre 状态。它是 ±.125 Nm 的有限干预效应；跨 guard/hinge 分支单列，即使未跨分支也不能默认它是真实微分 Jacobian。guard-blocked 的实际零/弱响应同样保留。

两种冻结模型仅用公开当前 q 对 base/side 请求分别计算原 `G` 与 signed hinge `h(G)=sign(G)*max(abs(G)-.25,0)`。九列中相同 q/v/常数贡献抵消，直接代数为：

`model_delta_v = B*(G_side-G_base) + H*(h_side-h_base)`，

`response_residual = model_delta_v - actual_delta_v`，

其中 `B=theta[:,4:6]`、`H=theta[:,6:8]`。theta 已是 2 ms 下一速度系数，**不再乘 dt**。不调用 `model.predict`，不构造虚拟运动参考，不 rollout、RLS、拟合或反算新控制请求。

理想感觉的弱信号标记只采用固定浮点规则：两 head 共用 `tol=128*float64_eps*max(1,sum(abs(v_side))+sum(abs(v_base)))`；各轴 `abs(actual_delta_v_i)<=tol` 为数值弱，整对两轴都弱才标 pair weak。它只说明理想测量下的数值可辨识性，不是噪声门、物理效果阈值或新科学成功标准。弱信号不触发增大刺激、延长 horizon、增加 sample 或重跑。

完整人口保存实际/两模型响应、残差、原始已知请求、G/h 差、guard 状态、触及/跨越分支与权限 NA。分量符号和已有响应的描述可以报告；不新增 SVD/逆解/最优化，不为漂亮 sign/rank 筛选人口或扩大代数范围。

## 6. 停止、账本与交付

沿用原 StudyAbort 逻辑与激活条件：位置偏离 **.12 rad**、速度 **1 rad/s**，原底层限位及每个 2 ms 子步检查均不变。source/base、资格或任一侧出现技术异常、来源/状态身份不符、StudyAbort 或环境 stop，立即记录首错并**停止全批**，不执行剩余 seed/origin/侧。保留停止前完整/部分 source 与 fork，缺失计划人口显式记为 not_executed；不得用部分人口排名或把提前停止解释成节省样本。只有事前规定的权限外 NA 可以在完整批次中存在。

预算与费用分列：

| 项目 | 固定人口或上限 |
|---|---:|
| source control / substep | 9,000 / 9,000 |
| origin / 同 u 资格 fork | 12 / 12 |
| 计划动作侧 / stepped side | 48 / 最多 48 |
| 总 control / substep | 各最多 9,060 |
| 冻结 theta scalar 读取 | 108 |
| 实际有限响应 scalar 用途 | 最多 96 |
| 两模型响应代数 pair / scalar 输出 | 最多 96 / 192 |
| fit / RLS / model.predict / 旧数学或旧 audit 执行 | 全部 0 |

base endpoint 的复用、side endpoint 读取、96 个响应差的两端点操作、B/H 系数复用、公开 G/h、残差与浮点标记的实际运算另计，不能把 96 个响应输出误写成全部标量访问。source 构造/reset/forward、12 个 pre 快照、各 fork 的 data 分配/复制/pre 资格、同 u endpoint 资格及状态读写都单列 attempt/return/failure 和实际付费步骤。必要新合成检查属于准备账，不混入本批正式人口。

保存首次源码 commit、协议/模型 pin、依赖版本、CPU、完整配置/seed、stdio、原始 source/fork 记录、全部 NA/停止、逐 seed 结果与费用 manifest；输出目录和各原件首次写入，拒绝覆盖，不自动重试。最终路径/schema 由冻结 runner 明列，不能遗漏任何计划人口与首错。

此前累计 **505,297 control / 2,784,970 substep**，online118,452+offline7,200=**125,652 scalar 更新**；本批仅按实际新增 source/fork 步骤累计，更新数不变，旧计算费用保持。不重算或放宽 C4 原门，不拿开发 seed 当新最终留出。无新的 scientific gate；五 science flags 全 false，C4及C5–C7仍未验收，持续目标 active。首次结果核验、提交和推送后继续依据本批有限结论推进，诊断本身不自动授权另一控制候选。
