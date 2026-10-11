# G 独立 PD-tail 控制审计工程交付

2026-10-11；仅 external/c4_pd_tail_control_audit_staging/，未修改生产文件、tracked 文件或提交。正式开关 false，canonical 将为 scripts/audit_guard_pd_tail_control.py；suite pd_tail_control_development、协议 docs/GUARD_PD_TAIL_CONTROL_DEVELOPMENT_PROTOCOL.md。

## 新增范围

基于原 E 标准库独立审计源码，保留 D 完整 snapshot/PD 独立绑定、原生历史、物理/部分停止预算、零更新及完整优先门。旧 E auditor 字节作为新增源依赖纳入 SUPPORT，不导入或执行旧 E 全档审计；原 LAG 及其独立支持仍用于已冻结数学。没有导入 online planner/model/runner，没有打开实际 E/C/D/F 数据。

新 candidate_math 对每个原81网格首请求独立重建 H15：h0=b；其余阶段固定 Kp=(64,64)、Kd=(0,4)，仅当前 target 与该候选自身预测 q/v，clip .5。每步原 guard/predict11/history/forecast 限界不变，stage effort 使用该步 request，change 仅首 b 与之前已请求力矩。所有候选重建 cost/rejection/paid steps；返回 trajectory_requested_torque 只含选中可行 H15，fallback 为空；candidate_records.torque 仍是 h0。

planner_spec 绑定原默认配置、历史、tail gains/规则、无未来目标与实际状态、selected 请求字段，fingerprint 仍逐 trial 核对。verify_sources 保留独立重建 PD binding、固定 metadata gains、metadata 与绑定相符三项；新增 tail metadata 固定同增益。必须同源码ZIP包含 new collector/new planner/original base/new auditor/protocol、旧 E auditor+原5独立支持、D及PD绑定。

实际尾费用单列于 paid_tail_request_accounting，不与 pair/scalar 预测混合：完整81 candidate records 首请求=81，tail=sum(max(pair_prediction_attempts-1,0))，含已计算但预测拒绝的阶段。仅已完整保存的决定能给精确数；无完整决定的 planner exception 为 unknown/lower_bound，tail 请求自身可能在下一次 pair attempt 之前失败。regular/重复异常通知按原付费决定身份去重，已返回决定后的物理异常仍保留数学费用。上限 first=97200、tail=1360800；审计自身 tail 重建 COUNTS 另列。

科学门保留同完整权限下控制20%、PD5%、actual effort1.05；D 原独立预测失败仍令 c4_scientific_validation evaluated/pass false。此次工程与人工 fixture 不解除 C4/C5，不构成控制收益。

## 一次必要新检查

CHECK_01.json 首次保存 **27 passed /0 failed**。仅新增 G tail 数学/请求字段/尾账/metadata/正式关闭接口，8个原 E 核心函数只比 AST，原 E/旧 tail 数学 fixture 不重跑。

手写独立 fake predictor 1311次，审计自身新计数：163 candidate replays、2 planner replays、1311pair/2622scalar 计算、1148tail request reconstructions，3 saved-decision 计账核对。fake 只提供合成 q/v 转移，真实在线 model.predict=0；原已冻结 model 数学 MATH_COST 增量为空，没有重复验证旧 lag predictor。真实物理、拟合/更新、实际 E/C/D/F 数据读取均0。

检查涵盖候选自身反馈与历史、各stage请求努力/仅首change、全部81候选、新selected请求篡改检测、完整/被拒阶段尾计账、重复notice、不完整决定与失败规划unknown、fallback空请求、固定增益/caps、formal拒绝。没有执行正式 archive loader 或真实模型恢复。

fixture wall .17931490018963814s，工具 exec wall .6445754s；fixture范围自入口至报告组装，含独立支持源加载，排除末CHECK JSON序列化/写盘。显式读取G源码与原E baseline快照2次，bytes见CHECK_01；Python source/module加载有非零工作，未混入这两份显式读取账。工程 source 阅读/编译不等于零计算。

## 保留工程失败

新增尾计账的首次 apply_patch 因误写原 metric_maps 行为 common.joint_rmse 而匹配失败，没有部分落盘或运行数学。必要读取该源段确认实际 guard.paired_rmse 后修正补丁；仅首次 CHECK_01 被执行一次。BUILD_SOURCE_RECORD.json 保留初始 draft 及原E源码身份，最终源码身份与封口费用另见 INTEGRITY.json；不把初始draft称最终执行source。

root需先核最终协议和canonical来源，冻结并正常提交推送后才可一次正式G物理与首审。当前formal=false、实际物理0，不运行旧档audit或补跑小检查。
