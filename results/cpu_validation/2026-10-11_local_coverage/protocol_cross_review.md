# C2-C 协议与采集实现的只读交叉复核

2026-10-11；本子任务只读源码和协议，未导入项目/仿真器、未执行 runner、合成实验、拟合、模型预测、物理或留出。唯一执行的 Python 检查为标准库 AST 解析。**新增物理交互、子步、参数更新及模型预测调用均为 0**。不把源码审核写成实验验收。

复核输入与精确版本：

- `docs/LOCAL_COVERAGE_ABLATION_PROTOCOL.md`，SHA256 `d36cd69c5f99c4b6d8b01d037338329f008edd614e8b59927058320383def966`。
- `external/c2c_staging/local_coverage_ablation.py`，SHA256 `21e2b43242cb2248af340515066243cffc16739c837e9310d3c78f400152fdc3`。
- 辅助只读既有 `environment.py` / `local_model.py` / `collect.py` / staging 合成测试文本；没有运行测试，不替代负责代理的测试报告。

## 当前结论

**未发现当前采集实现与协议在命令配方、StudyAbort、完整/partial评分、失败依赖和交互预算上的实质偏差。** 审核中提出的两个记录缺口已由负责代理修复，并在上述 SHA 版本重新确认：采集加入 `cpu_seconds` 与计时范围，协议独立覆盖门明确必要校准/两参考控制必须完整，禁止 partial 单独获得 coverage_pass。

采集 runner 不实现覆盖/性能采用门；这些仍须由独立审计实现并完成合成回归。此处“无偏差”只限已读 runner 与协议，不能宣称采用门代码、真实物理、覆盖或科研效果通过。正式运行需使用提交后的仓库路径、clean source、冻结协议与最终审计，不从 ignored staging 目录当正式 Git 源执行。

## 1. 对照和算法输入

1. `run_ablation` 在创建目录前拒绝非 development / seeds `[0,1,2]`、非 supine/joint0、非 old dose、非 hinge5、非 endpoint_euler。CLI 只有 output/protocol，无积分/配方/结构调优选项。
2. `calibration_request` 只接受固定 schedule、active 索引及一次性公开方向，不读取状态、误差、目标或接触选动作。short 为 5正/10零/5反/10零 ×10；reordered 为原幅度顺序正50/零100/反50/零100，完全符合协议。
3. 两轨各 50正/50反/200零；固定旧幅度总和 2.75 N·m，平方和 1.0 (N·m)²，每幅度正反各5步，所以 full 请求努力 .55 N·m·s / .20 (N·m)²·s。含 active 首命令相对零 prefix 的切换 40→22；这是完整计划，不是被停止 trial 的已付努力。实际努力从真实 applied history 单列。
4. 每条校准独立 HingeBodyModel 冷启动，固定初值/P/折点/不遗忘 RLS；没有读 B 拟合参数或 warm start。当前 encoder q/v 和 step 前请求 u 进入模型；未来实际力矩/接触/qpos/qvel只存诊断。原生 next-v 是标签。
5. 全部校准完成后 clone_frozen；评估前后模型和积分 fingerprint 检查。请求只有左肩可能非零，固定原权限，现有 MPC 和公开当前目标能力有明确披露，不能把固定 MPC 的目标控制能力称为从零学到的任务策略。
6. 与 B 的 short 历史锚点应逐原生字段精确复现，StudyAbort 若实际触发则保留差异；历史匹配不是新独立 seed。重排会同时改变速度、位置、接触、相关性和更新顺序；协议正确限定为时序配方总效果，覆盖改善不能单独证明因果中介。

## 2. StudyAbort、partial 与停止账本

1. 每个返回 active endpoint 在评分/更新前计算 `abs(q-qref)>=.12` 或 `abs(v)>=1`，含等值与负向对称；prefix 不启用新规则，不能把先前 prefix 高速单独改成 active 先验停机。
2. 触发后保存阈值、当前 q/v、phase、index、独立 study flag、`feedback_action=None`；完整末端仍完成预更新评分、RLS更新和存行，然后 break。没有纠正/返回动作或补试，环境保护不变。
3. `terminated = env.terminated or study_reason is not None`，completed 要求完整计划且未 terminated；故最后计划步触发同样不算 completed。calibration_complete 同样拒绝 study stop，不会给其 learned MPC 建立合法 view。
4. 原 env stop 原因优先；同时存在 study reason 时仍保留独立 study 字段。若停止之后又写盘异常，status exception 但原停止原因/collector_exception 都保留，避免覆盖已经发生的研究停止。
5. executed_substeps 与真实 paid physics 必须一致；partial 不更新，部分控制目标误差进入独立列表/row，只有 executed==10 才进入一步 q/v 与完整 tracking。完整终末转移可以评分；partial 的 endpoint、实际努力和风险仍计账。不能把2–18ms结果与20ms模型直接混算。
6. StudyAbort 仅检查20ms返回时刻，不检查其间每个2ms子步；不发制动指令，env.terminated 可以 false。新规则不是“状态从未越过阈值”或物理制动的保证，协议对此已明确。全身原环境保护继续按既有子步执行。
7. 非有限状态原环境有独立检查；archive_record 保留 invalid 数值位置而不是填零。最终审计必须让任意非法/非有限状态阻断完整和性能门，不能仅凭 native_study_abort 对 NaN 的比较返回 None 判有效。

