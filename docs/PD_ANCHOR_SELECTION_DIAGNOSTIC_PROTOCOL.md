# FR4D：一次保存PD锚点资格与选择投影（冻结候选）

2026-10-12。本文件只为FR4B原门未全部通过时准备一项保存证据诊断；此草案不授权执行。主任务先完成FR4B首次结果公开与原判门，再将本协议及唯一投影工具静态冻结、提交和推送。诊断只执行一次，不新增物理、模型调用、拟合或科学门计算。阶段交付后持续目标仍active。

## 执行条件与唯一问题

FR4B正式判门以原 `docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md` 为准，包括完整性、接触域资格、模型贡献门和强PD门，阈值、人口和分母均不修改。若FR4B原全部采用门通过，**不执行FR4D**，另冻结C4新留出验收。若原门未全部通过，主任务在首次调用前记录已公开的未通过事实及其来源；投影工具不打开metrics来重新判门，也不把五个始终false的全局科学flags当作本诊断的执行判据。

唯一问题是：在原先保存的同一macro起点，预定PD锚点槽是否存在、是否可行、是否被选择，保存的chosen cost与anchor cost有何差值。主分析固定为learned全部600个计划origin；cold全部600个计划origin是事前声明的描述对照。两组各为3seed×A/B×100，不按可行性、阶段、cost或结果筛选。此项不检验PD实际反事实收益，不识别模型失配与cost偏好的因果贡献。

FR4D结束后关闭PD锚点/首请求网格微调族，不追加网格点、权重、增益、时距、seed或重跑FR4A/B。本次描述可以限定保存选择结构的判断，不能直接指定最相关的新特征或宣称失败原因。没有明确结构依据时，不自动开始另一轮参数微调；需要因果研究时另冻结单机制协议，C4及C5–C7前置依赖保持原判定。

## 固定来源、工具与身份

固定raw目录为 `results/cpu_validation/2026-10-12_pd_anchor_pair_control/raw`。唯一工具为 `external/fr4_selection_diagnostic_candidate/project_saved_pd_anchor_selection_once.py`，schema固定 `fr4_saved_selection_projection_v1`，诊断label为FR4D。CLI必须显式传入原FR4B完整40位source commit、冻结协议SHA256和一个此前不存在的新输出目录：

```powershell
python external/fr4_selection_diagnostic_candidate/project_saved_pd_anchor_selection_once.py --repo . --source-commit <FR4B的完整40位SHA> --protocol-sha256 <本冻结协议的SHA256> --output <首次新目录>
```

此处占位符在首次调用中由主任务替换为已经核实的值，不选择新bank。协议SHA由调用者绑定；工具记录该CLI pin，不再打开协议文件。原FR4B `experiment_id=FR4B`、`stage=control`、seed顺序8101/8102/8103、source commit及以下四项run保存pin必须一致，否则停止并保留首次失败，不进入投影。工具runtime从run绑定这些生产pin，不打开生产源码或weights：

| canonical文件 | bytes | SHA256 |
|---|---:|---|
| `src/developmental_physics/pd_anchor_pair_mpc.py` | 26614 | `d9053b7ae5a8eabca342d29558df7a67fae6cf21f60d6e18110256988f04b3e3` |
| `src/developmental_physics/pd_anchor_pair_development.py` | 56106 | `59de8ff3127bcdb683f325b11e5df88262bf8eda3e5a9f093de6bb9a204e1d64` |
| `scripts/develop_pd_anchor_pair.py` | 29329 | `7b7f9fda0bc98111b78dcefa5535e5e7efa563a6a2f0e827178dc80cf71f1a28` |
| `docs/PD_ANCHOR_PAIR_LEARNING_PROTOCOL.md` | 14616 | `ae9b8ea0515d3ff71ac8c636e08542fa7b19725c5746613acd5d619284978b1f` |

本次最终工具与静态schema说明pin如下；这些是准备身份，schema说明不会成为额外runtime输入：

