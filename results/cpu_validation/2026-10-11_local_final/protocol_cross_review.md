# C2/C3 最终单肩协议只读交叉复核

2026-10-11；复核范围为协议、runner、标准库 audit 及相关合成测试源码。未导入或运行项目模块，未运行正式矩阵、MuJoCo、拟合、预测或新留出；只用标准库 AST 解析确认源码语法。未读取任何 20/21/22 的物理初态、模型或真实结果。只写本 ignored 文件，未改 tracked 或 C2 任何原件。

核心研究门、控制配方、失败依赖与计账对齐。冻结前发现的“末段误差”描述性诊断缺口已修：协议固定每个目标的最后 20 个计划 active 端点（active 80–99、180–199），audit 新增 control_tail_metrics 与四种 control trial 的 tail_tracking 输出，保留完整/缺失/partial 计数和原始误差。收益门不改变。本复核已只读检查此次 delta，没有余下实质偏差。

## 被复核源码

| 文件 | bytes | SHA256 |
|---|---:|---|
| docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md | 7821 | 45f053fff597b8c03d44d3c92751dbda1f71d64486579b55253c7ac59331e5d7 |
| src/developmental_physics/local_frozen_validation.py | 46274 | cd5822defbb84cc4c6319c8490be3cb5ce7f259f18b45f5badfacf021e9a2149 |
| scripts/audit_local_frozen.py | 92690 | cfa33ae0703afac1861f9d1a6561cae4a5c7dbe64fb7d33e4229444cace9c966 |

两 Python 源均 AST-valid，tail delta 后 audit 又完成只读 AST 解析。audit imports 只有标准库；runner 的 MuJoCo/NumPy 依赖没有在本复核中执行。112 项合成已过来自父代理提供的验收记录；tail delta 的三个纯手算定向 passed / .14 s，以及完整 21 trial 数学档案集成定向 1 passed / 8.28 s 也来自父代理。本子任务未重跑，不能将这些数字称为本次新增测试。

## 固定配方与唯一留出

- runner `FROZEN_FINAL_SCHEDULE="short"`，run_validation 在建输出/物理环境前拒绝其他 schedule；old/hinge5/endpoint_euler、supine/j0、PD64/0 同时固定。CLI 不提供调参入口。elbow_development 的 PD gain 尚未冻结，入口先拒绝，不能误作本最终留出的替代套件。
- runner 要求准确有序的 int seed `[20,21,22]`；audit `require_final` 在打开 trace 前要求唯一 suite/split/pose/j0/short，随后校验精确配方、协议 SHA 和源码 ZIP。
- runner 沿用 `SeedSequence(seed).spawn(2)[0].generate_state(1)[0]`，audit 固定 reset_seed 为 1822509288 / 2605417566 / 1950464737。声明这些纯算术常量不等于取得物理初态或指标，也没有从新留出选择种子。
- 每 seed 的模型从 hinge theta `[1,0,.02,0,0]`、P=100I、lambda1、hinge threshold .25 创建，未载入开发模型。只在 calibration 的完整 10 子步转移更新，calibration 后冻结；evaluation 的 before/after fingerprints 受 runner 和 audit 双核对。
- runner 自己记录 source status，不在入口自动拒绝 dirty；正式执行须由 root 在提交/推送后确认 clean。audit 将 dirty 或源 Git blob 不一致视为一致性失败，不能事后将 dirty 物理运行算作正式有效批次。

## 五、六、七 trial 门

| 命题 | 必要 trial/seed | 判定 |
|---|---|---|
| 同 MPC 的局部模型贡献 | calibration、prediction_low、prediction_full、nominal_mpc、learned_mpc | 三 seed 全部五项完整无 stop/异常/非法/非有限；low/full 的 learned v RMSE 各 seed ≤0.8×nominal；tracking 每 seed 严格更小；三个原始 RMSE 均值降低≥20% |
| 对经典 PD 的比较 | 上述五项+tuned_pd | 先模型贡献通过；六项完整；tracking 每 seed ≤PD，三个原始均值降低≥5%；actual control |u| 与 u² 各三 seed 均值≤1.05×PD |
| complete_matrix | 全七项，另含 zero_torque | 独立输出整体完成情况；不作为前两门的替代 |

`complete_trials` 核对三个唯一整型 seed；`trial_is_complete` 要求 eligible/completed/status 及 study/env=false。主门仅取 MODEL_REQUIRED=KINDS[:5]；PD 门仅追加 tuned_pd；zero 失败不抹除完整局部主门，PD 失败也不会反向把主门判失败。风险仍全量记录，不因局部通过称全矩阵安全。

速度门采用乘法，没有 epsilon：nominal=0、learned=0 可通过数值门，百分比仍 None。tracking 分母零令均值改善未定义、均值门失败，逐 seed 严格条件照常。PD effort=0 仅允许 learned=0；比率 None，不造百分比。audit 的 validated_pass 还要求一致性零失败及启用源 Git 核验；git_root=None 的合成运行不能成为正式性能结论。

## 公平信息与不同总成本