## 3. 预算、失败和计算成本

固定7 trial/seed：两校准各400控制步，两预测各200，三控制各300，共2,100/seed；全批21trial、6,300调用/63,000子步、1,800 RLS。phase prefix2,100/cal1,800/pred600/control1,800；126s模拟时间。每条校准一个模型更新300次，本批1,800标签=1,800更新，没有双结构共享样本需要倍增解释。

- control call attempted 在 step 前累加，control_steps/physics_steps 从环境实际计数差在 finally 计费，失败返回以前的已付子步仍保留。
- 请求绝对/平方努力按真实 paid physics dt计费；实际努力仅从可读取 applied history恢复。未返回实际遥测标missing/lower bound，不与真实零混淆。
- 模型更新原子提交后若后续存行失败，finally clone/snapshot/update_count 仍保存。单模型失败阻塞自己的 learned MPC和共同预测；另一校准/其 MPC及 nominal可独立继续。nominal在自己的付费prefix重建通用初始模型。
- 普通异常/环境/研究停止保留且不重跑；日志写入任何异常、IO和KeyboardInterrupt/SystemExit为fatal，其余planned标blocked。checkpoint分别尝试保存参数、episode、metadata，避免一处失败不尝试其余关键账本。
- 固定完整 MPC数学规划调用为 `3seed×3controller×200step×9candidate×15H = 243,000`；runner记录成功规划调用、失败规划尝试、耗时和数学调用完整/下界。它是**规划**预测成本，日志一步预测和RLS内部预测不在该计数，不能叫所有计算调用总数，更不能算物理交互。
- 最新 runner 的 CPU与wall从 source snapshot/初期setup以后同时起计，checkpoint采样值包括此前运行；metadata明确不含 imports、初始source snapshot、timer之前setup。最后checkpoint当前写盘和之后manifest写入不在其先取到的采样时间内；若需全进程成本，可另外外部计时，但不可事后编造或重跑补时间。

## 4. 最终审计需确认的覆盖/性能门

协议当前覆盖门已明确必要两cal/short与reordered两参考control完整、无stop/异常/非法/非有限；因此早停的容易前段不能独立获coverage_pass。门不要求nominal完整，但性能门要求三seed全部7trial完整，因此最后采用仍不能绕过nominal失败。两门分别输出这一差别合理，须精确实现。

覆盖描述及门须使用完整active转移**输入**，每完整cal300、control200。每seed的两参考control都是相同真实输入上比较两cal包络，形成4个参考cells；另对nominal全报2cells。reordered q域外≤10%且≤short，v域外≤short，各seed各参考轨迹都成立。严格小/大于域外，边界相等域内；nearest仅q距离，空分母None，partial无完整门。不把 envelope误称安全或联合q/v/action覆盖。

性能门须三seed全部7trial完整且没有任何停机或失败；low/full共同输入速度逐seed非劣；tracking逐seed非劣且三个原始RMSE均值改善≥5%；实际控制abs/square原始均值各≤1.05×short，零tracking分母无改善百分比，零努力只允许candidate零。覆盖和性能都通过、数据一致性及源码验证通过才采用，否则short/old_hinge5。不能用H50/full/某seed替代失败门，也不复用已见10/11/12作独立最终。

独立审计还须把 study_abort 当合法窗口 stop：完整终末转移可作末端、不能跨stop；partial终末不可完整窗口；row中study flag、env stop和exception都单独核对。校准final模型的in-sample标志、共用未来请求离线条件、所有幅度/block/零段、H50退化、full/prefix/active风险及原生端点/子步区别全部保留。

## 5. 接续建议

完成最终审计/合成测试和clean提交后依协议执行一次；本交叉复核不改变动作、阈值、门、预算或科研规则。结果可能通过、失败或研究停止，全部归档并保留成本；不要因“同剂量重排”就预言覆盖成功或同风险。

本复核不读取新最终20/21/22、不新增PD物理、不调用GPU/真机；不存在硬件或凭据需求。协议/实现已有先验和证据边界足够清楚，后续 root按计划完成单肩最终验收再推进多关节、未知动力学和成熟门控。

本子任务停止编辑。待最终审计代码就绪可另行只读核对，不能由本静态报告冒充其通过。