| 诊断候选文件（均在 `external/fr4_selection_diagnostic_candidate/`） | bytes | SHA256 |
|---|---:|---|
| `project_saved_pd_anchor_selection_once.py` | 19311 | `e0cce0111b05c5b5e9514d38f5095b9dff922dfeddec226848426acf5fd44322` |
| `run_saved_selection_projection_first_once.py` | 3126 | `c6475566eef013323589c64de249dc714471d111adb0b4deec4da6b8575ecadf` |
| `schema_and_budget.md` | 4710 | `11d18ea66a1a5fd84fd1c98411aa88b5ab4d89089904049f0fd7a3418b34f7ae` |

只允许打开 `manifest.json`、`run.json`、`trace.jsonl.gz` 各一次。manifest/run用于文件身份、保存source与固定trial绑定；trace compressed bytes缓存后单次流解码最多36,000行。compressed bytes的本次SHA/bytes与manifest绑定，读取、解码及缺失行数另计。不打开metrics、models、predictions、source.zip、paid/audit/installed等payload，不恢复snapshot，不调用生产collector或controller，不读取隐藏动力学、未来实际力矩或实际轨迹误差。投影工具自身源码单次读取以记录bytes/SHA，作为单独source读取费用披露；最小firststdio launcher自身与投影源码的身份读取另列launcher费用，不能混入raw读取次数。

## 固定origin与缺失规则

trial固定 `FR4_8101_control_learned`、`FR4_8102_control_learned`、`FR4_8103_control_learned`，以及同seed的 `control_cold`；不读取PD/zero的decision或使用其实际状态作反事实。每trial要求原2000active微步完整，宏起点为 `phase=active` 且 `phase_index=0,10,...,1990`。A为0–999，B为1000–1999，各100个macro；原 `macro_decision_index=phase_index//10`、`residual_hold_micro_index=0`、trial/seed/transition/control_index身份保留。

所有1200计划origin都必须输出一条记录，12个seed×method×A/B cell各有100计划分母。缺失、重复、停止或结构不合法不得删行、补零或改分母；缺失native、decision、81候选population或anchor slot record产生该origin的NA和原因。保存停止前的合法结构事实，但未完整trial的统计不可作为完整控制排名；cell同时报告planned、saved、evaluable、NA与原trial完整状态，不用较少可评origin声称效率优势。

## 原生PD、槽映射与anchor存在

仅用当前origin的 `observation_before` 中原生两轴q/v和 `current_target_q2`，按原公共表达式恢复两轴PD：

```text
p[i] = clip(64 * (target[i] - q[i]) - 4 * v[i], -0.5, 0.5)
U = (-0.5, -0.375, -0.25, -0.125, 0, 0.125, 0.25, 0.375, 0.5)
j[i] = argmin((abs(U[k] - p[i]), k), k=0..8)
anchor_index = 9 * j[0] + j[1]
```

所有q/v/target有限且维度合法才计算。每轴只替换原nearest槽为p，保持原九槽顺序与axis0 outer、axis1 inner的81枚举，不排序、deduplicate或加点。允许生成完整81个**预期请求pair**用于槽索引与population结构描述，但只查看预定anchor slot的保存torque/feasible/cost；不得扫描其他槽寻找更佳cost或替代anchor，不访问其他candidate的feasible/cost。

首请求保持生产roundtrip `clip(p + (replaced_grid - p), -.5, .5)`，不暗换nominal或直接用grid等式。`anchor_present`仅指合法完整81 population中**预定slot**的两轴finite保存torque与恢复p精确相等；合法slot但不相等为False，必要结构缺失为NA。此定义不是全grid搜索，False不能解释为整个候选集没有任何同torque项。保存 `public_pd_request2` 若存在，只绑定其当前值与恢复p的关系；缺失不从未来端点或其他trial补值。

## feasible、chosen与保存cost差

