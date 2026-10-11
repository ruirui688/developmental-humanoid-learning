# F 首次输出检查：新增断言的契约范围说明

2026-10-11；本补充不修改 FIRST_OUTPUT_CONTRACT_CHECK.json、原 REVIEW.md、F 输出或检查器，不重新运行检查、诊断或数学。首次 **50,255 项 / 24 失败** 原样保留。

冻结 F 协议第4节的精确句为：

> N≤20 时 earlier 分母明确为0，所有 earlier 统计为 null/`empty_window`；
> 不借其他 trial 填充，不计算“临停/之前改善百分比”。

同节先定义 `earlier=之前max(N−20,0)个`，并说明先在不分目标段的事件计数中公开，再按目标段在主表增加 window 标识。该规则明确要求 N≤20 时整个 earlier 为空的情形，并未额外要求非空 earlier 窗口内每个空 target 分段具有非空 `empty_window_reason`。

原首次检查中的24失败均来自我新增的断言：对任何 `expected_n == 0` 的目标分段检查 `bool(g["empty_window_reason"])`。本轮保存事件 N=104，整个 earlier=84；earlier×B 是该非空窗口中的空目标段。原首次输出的 Pearson 已为 null 且有原因、bin n=0及配对分母核对通过。因此这24项是**审查者增加了比冻结协议更宽的断言**，不能据此认定 F 违反原协议的 N≤20 空窗口要求。

这是我的检查范围错误；补充明确纠正其解释，不删除或重新计算首次24失败，也不追认该首次检查为零失败。F 原协议无需为了此新增断言事后加条件或重跑。描述分层仍不证明因果，scientific_adoption.evaluated/passed 仍 false，C4/C5 与 D/E 原科学门不变。

本补充仅必要读取冻结协议和自己的首次失败记录：**2 opens /16,095 bytes**，协议10,344bytes、SHA256 `eecf6cdf71699d18a076229765d7246c265a9fb0ddc95b60ce875d15795caaf3`；首次记录5,751bytes、SHA256 `22ed5a8add8282882ca8e4e5b3a48bc2d71acb9c5a78a0478e99402369104ec1`。read/hash wall `0.009649599902331829s`，不含decode/excerpt/parse、输出写盘或人工推理；source记录与协议原字节已保存。

本轮有限审查累计输入读取 **8 opens /6,389,001 bytes**。补充0新检查、0统计、0模型/物理、0实际实验数据读取，不重算 Pearson/norm 或消除原首失败。原首次失败与本补充共同封存，继续 G 独立审计工程。
