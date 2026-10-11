# T：固定 Q 初始化的有限梯度信赖半径 / Armijo 数值修订

本协议只冻结一个新开发候选 T。S 首次执行在全部 seed 的 objective3 出现 quadratic21 非有限值；初始及 SciPy 重复初始有限，callback0，未产生 S 候选。T 据此只修订数值试探过程，不把 S 的失败、初始快照或早期部分误差当成成功模型，不从 S 的参数恢复或继续优化。T 每 seed 只从原冻结 Q 初始化一次；不是补跑 S。

协议与源码先冻结，随后由独立运行入口在干净精确提交上首执行一次。作者准备阶段不 import 或执行 T，不调用模型、objective、梯度或 scientific payload；只做静态语法、字节身份和本协议链接检查。第一次 synthetic self-check 与正式离线执行各自留存成本和失败。禁止物理、拟合超参数搜索、新特征、模型重构、任务教师和预训练策略。

## 不变的科学核心

T 动态导入并复用 byte-pinned S 源码的 training population、Torch forward/autograd 核心和固定运行时身份。S 源码 SHA256 为 22097d00bbb884e29b9d0e6cd060b53e0448beb72321685c11e7942762acfe7e，协议为 ce5e8f0d3d6b5580406dd73a5b6f8a9928f56c5b13ad4056d1d05145659d944d。Q/R/K/D 及原始共享输入仍由原 pins 绑定。本轮不重做已验证 mapping 或旧 gradient fixture。

保持原 Q 公共 phi50、原生 x22 全状态闭合、原 prior、exact 起点 guard、已知请求 clipping 和过去端点推进；预测过程中不裁剪状态，不平滑 guard，不用 straight-through 或 teacher forcing。qref、关节限位及经典初始化先验继续披露。只有 q0/q1 的 50×2 权重 U 可变，另外 20 个输出头的 50×20 权重完全冻结，仍保留其递推状态的梯度路径。模型不读未来实际力矩、接触力、动能、真实动力学、root quaternion 或不存在的 native orientation。

每 seed 的 C sparse calibration step100–499 仍提供 400 连续已保存训练转移。合法连续 H1/H2/H5/H15 window 分别为 400/399/396/386；总 1,581 window、3,162 terminal q label uses、每次完整 objective 8,968 transition。800 个独立 q scalar label/seed 的唯一端点池不变；terminal label 仅进入损失，不进入递推状态或控制。

损失严格不变：

    L(U) = .25 * sum_h mean_origins_and_two_axes(((q_pred_end-q_actual_end)/.12)^2)
           + .01 * sum((U-UQ)^2)

每次返回有限的 objective 都计算真实 forward 和全部 100 个权重的真实 autograd gradient。只要实际 numerical 非有限使 forward/gradient 不能返回，即保存已付费 partial 及明确缺失值，不用伪造 loss、零 gradient 或有限替代值。

## 唯一数值优化器

方向 d = -gradient / ||gradient||_2；每个 accepted iteration 重新从 alpha=1e-3 开始。该 alpha 是 L2 数值信赖半径，是公开的纯数值先验，不是新的物理保护或科学门。Armijo c=1e-4，beta=.5，每个 iteration 最多 10 次 trial evaluation。仅当真实 finite trial loss <= 当前 accepted loss + c*alpha*(gradient·d)，才能申请 accepted checkpoint 注册；每个 trial 都有真实 loss/gradient 计算的费用，拒绝后 alpha 减半。

单 seed 最多 30 个 accepted update，硬上限 100 次 objective calculation，初始、有限拒绝、非有限拒绝及失败 partial 均计入。120s 是 objective 入口/出口、checkpoint 入口/持久化后注册、optimizer 出口的边界检查预算；没有抢占，不宣称硬墙时间限制。实际墙时、CPU时、overrun、各阶段 attempts/returns/failures、checkpoint 持久化字节及已有全部学习成本分别保留。

不添加 gtol 或经验收敛容差。真实 gradient L2 norm 恰为 0 时停止；若是 initial0 则没有 T update，明确失败、无候选。30 accepted limit 是非收敛预算停止；允许发布既有真实 T accepted update。没有 restarts、不同 alpha 扫描、best-loss 选取或最终 trial 替代。

## 非有限、失败与选择

