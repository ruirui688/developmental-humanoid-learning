# U：最后一次固定 Q 多步位置头候选的 bounded L-BFGS 几何修订

U 是当前 Q phi50 / C400 / 双 q-head 多步损失候选族的最后一次优化器修订。T 首次完成全部 300 finite objective 与完整预测请求；每 seed 100 objective 预算停、12 registered accepted update，训练 loss 小幅降低但原 K/D 双开发门仍未过。U 只检验归一化梯度方向是否丢失有用的小 Newton 幅度，不续 T、不追加同 seed 预算，也不解释训练 loss 降低为科学成功。

U 每 seed 首次从原 Q 初始化一次。协议和源码先冻结，再由 root 在干净精确提交首执行。作者只读 root 导出的 metadata 绑定账、复用已缓存源码并静态检查新源码/协议；不 import 或执行 U、自检、model、objective、gradient、fit 或科学 payload。root 首次新几何 self-check 不重跑 T 已通过的 12 个工程 fixture。

## 冻结的科学核心和旧成本

U 动态导入 pinned T，复用 T 的已冻结数值非有限分类、S 科学 forward/autograd kernel、训练 population、运行时身份、K/Q/D 恢复与评估。T 源码为 46,375 bytes / e4cd9e06d078e85ba82614f05b160e69e8b11bd6e66773d795646f5766759464，协议为 8,655 bytes / 79a18f3bc52ded3b650d00f0942d7dfc0d4584727c7c71a4a254860af8a59824，source commit 585540fe8ba07c1149e61c4aa6e9638679ecabb3。T 原首 checked bytes 与冻结尾空行修订的证据由 root 原样保留；U 不再核算旧工程或梯度。

保持公共 phi50、x22 全状态闭合、原 prior、exact guard 和连续过去端点推进；只有 q0/q1 的 50×2 权重变化，其余 20 heads 的 50×20 权重冻结且保留状态梯度路径。无状态 clipping、guard smoothing、straight-through、teacher forcing、新特征或特权观测。任务目标、共享权限、努力分母和原 K/D gate 阈值保持不变，Q 仅描述。

每 seed C calibration step100–499 固定 400 训练转移。H1/H2/H5/H15 连续 window 仍为 400/399/396/386，共 1,581 windows、3,162 terminal q label uses、完整 objective 8,968 transitions。原 800 唯一 q scalar labels/seed 与终端标签只入损失的边界不变。

    L(U) = .25 * sum_h mean_origins_and_two_axes(((q_pred_end-q_actual_end)/.12)^2)
           + .01 * sum((U-UQ)^2)

不重拟合 Q/K/D，不恢复 T 候选，不新物理、RLS、MPC、教师或安装依赖。Q、S、T 历史成本分别保存。T 仅新增读取 root manifest / raw manifest / raw run 三份 byte-pinned metadata，核对绑定、completed run、self_check=false、clean585540f、源字节与 C/D/K/Q/S 输入身份，保留 frozen_T_original_cost；不读取 T parameters/predictions 或重算 T 科学量。原 S metadata-only 读取直接复用 T helper。新 kernel 计账把 T helper 的 training namespace 转录为 U_training，保存实际付费计算，不改变数学。

## 唯一新方向

memory 固定 5 pairs。初始逆 Hessian 为 I；无 history 时 p=-g。有 history 时使用标准 limited-memory 两环：

1. q=g，按新到旧顺序：rho_i=1/(s_i·y_i)，a_i=rho_i*(s_i·q)，q=q-a_i*y_i。
2. gamma=(s_last·y_last)/(y_last·y_last)，r=gamma*q。
3. 按旧到新顺序：b_i=rho_i*(y_i·r)，r=r+s_i*(a_i-b_i)。
4. p=-r。若 ||p||_2 > Δ=1e-3，仅缩小到该 L2 上限；小方向完全保留，绝不归一化放大。

trial = current_U + t*p，t 初值 1，beta=.5，最多 10 trial/accepted iteration。Δ 只应用一次；不再次乘旧 T alpha=.001。Armijo c=1e-4，阈值为 current_true_loss+c*t*(g·p)，斜率绑定最终 capped p；每次 trial 仍求真实 loss 与全 100 gradient，没有额外 objective 计算用于选择或 history。

