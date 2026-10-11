# F 工程修订交付（revision 01）

最终源码与协议已冻结在本目录的独立快照。顶层 `DELIVERY.md`、
`INTEGRITY.json` 及 `*.original.*` 保留首轮版本，不应解释成当前版本的绑定。
本交付只供 root 提升、冻结与独立有限审查；正式诊断开关仍为 `False`。

## 最终身份

| 文件 | SHA256 | binary bytes |
| --- | --- | ---: |
| `diagnose_guard_native_context.final.py`（与当前 staging 源码相同） | `c25a83ad6986c798477652dde7d0b61c45e839351afa329a5ff1f57f224a7063` | 44292 |
| `F_PROTOCOL_DRAFT.final.md`（与当前协议相同） | `7eb27e57d0aed1edfd318170c17cd8e50761ffcb7977d3c23ad4680bd562c6e5` | 9861 |

源码 staging 路径为 `../diagnose_guard_native_context.py`，canonical 路径为
`scripts/diagnose_guard_native_context.py`。协议 staging 路径为
`../../c4_native_context_protocol_staging/F_PROTOCOL_DRAFT.md`。
原审查绑定为源码 `037fb78aa17333aaebe4db15b7737b887cb7d1168ce415421777428c51cfcf47`、
协议 `a46f036e55d7ffe809d6ff2fdd09aae336b3cc2413578607b87ef69c85d6790e`。
完整文本变化见 `REVISION_DIFF.patch`，新清单见 `INTEGRITY_REVISION_01.json`。

## 修订范围

1. F 自身的 source、binding、protocol 读取分别计 opens 和 binary bytes，
   与 Git 返回 bytes、E 源读取和 task cache 读取分开。`run.json` 明确主计时
   不含尾部 run/manifest 写盘和输出完整性读/hash；`manifest.json` 单列
   run 写盘与完整性读取/hash 的计时，排除最后 manifest 序列化/写盘。
2. clean F provenance 一经核验，立即保存在 run 中，随后才开始 E 预检。
   因此首个 E 预检失败也能保留已核 F 身份。
3. 常规动作 ID 缺失、错误、重复及其他身份问题在退出前分别计数。
   最后补了非字符串 ID 的 membership 保护，列表型 ID 也会明确计为错误，
   不会先抛未计数的 `TypeError`。缺失、错误形状、非法标量、非有限值、
   不完整 interval、缺失历史、缺失 target 等作为独立旁路 flags 保留。
   多个 flags 可同时属于一行；flags 总数不等于样本数，也不修改原误差资格。
4. 协议区分原始 `terminated` 且声明 stop 的常规 tail，与伴随实际 stop flags
   的 `exception`。后者保留原停止原因、flags 和费用，不进入常规 tail，
   并不表示没有物理停止。
5. 协议明确 `score_valid_n` 是所有保存动作前 context 的分母，可包含 partial
   或唯一 unreturned 记录；bins 的比例只除完整有效 error+score 配对数。

三个 native score、bins、相关描述公式和科学验收门保持不变。
E 完整行只保存 `predicted_next_qv` 和 `after`，因此必要的 `after-pred` 描述代数
保留；partial 专用误差不进入主统计。科学采用始终为 false，不追认旧门。

## 必要检查

`AST_SOURCE_CHECK_02.json` 的 20 项静态检查通过，绑定中间源码
`057f7a1e89970ae2482a239f6dbf3a6d63c897855ab3589c34b3b0941774e0c0`。
该版本另存为 `diagnose_guard_native_context.ast02_verified.py`。

随后对新增分支做唯一一次最小 fake/monkeypatch 检查，结果保存在
`BRANCH_CHECK_01.json`：**64 passed / 0 failed**。包括 17 个数学/native core
与原 037 源码的 AST 一致、其余函数与 AST02 源码一致、derive_rows 唯一额外
变化为 regular-ID 类型保护，以及以下运行分支：

- 15 个同时缺失标志和 13 个混合质量标志独立保留，行数与 flags 数分开；
- 缺失、错误、列表型及重复 regular-ID 均先记计数再退出；
- F 三种本地读取标签分别记账；
- stubbed E 首预检失败仍保存 fake 已核 F provenance，尾部计时范围明确。

检查只导入 F 的标准库源码；统计入口被替换为禁止执行的 stub。正式开关
仅在内存中的 fake 检查临时设为 true，检查后恢复，磁盘源码始终 false。
fake preflight 输出明确带 `synthetic_test_provenance: true`，不属于 E 正式结果。

首个静态检查器曾因把 `Assign` 当作 `Try` 而失败，该失败原样保存在
`AST_SOURCE_CHECK_01_FAILURE.md`；这是检查器错误，没有据此改 F。
旧 3 项人工统计 fixture 已成功且没有重跑，本轮没有完整 fake 矩阵。

## 本轮费用

下表只汇总显式应用层文件读取，不含 Python 解释器/标准库内部读取；
写盘与计算的计时范围在各原始记录中另列。不存在实际 E/C/D 数据读取。

| 操作 | opens | binary bytes | hashes | AST parses |
| --- | ---: | ---: | ---: | ---: |
| 原件保存 + 两次 AST 检查（含失败） | 12 | 251287 | 8 | 4 |
| AST02 已核源码额外保存 | 1 | 44229 | 1 | 0 |
| 唯一分支检查 source 读取 | 4 | 136936 | 4 | 3 |
| fake F 三标签读取 | 3 | 78 | 0 | 0 |
| fake preflight 内部输出完整性读取 | 1 | 1926 | 1 | 0 |
| 检查器读取 fake run/manifest | 2 | 2528 | 0 | 0 |
| 最终 source/protocol 快照保存 | 2 | 54153 | 2 | 0 |
| 原件与最终快照生成 diff | 4 | 100085 | 0 | 0 |
| 上述修订与检查合计 | **29** | **591222** | **16** | **7** |
| 额外协调工具内容读取 | 6 | 54613 | 0 | 0 |
| 新完整性清单生成前总计 | **35** | **645835** | **16** | **7** |

新清单生成所需读取与 hash 单列在 `INTEGRITY_REVISION_01.json`，不混入上表。
原件、失败、中间已核源码、final 快照、fake 检查记录和生成 diff 的费用记录
均保留。所有本轮新描述统计运算、模型调用、RLS 更新、物理查询、实际
E/C/D 读取、Git 调用、旧统计 fixture 重跑均为 **0**。fake 行只有数据质量
分类和身份计数；没有新预测、模型拟合或仿真。

静态 AST02 wall/CPU 为 0.05054870015010238/0.0625 s；失败首检查 wrapper
wall 为 0.5386348 s、CPU 不可得；唯一分支检查 wall/CPU 为
0.22373649990186095/0.09375 s。fake preflight 主计时与最终记录计时分别保留
在分支记录中，不重复加入分支整体计时。diff wall/CPU 为
0.02095869998447597/0.015625 s。其他保存操作没有声称独立 CPU 计时。

root 的正式冻结须单独核定 canonical 源码、协议和 committed binding。
本子代理没有执行 Git，没有运行 F 正式诊断，也没有对 E/C/D 科学结果作判断。