专用 NonFiniteTrial 只识别数值非有限。S kernel 抛出的 ValueError 仅在 type 恰为 ValueError 且 message 完全匹配源码列出的计算结果 nonfinite_tensor 名称时转换；trial 参数/loss/gradient/norm 的实际非有限同样归此类。固定输入 state/history/request/qref/frozen weights 的非有限、shape、来源绑定、IO、missing gradient、内部错误及其他 ValueError 仍是 fatal fit failure，禁止 catch-all 数值拒绝。非预算结构或内部错误即使发生在时间边界外，也不得改写成预算停止或发布已有 accepted 模型。

每个 numerical trial 非有限均拒绝并保存 trial 参数、实际可得 loss/gradient/norm、失败类型、原因、源 objective、partial rollout 和实际成本；减少 alpha 后最多继续本 iteration 的既定 10 次。initial 非有限没有可用方向，直接失败。10 次均拒绝是 line-search stalled 的非预算失败，整个 seed 无候选，即使此前有 accepted checkpoint，也只保留为证据。其他非预算异常同样无候选。

保存 initial iteration0 仅作证据，不计 accepted_updates、不赋值 last、不发布 Q 为 T。有限 Armijo 通过的 trial 先持久化 checkpoint，再检查注册边界。持久化期间跨 120s 的新 checkpoint 保留为证据，不能升级 last；此前已注册 accepted update 可以在预算停止时发布。selected 只取最后注册的真实 T accepted update，必须 >=1；预算在零更新时终止也无候选。所有已发布 50×22 权重独立要求 finite，冻结 20 heads 逐项保持不变。

所有 JSON payload（包括 completed run 中被拒绝的非有限 trial）、checkpoint evidence 和紧凑 stdout 采用递归显式 NaN/+Infinity/-Infinity 标记，strict JSON 禁用裸非有限值。编码保存证据，不修正候选或模型数值。stdout 不输出参数或大数组。

## 不变的比较与证据边界

仍用原 C prediction 的 fixed origins 及 H1/H2/H5/H15，比较 T22/Q22/K22/D11，固定 4,572 requested prediction records。Q 仅描述；原 S 对 K、D 的 dual_gate 数学、完整 fixed-count 优先门和阈值原样转写为 T 名称，未放宽或追认。缺候选、window 不可用及停止均保留，禁止部分 RMSE 排名或通过减少步数宣称效率。每个 seed 拟合失败后继续保存请求的完整评估 population；T unavailable，原 Q/K/D 仍按原规则评估。

Q/K/D 恢复前后指纹必须不变。保留 Q 历史 fitting/标签成本；S 仅额外读取 root manifest、raw manifest、raw run 三个已固定 metadata JSON，核对 S failed/self_check=false/clean sourcefcab231a511996de83e28d93ce6749326b38308f、源字节、manifest绑定和 C/D/K/Q 共享输入身份，再保留 frozen_S_original_cost。禁止读取 S parameters/predictions、恢复 S 模型或重算 S 数学。三个 metadata 文件的 bytes/hash 直接固定在 T 源码，不重新扫描目录。

不新增物理或在线/离线 RLS 更新，不重新拟合 Q/K/D，不重读已揭晓物理以调试 gate。T 成功与否仅为 seen-C 开发证据；scientific_adoption、c4_scientific_validation、c5_scientific_dependency_released 固定 false。C4 完整控制、C5 科学适应、C6/C7 仍未验收。

## 首次新 fixture 与运行接口

self-check 只运行紧凑 synthetic optimizer fixture：有限 Armijo 回退后接受、非有限拒绝后较小 trial 接受、10拒绝及结构错误的无候选隔离、call/time/post-persistence 边界下零更新与真实 accepted update 的区别、exact-zero initial 隔离。不调用 S/Q 的旧映射、gradient fixture 或任何科学数据。每 fixture 保存完整 trial/checkpoint/result evidence；自检通过不证明科学方法通过。

接口：

    python scripts/develop_guard_trust_position_transition.py --repo . --output <new-directory> --self-check
    python scripts/develop_guard_trust_position_transition.py --repo . --output <new-directory> --source-commit <clean-exact-40hex>

两条命令均必须使用从不存在的新 output directory；源路径、协议、所有 frozen helper 和 inputs 绑定先验证。正式首执行从每 seed 原 Q 开始一次，不对任何失败 seed 补跑。运行和封存由 root 的 first-only helper 管理，准备、self-check、正式 objective/gradient、评估、序列化、封存和薄 saved-output check 分账。

相关冻结边界见 [S 协议](GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md)、[Q 协议](GUARD_QUADRATIC_NATIVE_TRANSITION_DEVELOPMENT_PROTOCOL.md) 及 [持续阶段账本](CONTINUOUS_EXECUTION_PLAN.md)。

