# F revision_01 的一次有限独立静态审查

2026-10-11；依 root 授权，只读取修订前后 source/protocol 原件及首次 REVIEW.md，核对原四项修正及 score 分母。未读取 E/C/D 数据，未执行诊断、模型、物理、数学、统计、旧审计或 fake fixture，未修改生产文件。

结论：四项及分母说明已对齐，所查范围内没有新增阻塞。此结论只适用于下面固定 SHA 的修订差异；它不替代正式 F 来源绑定、首次描述执行或独立验收，不证明 native 上下文与预测失配的因果关系。原首次待修正记录保留，不覆盖或追认其已无缺口。

## 逐项核对

1. 本地读取与计时范围：新增 read_f_local 分别记录 own source、binding、protocol 的 opens/binary bytes，与 Git 返回 bytes、E 输入及 cache 读取保持分账。主 run 的 timing_scope 明确排除 run/manifest 写盘与 output-integrity 读取/hash；manifest 的 final_record_timing 单列 run 写盘及完整性读取/hash，并明确排除最后 manifest 序列化/写盘。未把遗漏尾段计时写作零计算。
2. E preflight 失败时的 F 来源：clean_f_provenance 成功后立即写入 run.f_provenance，再计算/核对 E archive 路径与 sealed_e_inputs。后续 E 路径、hash 或身份失败进入原 finally 时，已有 F clean commit/source/binding/protocol 身份可保存；没有修改 E 来源门。
3. 缺失与 regular 身份分类：增加逐行 input_quality_flags 和辅助独立计数，分别保留 sensor、target、history、保存预测/返回标签的缺失、形状、scalar 类型与有限性。标志先于 target/history 对原主误差原因的覆盖计算，允许同一行多个标志且不把计数和当样本量。regular missing/wrong/duplicate ID 与 seed/kind/index/order/phase/substep 来源损坏先计独立失败类别再中止；字符串类型保护避免非 hashable regular ID 越过这类计数。原主 score/error eligibility 不变。
4. 异常伴停止：协议明确常规 tail20/earlier 还要求原 status=terminated；status=exception 同时带 stop 标志时，保留合并异常结局、原停止原因及费用，不生成常规 source-stop tail。没有把没有常规 tail 解读为物理没有停止，也没有把普通异常替代 source stop。
5. score 分母：协议明确 counts.score_valid_n/missing_n 基于窗口全部保存动作前 context，可含 partial/唯一 unreturned；paired_n 和 bin fraction 的分母只基于完整有效误差与 score 的配对。前者不补足主误差分母。

## 固定来源与此次读取费用

| 文件 | bytes | SHA256 |
|---|---:|---|
| revision_01/diagnose_guard_native_context.original.py | 38554 | 037fb78aa17333aaebe4db15b7737b887cb7d1168ce415421777428c51cfcf47 |
| revision_01/diagnose_guard_native_context.final.py | 44292 | c25a83ad6986c798477652dde7d0b61c45e839351afa329a5ff1f57f224a7063 |
| revision_01/F_PROTOCOL_DRAFT.original.md | 7378 | a46f036e55d7ffe809d6ff2fdd09aae336b3cc2413578607b87ef69c85d6790e |
| revision_01/F_PROTOCOL_DRAFT.final.md | 9861 | 7eb27e57d0aed1edfd318170c17cd8e50761ffcb7977d3c23ad4680bd562c6e5 |
| ../REVIEW.md | 5220 | 963aa8d9ac492864d29daed3229267bf91334cb63655d3e20f3d85868432cb84 |

前四份来自 external/c4_native_context_diagnostic_staging/revision_01；末份来自 external/c4_native_context_review_staging/REVIEW.md。此次一次读取共5 opens/105305 binary bytes；read/hash/decode wall 0.001550000160932541s，范围只覆盖五份输入读取、hash、decode，不含 diff/render、工具输出、人工阅读或本报告写盘。工具 exec wall 0.452972s另有进程/输出范围，不能代替完整人工审阅墙钟。SOURCE_RECORD.json 保留机器可读身份。

diff 由这五份已读取原件内存生成，没有另读取 revision diff、分支检查结果或其他交付清单。不复跑原数学/fixture；实现者报告的必要分支检查不是本审查独立验证结果。正式开关、来源提升及 F 首次执行仍由 root 单独冻结核对，scientific_adoption.evaluated/passed 保持 false。
