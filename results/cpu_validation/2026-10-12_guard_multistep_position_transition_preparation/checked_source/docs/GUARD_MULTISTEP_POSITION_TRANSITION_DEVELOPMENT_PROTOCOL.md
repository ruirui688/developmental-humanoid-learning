# S：冻结 Q 两位置头的有限多步目标开发协议

唯一候选 S 保留 Q 的 phi50/公开尺度/prior/guard/previous_v 与 22 维自身闭合；冻结其它 20 个输出头的系数，只重拟合肩/肘两个 q-head。源码为 [S script](../scripts/develop_guard_multistep_position_transition.py)，动机见 [R results](GUARD_KINEMATIC_NATIVE_TRANSITION_DEVELOPMENT_RESULTS.md)。R 未识别缺数据或唯一误差原因；“一步训练目标与 H15 门不充分对齐”只是待检验假设。

只使用原已见 C400，不增加物理，不延续 R 梯形、不扫参数、不增模型阶数、不重启或补跑到成功。开发门不改变，科学采用/C4 验证/C5 科学依赖释放始终 false；此开发 bank 不改称未见验收。

## 1. 来源、权限与恢复

复用 R 的纯来源校验/恢复 helper 与 Q 纯函数；不读取 R 科学 payload、不运行 R 数学。S 锁定 helper bytes/SHA；原 C/D/K/Q 输入使用已有固定 hash/bytes、manifest 和 source commit 绑定。Q clean commit 为 `20fa0321c84eb766eeafb9f8d906f554bca60622`。正式执行须 S 精确 40 位 commit、clean HEAD 与提交字节相等；输出新建且不包含原输入路径，不覆盖旧输出。

单次 gzip 解析复用 K `parse_trials`，仅保留 calibration_sparse/prediction 的原生 q8/v8/gyro3/acceleration3、已知请求、ID、完整子步及源 stop 标志。没有未来实际力矩、接触、root quaternion、隐藏动力学或 orientation 注入模型。

Q/K/D 只恢复，不更新/重拟合；每 seed 保存权重指纹 before/after，必须一致。Q 历史 26,400 标签/3 solve/3,300 拟合系数与其它原费用完整继承；S 不能称从零零训练成本。

## 2. 固定训练人口与损失

seed 0/1/2。每 seed calibration_sparse trial 必须精确 steps 0..499、400 active，训练 IDs 为 100..499 且等于旧 K 保存 IDs；prefix:99 after 的 q8 等于 K/Q qref 和 prediction prefix:99 after，前两轴等于 D qref。prediction trial 必须精确 0..199、100 active。

H 固定 1/2/5/15，全部 origins 400/399/396/386，共 1,581 窗。每窗复用原 K window 检查：同 trial 连续过去两端点、原生感觉一致、完整 10 子步、连续已知请求、此前无 stop。最后完整端点可含 stop，不删窗；缺失/部分/非有限/来源不同使开发失败，不缩分母、不补零或跨 trial previous_v。

每窗递推仅传首个 x22、合法 previous_v2、该窗未来已知请求；未来实际两轴 q 仅为末端相对 qref 的 label，不注入中间感觉。prediction 不参与梯度、早停或参数选择。

```text
U_Q = frozen_Q_weights50x22[:,0:2]
U_initial = U_Q
weights_S = concatenate(U, frozen_Q_weights50x22[:,2:22])

L(U) = (1/4) * sum_h mean_over_all_origins_and_two_axes(
                         ((q_pred_end(U)-q_actual_end)/.12)^2)
       + .01 * sum_50x2 (U-U_Q)^2
```

每 h/每轴等权，先平方再均值；100 系数正则为 sum，不除 100 或 seed。位置尺度 .12 为公开值，不估 RMS。这是新的固定目标/正则先验：数值 .01 虽同 Q，其归一化与零中心 ridge 有不同有效强度，不称原 ridge 未变。

每 seed 800 唯一 q scalar 标签；每完整 objective 3,162 label 用途、1,581 窗、8,968 转移，以及各 197,296 prior/residual scalar 输出。三 seed 可优化 300 系数，冻结其它 3,000 系数。窗口/tensor 构造与重复 objective 费用分别按实际请求/返回计；向量化不把一批计为一个窗、转移或标签。

## 3. 训练与预测使用相同映射

训练显式向量化原 Q 数学；state/request/qref/weights/常量直接 CPU float64 材料化。推断调用原 Q `rollout50`，只替换两个 q-head weights，实际费用改名 S22，不调用 R。

guard 先 clip 已知请求到 ±.5；绝对 q<=L+.03 且 clipped 请求<0，或 q>=U-.03 且请求>0 时置零。保留等号，zero 不 blocked，q 不裁剪。hinge=`sign(g)*max(abs(g)-.25,0)`。phi29 为 x22/g2/hinge2/1/(old v2−previous_v2)；z 用索引 (0,1,8,9,22,23) 除 (.12,.12,1,1,.5,.5)，21 二次对严格 i<=j 顺序。

prior 的 q8=old q+.02*old v8，v0/1=old v+.02*g，其余 12 输出 persistence。全 22 residual 输出全部计算；previous_v_next=old current v2，全部自身状态继续反馈。其它 20 头冻结的是系数，其状态路径不 detach/no_grad、不替换真实中间状态。