新的 accepted checkpoint 完成原持久化后注册边界后，才计算 s=new_U-old_U、y=new_g-old_g。有限 validated Q initial0 是第一次已注册更新的左 anchor；initial0 单独不形成 pair、不计更新、不发布。此后只使用相邻已注册更新。拒绝、partial 或 post-persistence 未注册的越界快照不能生成 pair。

仅 s/y finite、s·y finite 且严格 >0 时加入；不加 epsilon、floor、相对曲率阈值或扫描。超过 5 pairs 只移除最旧 pair。y·y 及 rho/gamma/two-loop 的计算非有限，或最终 capped p 的真实 g·p 非有限/非下降时，清空 history 并用 -g 经同 Δ 上限的一次固定 fallback；fallback 不放大小方向，也不再尝试另一个几何。如果 fallback 仍非法则是非预算 fit failure，无候选。结构/shape/固定输入/IO 错误保持 fatal，不得伪装数值 fallback 或预算退出。

方向与 history attempts/returns/failures、内积、除法、向量更新、cap、pair 加入/拒绝/淘汰和 fallback 独立计账；保存 direction、pair、非有限 partial 与实际成本，严格 JSON 显式转录所有非有限证据。方向 geometry 不宣称物理安全或新的保护。

## 预算、选择和失败保持 T 边界

每 seed 最多 100 次 objective（初始、有限/非有限拒绝、失败 partial 全计）、30 个 registered accepted updates 和 120s 入口/出口/持久化后注册边界。计墙时、CPU时和 overrun；无硬墙时间或抢占承诺。预算停止仅可发布 >=1 真实 finite registered U update，选最后注册顺序，不选最佳 loss、末 trial 或 initial0。

10 trial 全拒绝、结构错误、内部错误及其他非预算 failure 均无候选；已有 accepted 快照只保留证据。非预算异常即使跨时间边界也保持 fatal。initial0 非有限或 exact-zero gradient 没有 U update，不能发布。新持久化跨界快照不能升级 last，此前 registered update 可在预算停止时发布。30 accepted limit 是非收敛预算停。发布 50×22 权重独立 finite 校验及冻结 20 heads 等同性不变。

固定 4,572 requested U/Q/K/D prediction records、840 channel groups，原 K/D dual gate、完整 fixed-count 优先及所有停止/不可用记录继续保留。不能用部分 RMSE 排名、步数减少或零停止宣称效率/安全。任何成功只是 seen-C 开发证据；scientific_adoption、c4_scientific_validation、c5_scientific_dependency_released 继续 false，C4完整控制及 C5/C6/C7 未放行。

## 首次新几何检查与退出条件

新 self-check 仅 9 组几何：I 大方向 cap、小方向不放大、单 pair 小 Newton 保留、两轴两环逆近似、正曲率/initial anchor/memory5淘汰与非正拒绝、gamma 非有限一次 fallback、rho 非有限一次 fallback、finite 非下降/underflow 一次 fallback、shape fatal 不 fallback。它们不调用科学模型、不重做旧 mapping/gradient、不执行 T 工程 fixture。每组保存实际方向/history 与成本，自检通过不证明原科学门通过。

接口：

    python scripts/develop_guard_bounded_lbfgs_position_transition.py --repo . --output <new-directory> --self-check
    python scripts/develop_guard_bounded_lbfgs_position_transition.py --repo . --output <new-directory> --source-commit <clean-exact-40hex>

U 正式首次只从 Q 运行一次，失败不补跑到成功。如果 U 仍未过原开发门或数值 fit 失败，公开该固定数据、特征及目标下的局部负结论，终止本 bank 的步长/优化器/特征扫描，保持 C4/C5 科学依赖关闭；持续目标转入一次有边界路线诊断或新物理信息设计及其先冻结协议。active 不表示无限同数据优化。数值失败不等于否定全部多步身体建模，训练 loss/正曲率也不等于泛化或完整控制。

参见 [T 协议](GUARD_TRUST_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md)、[S 协议](GUARD_MULTISTEP_POSITION_TRANSITION_DEVELOPMENT_PROTOCOL.md)、[持续阶段账本](CONTINUOUS_EXECUTION_PLAN.md)。