四控制都在独立 reset 后付 100 步零请求 prefix，active 200 步，目标当前可见、切换不预告；同身体/baseline 接触/限位/急停逻辑/.5 Nm/另外七关节零请求。原生 qref/方向均由各自已付 prefix 末端与公开限位确定，audit 比对完整 prefix 字节 payload 与公共 direction_record。

这说明配对控制窗口、权限和信息一致，不能推出相同总启动成本。学习控制另需每 seed 400 次真实 calibration（100 prefix+300 active），PD/zero/nominal 自身无需该校准；共同 prediction 的 2×200 是独立评价成本。原始 phase/trial ledger 可逐方法列出这些成本；九组 PD 开发和全部 C2 开发账须继续披露，不能将总矩阵 6000 次均摊为每方法预算。

PD action 仅 `clip(64*(target-q),-.5,.5)`，Kd=0；audit 独立重算 continuous request、raw_pd、gain、无 planner；zero 不读模型执行动作。PD/zero 轨迹上即使存储 frozen 模型的诊断预测，也不改变动作输入或构成 PD 拟合先决条件。

## 依赖、停止与异常

- runner/audit 的 calibration 依赖仅用于两 prediction 和 learned_mpc；nominal、PD、zero 独立继续。cal prefix 失败后，nominal 可以从其自身 prefix 建参考和公共 prior；没有从失败模型取得动作能力。已有合成源码覆盖 prefix/active calibration 失败仍能执行三 baseline。
- 所有返回 active endpoint 以原生 q/v 独立触发 StudyAbort（≥.12 rad 或 ≥1 rad/s），prefix 不用此门。env/study 分别保留，env 原 reason 优先；不输出制动/纠正动作。最后计划步 stop 也不 completed。
- 完整 terminal 的预测/target 分数及 RLS 更新保留；partial (<10 子步) 只保存当前 target 的原生误差、实际子步/努力、updated=false 和已有模型 count，不进入完整 20ms RMSE、RLS 或有效 rollout。model_update 的 hinge5 和 model_id=short_hinge5 各层含义一致。
- 异常 endpoint 的 `partial_model_snapshots` 使用键 hinge5（不是 short_hinge5），保存成功 atomic 后 theta/P/count；audit shared_transition_id 去重，支持有 update item 或 atomic 已成功但 item 未返回时恢复一次。只有唯一完整缺失 10 子步、原生 endpoint、正确 phase 成本和原始计数才能恢复；不会从 partial 创造一次更新。
- 缺 raw 实际力矩 history 的成本仍保留 requested effort 与 paid physics，actual effort/风险标下界，不填零或捏造完整；更新、returned/attempted、phase、trial、batch 相互对账。普通异常不补跑，IO/trace/checkpoint/中断 fatal 后所有未开始项 blocked，失败模型与源码/原始文件保留。

## 固定预算复核

| phase | control | physics substeps |
|---|---:|---:|
| prefix | 2100 | 21000 |
| calibration | 900 | 9000 |
| prediction | 600 | 6000 |
| control | 2400 | 24000 |
| 合计 | 6000 | 60000 |

每 seed 顺序和最大调用为 400+200+200+300+300+300+300=2000；7 trial/20000 子步/300 RLS，三 seed 21 trial/6000/60000/900。audit planned_matrix、maximum_control_steps、phase caps、batch caps 与 runner 一致。相同规范下累计基点 202850/2028500/9000，完整批次结束为 208850/2088500/9900；本次只读复核不改变物理或 RLS 总账。

## 诊断与保留边界

audit 覆盖完整 q/v 原生输入支持与 q-only nearest、1/5/15/50 多步 q/v 的路径和端点 RMSE、有效/排除/terminal 窗口、block/幅度/切换/保持分箱、各 phase 的子步接触峰/冲量/穿透/动能及端点八关节速度/软限位/干预。未来已记录 request 仅作离线条件输入，不授予在线预知。两个 target 窗口已分组，tail 已修；calibration-final 模型诊断标 in-sample，重叠窗口不独立。

tail delta 具体检查如下：原始 step_index=100+active，因此两个区间为180–199与280–299；选择条件严格小于120+first，准确取得20个计划端点。仅 control 的普通记录、executed_substeps=10且target可见时评分。planned_endpoints始终20，returned/scored_complete/partial/missing分别报告；RMSE和signed mean分母用实际完整评分数，缺失不填零，空窗为None。complete_without_stop核对完整index集合且无任何study/env stop；完整terminal可参与评分，contains_stop仍true并阻止完成。窗口完成与整个trial完成分别报告，第一尾窗完整不能掩盖随后失败。四个control即使blocked或qref缺失也输出20端点缺失状态；收益门没有读取tail指标。合成源码分别覆盖手算.1rad误差、17返回/16完整/1partial/3缺失、完整terminal评分且不完成，以及完整21trial集成字段。

阶段目标仍是固定单肩上的局部预测/同 MPC 模型贡献与强 baseline 比较。三 seed 不证明统计显著性、未见动力学适应、冷启动站立/行走或真机能力。协议明确本批结果失败也归档、20–22随后已见、未来改配方另编号和新 seed bank；之后继续左肘/协调，而非在漂亮单肩结果处停止。
