# CFD1：首次差分拟合资格失败

首次来源：clean **`72e2f50dc728bc0d0e2e4c625133334df9a2298a`**，事前[CFD1协议](CAUSAL_DIFFERENCE_PREDICTION_PROTOCOL.md)。**首个3998×4设计OLS返回rank2，未达到事前rank4；全批停止，没有执行任何预测。** 原门不放宽，CFD1关闭；C4及C5–C7未验收，持续目标active。

## 首错与不可评项

8101评估map只使用8102/8103完整trial active1..1999；已保存X3998×4、Y3998×2、provenance和一次lstsq全部返回。返回rank `2`，singular values `[11.301656026171543, 5.449317616021822, -0.0, 0.0]`，RSS `[]`；解为 `[[0.008782237158378774, -0.006742057875672443], [-0.006821186281713415, 0.014098659447861372], [0.0, 0.0], [0.0, 0.0]]`。这些只转录[fits.json](../results/cpu_validation/2026-10-12_causal_difference_prediction/raw/fits.json)，没有重算SVD、fit、条件数或预测。rank2不满足本四特征候选资格，不证明所有身体模型或其余两fold也不可辨识；其余fold未执行。

| 评估seed | 训练seed | 保存状态 | 实际OLS | rank |
|---|---|---|---:|---:|
| 8101 | 8102/8103 | failed / available=false | 1 | 2 |
| 8102 | 8101/8103 | not_attempted / available=false | 0 | 不可用 |
| 8103 | 8101/8102 | not_attempted / available=false | 0 | 不可用 |

全部2073事前预测槽保留为not_attempted/available=false，预测流0records。新的67950pair/135900heads、8292评分scalar、42RMSE向量均未执行，不partial排名或把少步停止当效率。保存`cfd1_prediction_gate_passed=false`仅表示资格失败后关闭入口；**预测比较不可评**，没有新模型RMSE或20%改善结论。CFD2控制仍未开放，旧CF1/长时/控制失败保持。

## 实际费用与证据

原9000 compact区间完整资格，流身份/接触资格/同trial连续性/公共范围符合来源要求；输入9000行解码，不读取IV3大trace或CF1旧预测流。CF1cold84原RMSE+2保存H1均值直接转录，0cold forward/RMSE/均值/旧门重算。它们只是基线原件，不构成这批预测比较。

实际3998差分行、15992 X scalar、7996 Y scalar拟合用途；1OLS attempt/return、8解scalar输出，**0 adopted B系数、0冻结学习模型**。全设计3998行原件保留，拟合标签不是新采集/RLS。后续两fold无数据构造或fit，不把23988预算写成已执行。wall `1.1037194000091404` s，CPU `0.78125` s；未测lstsq内核/IO工作unknown。配置、runtime、源码ZIP、计账和全部未执行槽在[run原件](../results/cpu_validation/2026-10-12_causal_difference_prediction/raw/run.json)，首错误在[stderr](../results/cpu_validation/2026-10-12_causal_difference_prediction/raw/first_stderr.log)。

新物理/构造reset/RLS/教师/任务策略均0；正式累计保持 **544345控制/2824018子步**、历史 **125652 scalar RLS**。既有IV1、IV3、CF1费用保持，首CFD1这7996离线标签用途另列。一次[保存轻核](../results/cpu_validation/2026-10-12_causal_difference_prediction/delivery_checks.json)21项passed只核原件、源码、保存人口/成本/来源和cold转录，0数学重算，不代表科学资格通过。原件[checksum](../results/cpu_validation/2026-10-12_causal_difference_prediction/delivery_manifest.json)与source.zip可复核。

首次必要新合成2case passed，0fit/predict/原数据读，单固定B matvec另计。冻结前发现runner误填NumPy2.2.6，实际CLI与指定CF1保存runtime均1.26.4；只改版本literal和报错string，原检查未重跑。原runner通过两literal逆修复可精确匹配首check SHA并归档；数学函数不变。见[准备manifest](../results/cpu_validation/2026-10-12_causal_difference_preparation/manifest.json)。这次真实rank失败不是该已纠正版本配置问题。

## 下一唯一有限设计

关闭四特征rank4差分候选。下一方向是**只学习线性guarded请求G0/G1的2×2响应，公开固定hinge系数为0**。普通stateless motor没有实际`.25` hinge拐点，线性动作项是新的结构假设；不能把CFD1门降为rank2、复活原候选或以输出解中两行0直接宣称设计列为0。

先冻结一次只针对已保存首fit设计的列资格（0fit/物理/模型），核原X两hinge列是否精确0及返回rank2/有限。如果成立，可在独立新协议中显式复用这个已付OLS的两线性行，再对另外两个map执行新的两列OLS；不能不核等价边界就恢复失败candidate。三map全部资格后才另冻/执行2073匹配短时预测。保持相同crossfit、cold、全部H/seed/完整性与20%门，不scan比例/滤波/regularization/seed。原C4 20%模型贡献、5%强PD、1.05实际努力与新最终留出要求保持；提交推送后立即继续active目标。
