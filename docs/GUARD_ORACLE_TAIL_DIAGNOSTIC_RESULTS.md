# V：固定尾通道闭合诊断未带来受控预测收益

2026-10-12，从干净提交 `7e1e5dd0cbaad322cdb9169cba07d10818649cfd` 首次执行一次，exit0，无重试。
[冻结协议](GUARD_ORACLE_TAIL_DIAGNOSTIC_PROTOCOL.md)保持 Q/U 模型不变；每步完整计算22通道，
只在非末步将其余18通道替换为同窗口实际未来状态。受控肩肘 q/v 及预测速度历史保持自身递推。

**结论：该干预没有改善受控预测。** Q 与 U 各12项描述检查均失败，H2/H5及H15的受控 q/v
在全部三seed略有退化。600个H1成对记录精确相同，固定4,572记录、192组均完整。
这是否定本次混合回放干预的收益；不能据此识别传感、支撑或接触的因果作用。

## 长时距位置结果

以下相对值转录首次保存的描述规则；负值表示 oracle18 比原自身闭合更差。
各行均为相同 source、相同 seed、相同窗口配对，未选择最佳 source。

| 模型 | seed | 肩H15位置相对改善 | 肘H15位置相对改善 |
|---|---:|---:|---:|
| Q | 0 | −1.348200% | −0.488553% |
| Q | 1 | −0.568746% | −0.162524% |
| Q | 2 | −1.442934% | −0.549456% |
| Q | 三seed均值 | −1.119960% | −0.400178% |
| U | 0 | −1.345426% | −0.567794% |
| U | 1 | −0.966972% | −0.366024% |
| U | 2 | −1.416988% | −0.775099% |
| U | 三seed均值 | −1.243129% | −0.569639% |

各source的20%描述幅度条件和其余时距不劣条件均未满足。原K/D科学门未重算，
旧Q/U开发结果不变；本诊断不接入控制、不验收C4、不解除C5科学依赖。

## 信息与计算边界

future18仅来自已保存U的H1实际端点，无C原始日志回退或新物理采样。
Q/U原自身闭合2,286记录、96受控组只转录；另新增2,286 oracle记录、96受控组。
末步18通道不替换、不评分；每步先检查全部22输出有限，替换不能掩盖非有限尾部。
未来状态可能包含受控运动信息，混合状态也不保证物理一致，不能用于部署或证明缺传感。

| 本次实际新增计算 | 数量 |
|---|---:|
| full22前向尝试/返回/失败 | 12,408 / 12,408 / 0 |
| 非末步18通道覆盖 | 10,122 |
| 未来18通道scalar标签用途 | 182,196 |
| 已计算但未评分的尾head输出 | 每source111,672，共223,344 |
| 新受控终点误差 / metric聚合 | 9,144 / 96 |
| 拟合、RLS、物理调用、MPC | 均0 |
| 原自身前向、误差、metric重算 | 均0 |

三seed Q/U前后指纹全部不变；未恢复K/D模型。正式源读取17文件/320,152bytes，
科学输入6文件/53,085,450bytes；对应hash字节同量，实际读取/恢复费用保留在run中。
原费用只作来源引用，累计物理仍252,690控制调用/2,526,900子步。
内部wall/CPU为4.2947398/3.46875秒，不含最终序列化与写盘；外部9.4376252秒。

## 原件与核对

- [首次执行与stdio](../results/cpu_validation/2026-10-12_guard_oracle_tail/execution.json)
- [原始运行记录](../results/cpu_validation/2026-10-12_guard_oracle_tail/raw/run.json)
- [逐组指标与描述规则](../results/cpu_validation/2026-10-12_guard_oracle_tail/raw/metrics.json)
- [逐窗口预测、历史及覆盖身份](../results/cpu_validation/2026-10-12_guard_oracle_tail/raw/predictions.jsonl.gz)
- [模型引用、公共guard及指纹](../results/cpu_validation/2026-10-12_guard_oracle_tail/raw/parameters.json)
- [原件归档清单](../results/cpu_validation/2026-10-12_guard_oracle_tail/manifest.json)
- [首次报告读取账](../results/cpu_validation/2026-10-12_guard_oracle_tail/reporting/c4_v_reporting_reads.json)
- [薄输出契约](../results/cpu_validation/2026-10-12_guard_oracle_tail/reporting/output_contract/report.json)
- [准备、首六夹具及静态审阅](../results/cpu_validation/2026-10-12_guard_oracle_tail_preparation/manifest.json)

归档10payload、20读/13,243,530bytes，0复制失败，wall/CPU .1296669/0秒。
报告只读五保存文件一次，186,859bytes/5解析，wall/CPU .0108797/0秒。
首薄契约8组全过，6读/6,623,818bytes、4,576JSON解析、58,765,151解压bytes，
wall/CPU1.3901324/1.375秒；没有恢复模型或重算科学指标/门，只确认保存的一致性。
root首次显示误找contract.json，正确文件为report.json；仅路径读取失败，未重跑契约。
显示派生摘要的准确读取字节/CPU未知，不补测或计作新科学计算。
结果导航239本地链接零缺失。附属stage20读/491,694bytes，seal15读/252,555bytes，
原raw/rootmanifest字节不变；[附属独立清单](../results/cpu_validation/2026-10-12_guard_oracle_tail/reporting/reporting_manifest.json)
保留报告、首契约、静态审阅和导航，均无科学重算。

## 接下来持续执行

按冻结分支关闭oracle路线，不追加通道组合或同bank优化。下一项形成一个有明确预算的新支撑域
双关节机制设计，区分支撑提供的能力、少量身体辨识与控制贡献，完整执行优先、原阈值不放宽。
新域结果只能支持该域，不能追认原地面接触C4；最终仍须回到完整接触控制并检验适应与成熟。
持续目标保持active，检查、报告与推送后立即继续下一项。
