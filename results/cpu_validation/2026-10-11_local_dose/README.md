# 校准剂量×身体模型结构开发证据

[冻结协议](../../../docs/LOCAL_DOSE_ABLATION_PROTOCOL.md)；[结果与边界](../../../docs/LOCAL_DOSE_ABLATION_RESULTS.md)。仅development0/1/2，不读取新最终20/21/22。

`development/` 完整原始27trial字节，包括两cal双模型的原生转移与更新、全部冻结预测/控制、子步遥测、成本ledger、源码/协议ZIP及依赖/manifest。采集源码clean `7a2462f2e5c9809f954ae49f3b34cc8411b5f4cc`，8,100控制/81,000子步/3,600 RLS，wall26.4389568998 s。只有1,800个真实校准转移，两结构分别处理同一轨迹。

`audit.json` / `audit_source.py` 是首次独立标准库审计原件与精确源码：1,319,376 checks、0 failed，最大差6.590283874e-13，12条原生历史锚点精确复现，Git来源校验启用并通过。wall17.5920336000 s / CPU16.203125 s，无新增物理/学习。全部新候选采用门失败，保留old_hinge5；一致性通过不授予科研成功。

`summary.json` / `summary_source.py` / `summary_execution.json` / `summary_stdout.txt` 保存第二位审查者一次只读汇总原件，内含源bytes/base64与输入hash。内部wall.1298293001 s / CPU.046875 s，外部含启动/写盘wall.3140223 s，0失败/重跑。完整候选门逐字段、因素差、覆盖/风险分母对账与逐seed原指标均保留。

`tables.json` / `table_extraction_source.py` / `table_extraction_stdout.txt` 是随后另一次只读提取，wall.0233199 s / CPU.015625 s，不重新预测、拟合或采集。`result_review.md`为审查原件，其相对链接仍以原external位置为基准；本归档的采集、审计与汇总分别映射development/、audit.json、summary.json，原字节不改写。

[外层manifest](manifest.json)保存全部SHA256、嵌套清单和累计账本。正式物理累计196,550控制/1,965,500子步/7,200 RLS；全部测试、规划与只读处理分开列报。

复现审计应写新文件：

```powershell
python scripts/audit_local_dose.py `
  results/cpu_validation/2026-10-11_local_dose/development `
  --reference results/cpu_validation/2026-10-11_local_integration/development `
  --output external/new_dose_audit.json
```

后续C2-C只重排相同命令总量，不能因本批负结果放宽门、追加剂量或提前揭晓新留出。持续目标继续。