仅在anchor存在时读取该slot保存的feasible；缺失或非bool为NA，False保留原保存rejection信息，不重新运行约束。`anchor_chosen=True`要求原decision非fallback、保存 `selected_residual_nm==(0,0)`，且保存selected first torque两轴finite并恰等恢复p。delta0但first torque缺失或不匹配为NA；合法非零delta为False。合法fallback为False，不把literal-zero动作当作PD，缺失fallback或选中残差为NA。anchor缺失/不存在时chosen资格仍标注NA，不能通过扫描其余candidate修复。

逐origin原样保留保存selected residual、selected first torque、selected cost与fallback；缺失为NA，fallback不补zero residual或cost。只在anchor存在且保存feasible=True、保存selected非fallback、双方保存cost有限时计算一次 `chosen_cost - anchor_cost`。双方cost缺失或非有限则差值NA；不重新算rollout、cost、tie、forecast、努力、SSE、RMSE或任何科学门。负值、零值、正值只描述原预测排序，不表示实际PD轨迹会更优。

汇总采用固定12cells，主learned与cold分列：present/evaluable/feasible/chosen的True/False/NA counts；feasible与chosen同时提供固定计划分母与前置可评分母，不把NA视为False。保存cost差只报告finite counts及描述统计；12cells内合计最多1200个finite值排序，q25/q50/q75用nearest-rank且不插值，所有缺失原因完整保留。不跨method、seed、native状态或阶段比较cost以声称因果，也不把不同状态的cost拼成PD收益证据。不新增科学通过阈值或优胜method排名。

## 有界计算与最小输出

预算上限固定，不随NA或结果追加人口：

| 本次费用 | 上限 |
|---|---:|
| 计划origin / learned主 / cold描述 | 1200 / 600 / 600 |
| 两轴公共PD恢复 / axis gain expressions | 1200 / 2400 |
| nearest scalar distances / nearest index选择 | 21600 / 2400 |
| 预期请求pair枚举 | 97200 |
| anchor slot record inspection | 1200 |
| `anchor_rejection_field_inspections`（仅present anchor的保存reason） | 1200 |
| `saved_public_PD_field_inspections`（字段存在性与finite保存pair） | 1200 |
| `saved_public_PD_comparisons`（finite保存pair与恢复p） | 1200 |
| 保存cost差减法 | 1200 |
| cell描述排序的finite值 / 固定cells | 1200 / 12 |
| raw文件读取 / gzip流解码 | 3 / 1 |
| trace解码行 | 36000 |
| projector自身source读取 / bytes | 1 / 19311 |
| launcher身份source读取 / bytes（自身与projector） | 2 / 22437 |
| 新物理控制/子步、model前向/rollout、fit/RLS | 全部0 |
| 旧/新RMSE、cost/tie、科学门重算 | 全部0 |

actual attempts/returns/NA及bytes、SHA、CPU/wall分列，不把未知I/O内部费用写为零。历史FR4A/B付费物理、规划、辨识与累计账保持原值，本次仅追加保存投影计算。投影仅输出 `<fresh-output>/projection.json`，内含固定1200 `origin_records`、12cells摘要、source/协议pins与实际预算/首次状态；失败另存 `first_failure.json`。最小 `run_saved_selection_projection_first_once.py` launcher保存capture根的 `stdout.log`、`stderr.log`、`first_execution_receipt.json`，投影目录为capture/result；launcher不读raw/协议、不算门，其自身和投影source身份各读一次、bytes和SHA另计。不新增复杂重复audit，不再重复原保存核验或报告writer。

首次失败、缺失或partial输出全部保留，不补跑到获得完整或漂亮分布。准备必要静态/合成检查与诊断执行费用分开，诊断过程中不修改工具、协议、映射或人口。此项最多一次；完成后公开保存选择结构及其解释限制，关闭本族，再由主任务沿C4→C5→C6→C7持续推进。`scientific_adoption`、`old_free_root_C4_validation`、`c4_scientific_validation`、`c4_contact_scientific_validation`、`c5_scientific_dependency_released`仍全部false。
