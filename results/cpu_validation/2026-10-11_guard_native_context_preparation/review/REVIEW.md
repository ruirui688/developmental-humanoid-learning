# F 草稿的有限独立静态审查

审查对象固定为下列原件，不读取 E 首次实验或 C/D 数据，不运行诊断、
数学、旧审计、fake 矩阵、仿真或 Git：

- `external/c4_native_context_diagnostic_staging/diagnose_guard_native_context.py`
  SHA256 `037fb78aa17333aaebe4db15b7737b887cb7d1168ce415421777428c51cfcf47`
- `external/c4_native_context_protocol_staging/F_PROTOCOL_DRAFT.md`
  SHA256 `a46f036e55d7ffe809d6ff2fdd09aae336b3cc2413578607b87ef69c85d6790e`

这是有限源码审阅，不替代 F 的独立验收或真实来源绑定。正式开关仍为 false。
不改 E 的候选、科学门或任何 tracked 文件；实现者已收到以下发现。

## 已核对的边界与计算

F 只提取动作前原生 q/v/gyro/acc；返回端点只用于保存预测的离线误差。
没有模型、runner、MuJoCo 或 C/D auditor 导入，也不消费 planner 候选预测、
root pose、qpos/qvel、接触真值或未来 actual torque。

`acc_delta` 的 current-before 与前一 before，在 active0 分别是 prefix99 与
prefix98 的原生端点；连续性另要求两段完整过去，部分 current interval 不会
被用于 20 ms 主误差。每个 trial 的 8D qref 来自自己的 prefix99 返回。
body6、gyro、acc_delta 的尺度与固定 bins 符合协议。

尾部窗口由递增的原 transition ID 和有返回 endpoint 定义，包含部分 terminal
endpoint，但完整误差另筛选；普通异常通知不自动增加 endpoint。独特的
returned-but-unwritten 通知另外要求 episode 的 returned/returned_unwritten
账匹配；重复通知不重复计数。canonical E 每个 loop 会重置 `stepped=None`，
不存在先前讨论中误读的 stale StepResult；此误读没有进入正式发现。

相关性使用 fsum 中心化二阶和，同时公开 signed/absolute 两种误差，不按结果
挑 bins 或方向；少样本、零方差与溢出/下溢均有 null 原因。seed/kind/predictor/
axis/channel/目标段保持分组，planned 与实际配对分母分开。

E 来源键使用 `first.archive.source_commit` 与六 basename 的
`first.archive.input_hashes`；F 还逐项核 thin summary 的完整复制项，包含
episodes、seeds、physics_budget、paid_prediction_accounting、restoration/
cloning、outcomes 与四 gates。仅用保存值，不重算 E 指标。

## 有限待对齐项

1. **读取费用和计时范围缺口，P2。** 第457行的 `clean_f_provenance` 读取
   own source、binding、protocol 三份本地文件（467/471/477行），没有与 Git
   返回 bytes 分开记录这些 opens/bytes。第673行 wall/CPU 取样发生在 run.json
   写入和 output integrity 读取/hash/manifest 写入之前。已有完整性读取有单独
   账，但计时字段没有声明排除这段尾部工作。建议补三项本地读取账和明确
   `timing_scope`，不把字节单位混合，也不声称零计算。

2. **E preflight 失败会丢失已核 F 身份，P2。** `run_diagnostic` 先取得
   `clean_f_provenance` 的结果，再执行 `sealed_e_inputs`，到第656行才写入
   `run.f_provenance`。若首个 E 文件 hash/身份核查失败，run.json 保留异常和
   `source_records`，却丢失已经核对成功的 F clean commit、source/binding SHA
   与 protocol。建议在 clean provenance 成功后立即保存这些身份，再读 E。

3. **失败类别计数与协议承诺不完全一致，P2。** 194行 regular wrong/duplicate
   ID 直接 raise；invalid exception ID 有独立 fee，而 regular 身份失败没有。
   `vector` 将缺失、形状错误、非有限统一返回 None；score/误差原因常合写为
   `missing_finite_*`，target/history 失败还会覆盖先前的误差原因。因此当前
   输出有有效/缺失总数，却不能直接得到协议要求的各独立 sensor/有限性/
   诊断未成功/身份失败计数。建议增加互不覆盖的缺失标志与计数，或在冻结
   协议明确身份损坏直接中止、哪些类别只保留原失败账。不得把中止行当有效
   主统计。此项不主张重新审核 E 全档。

4. **异常同时含物理 stop 的事件定义需明确，P2。** 第345行 source_stop 还
   要求 episode.status == terminated；带 study/environment stop 的 exception
   仅记录 `stop_flags_in_exception=true`，不作 tail20 窗口。协议“仅采用已声明
   stop”没有明确这个额外状态条件。当前保守分类可以保留，但需明确这类
   combined outcome 被单独披露、没有常规 source_stop 窗口；不能把它解释为
   没有发生物理停止，也不能用普通异常替代 source stop。

另一个需要读者理解的分母区别：`counts.score_valid_n` 覆盖所有保存的动作前
context（可能含 partial/unreturned 通知），而 bin 的
`fraction_of_valid_score_error_pairs` 只除以完整有效误差与 score 的配对数。
两者不是同一分母，代码目前已用不同字段标识；建议在协议表述中同步说明。

所有建议仅修来源/描述工程或明确协议语义，不新增特征选择、算法优势、模型
拟合、统计采用门或新物理。`scientific_adoption` 仍应固定 evaluated/pass false。
