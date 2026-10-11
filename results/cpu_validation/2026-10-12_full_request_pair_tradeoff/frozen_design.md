# FR3B 唯一下一项：一次保存轨迹的轴与阶段描述

这是供 root 实现并冻结的一次诊断设计，尚未执行或读取任何 raw、结果、模型参数。
依据仅为 root 已给事实与公开冻结源码：模型贡献原门通过；正式 PD 比较中肘跟踪
退化18.1937%，两项实际努力门失败。完整12条/36,000步及首审660,047项零失败已建立，
本诊断不再核验或改判科学门，不自动实施下一控制器。

## 固定输入与人口

只读新 FR3B `manifest.json`、`run.json`、`trace.jsonl.gz`，各一次；压缩轨迹缓存后
一次正向解码，最多36,000行。绑定本次 manifest 的 run/trace bytes/SHA，只做输入身份
检查；不打开 models、predictions、journal、source ZIP、FR3A或任何旧 raw。

主人口固定为8001/8002/8003 × cold/learned/pd九组，active最多18,000个起点。
12条轨迹的prefix/active解码数可保留，但zero不进入本诊断比较。固定主组全列出，
缺失字段保持NA；已有完整性证据不授权填零、部分排名或更换窗口。

固定四个 scope：A active0–999、B1000–1999、switch_pre900–999、switch_post1000–1099。
后二者各为200ms固定窗口，分别包含在A/B内；不得扫描窗口或按峰值重选。

## 两轴跟踪与实际努力

直接使用已审计的保存 `target_error_rad` 和本步保存的2ms原生 actuator torque端点。
对每组/每scope/每轴描述：已知/计划数、sum(error²)、signed mean、MAE、max abs error，
以及 `sum(abs(actual_torque)*.002)`、`sum(actual_torque²*.002)`。
不重算H预测、模型、目标标签、旧full RMSE或科学百分比。full2000既有axis/joint RMSE
及实际努力axis摘要从run直接转录，明确其来源。实际努力是保存端点样本积分估计，
不称连续积分、能量或安全收益。

同seed的learned−PD两轴A/B SSE与abs/squared努力差分，描述哪一轴、哪一phase贡献
不利差异；cold仅作本实验参照。固定switch窗与所属phase之比只描述损失/努力是否集中
在切换附近，分母零或未知保持NA。不同方法实际状态不同，不把同index差分称作匹配
状态反事实或因果贡献；不把MSE差分当作原三seed RMSE门的新百分比。

## 宏首请求网格的有限描述

仅六条cold/learned的最多1,200个保存macro。使用其保存 `public_pd_request2`、
`selected_residual_nm`、fallback；fallback没有保存PD时保持未知，不重新算PD。
每macro/轴对固定九点grid计算一次最近距离，作为可选残差的最小绝对幅度描述；
同时记录已选abs(delta)及其超过最近距离的部分，并按相同四scope描述。

纯PD候选的集合存在性定义为：两个保存clipped PD值都**精确**属于九点grid，因而
存在delta=(0,0)。存在时只读取该固定index的一个已保存candidate feasible标志，
不重放可行性、cost或tie。分别列出存在、缺失、未知和存在但不合格的分母与计数。
这是当前native起点的候选集合事实，不能移作另一方法轨迹上的PD反事实。

grid只规定macro的首请求；后九步actual native PD继续变化，不能把全部2ms请求称作
量化动作。相同首请求也不证明后续候选路径相同。最近grid距离/纯PD缺失与不利误差
或努力同现，只提供开发描述，不能认定它们造成退化。

## 新工作上限与输出

- 36,000解码行，九主组18,000active记录。
- 九组 × 四scope × 两轴 =72个轴统计cell；共19,800次row-scope投影、39,600次轴更新。
- 最多1,200 macro；最近grid距离最多21,600次scalar abs距离比较；最多读取1,200个
  对应purePD candidate记录，不再次遍历/审计全97,200候选。
- macro统计最多1,320次macro-scope投影、2,640次轴投影。固定窗口及NA人口原样保留。
- 单个JSON报告及自身wall/CPU、读/解码bytes、上述实际完成计数；失败只保存首失败和
  已完成人口，不自动重试。0新物理/更新/fit/模型/PD调用/rollout/cost/tie/旧gate重算。

下一判断只回答：肘跟踪与努力不利差异集中在哪个固定轴/phase/切换窗，当前候选
集合的最近距离与purePD存在性是什么。若purePD通常已存在且可行，不能继续把失败
统称为缺purePD；若不存在，也只能提出另行冻结的机制问题。不得由相关性直接扩grid、
改权重/增益、扫参数、增加辨识剂量或宣布找到原因。C4/C5及五科学flags不改变。