guard 对 q 有有限跳变，hinge 有折点；布尔 mask autograd 只给当前分支导数，不给跳跃导数。不平滑/直通。L-BFGS-B 为一次固定启发式优化，success/小梯度不能证明数学光滑收敛、有效性、控制能力或安全。有限 U 导致非有限闭合同样失败，不裁 state、删行或返回伪 loss/0 gradient。

## 4. 固定优化、accepted 与失败

预安装运行时：torch 2.2.2+cpu（distribution 2.2.2，git `39901f229520a5256505ec24782f716ee7ddc843`，CUDA null）、SciPy 1.15.3（git `e29dcb65a2040f04819b426a04b60d44a8f69c04`）、NumPy 1.26.4。强制 cpu/float64，`torch.set_num_threads(1)`。本轮不安装或下载；父任务归档预安装身份。上游 [PyTorch](https://github.com/pytorch/pytorch/tree/v2.2.2)、[SciPy](https://github.com/scipy/scipy/tree/v1.15.3)、[NumPy](https://github.com/numpy/numpy/tree/v1.26.4) 均为 BSD-3-Clause；不虚构本轮下载日期。

每 seed 一次 `minimize(method="L-BFGS-B", jac=True, bounds=None)`；一次真实函数调用同时返回 loss 和 analytic gradient：

```text
maxiter=30, maxfun=60, maxls=10, ftol=1e-12, gtol=1e-8
```

initial UQ 先做有限 objective/gradient，计入预算后才登记 iteration0。SciPy 首次重复 UQ 也实际计费，不缓存少计。所有试探保留输入参数、scalar loss/gradient/gradnorm、状态、forward/backward 尝试/返回/partial；solver nfev/njev 独立记录，jac=True 的同次工作不加倍。

硬 objective 计算上限 100/seed，包含 initial；入口先检查，超过不做计算。maxfun/maxiter 是独立 solver 限制，不能替代硬计数。

120 s 从 initial objective 前起，仅在 objective 入口/出口、callback 入口、快照登记入口/持久化出口及 optimizer 返回检查；同步计算不可抢占，可跨界。保留 elapsed/overrun 和跨界费用，停止下一次计算，**不是 hard wall**。人口构造、其它 seed、评价与最终输出写入不含在 per-seed 优化计时。

callback 不重评估，只接受有限且精确绑定同参、已返回有限 loss/gradient、deadline 内 objective 的独立参数 copy。initial/每 callback checkpoint 写盘并绑定 bytes/SHA 和已付费用；写盘跨界的 checkpoint 仅保存证据，不升级 last accepted。只有截止前登记的最后 accepted 次序选择候选。

正常返回也只选 last callback；无 callback 时仅合法 iteration0。不用 best loss、line-search 最后 trial、result.x 或 prediction 分数。maxiter/maxfun 正常限制、硬调用/time boundary 截止允许此前合法 snapshot，但公开 budget_exhausted、reason 和非收敛；无合法 iteration0 则无候选。

line-search 异常、非有限 loss/gradient/状态或其它非预算异常均 fit_failed，accepted 仅归档、不可发布；不回退 Q/cold、不删 seed。optimizer_failed 与 fit_failed 分开：未调用 minimize 的 initial 失败如实标 optimizer 未尝试；已调用后的非预算异常标 optimizer_failed。非预算异常不伪装预算耗尽。

每 seed 各尝试一次。无 S 候选则保留固定 S 评价人口 unavailable，门失败，failure.json 保存已付 partial 与非有限显式编码，不重新执行。

## 5. 原评价门、输出和必要检查

S/Q/K/D × seed 0/1/2 × H1/2/5/15，origins 100/99/96/86，共 4,572 记录/840 通道组。只有 S→K/D 两原门裁判；Q 只描述，R 仅历史动机不重跑：

- H1v/H15q 每 seed 严格改善，且每轴平均相对改善≥20%。
- H2/H5 qv、H15v 每 seed 不劣；H1q 描述。
- 缺失/部分/非有限/零基线失败或不可评，不做部分排名，D 旧门不追认。

保存固定人口/目标、参数、全部 objective/callback、predictions/metrics/run/manifest 与 accepted checkpoint；失败另写 failure.json，沿用非有限编码，不改成零。计时与逻辑操作不是硬件 FLOPs，不推出样本效率、控制效率或安全。

只新增三个小合成 case，不读实际数据、不重跑旧 Q/K/R case：

1. Torch batch step 对 Q 纯函数在 guard 等号/clip/zero/hinge/quadratic/old-v 的 forward parity。
2. 四步自身闭合的两方向 autograd/central difference；固定 v-head 含 q→v 与 previous-delta，覆盖 previous_v 后续反馈；末端 label 改变不注入递推。
3. accepted 选择、硬调用截止、time boundary overrun、line-search 失败与 initial 非有限夹具，保留付费/失败证据。

父任务负责首次执行这些 case、冻结 source commit 和一次正式开发；本次实现只做 AST/compile/hash pins、Markdown 空白/链接及读取账本，不 import 模块或调用 self-check/fit/真实 payload。后续科学采用仍需新冻结留出与匹配完整控制，不能以本阶段完成宣布 C4 或释放 C5/C6/C7。
