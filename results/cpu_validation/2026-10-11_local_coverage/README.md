# 同剂量探索时序开发证据

[冻结协议](../../../docs/LOCAL_COVERAGE_ABLATION_PROTOCOL.md)；[结果](../../../docs/LOCAL_COVERAGE_ABLATION_RESULTS.md)。仅development0/1/2，无新最终20/21/22真实数据。

`development/`为原始21trial字节，包括原生trace/子步遥测、完整计划/实际账本、模型/P与更新、源码/协议ZIP、依赖及内部manifest。clean a2fe5c2c19602d759bd98b882000753036645432；6,300控制/63,000子步/1,800RLS，无停止/异常/补跑，wall19.30339359981008s/CPU19.171875s。采集stdout独立保留，timer排除导入/初始源码快照并在metadata说明。

`audit.json`及`audit_source.py`保存首次独立标准库审计原件与精确源码，963,372 checks零失败、最大差6.590283874e-13，12历史锚点精确复现，Git来源核验通过；wall11.625759599963203s/CPU10.25s。审计零新增物理/学习，重算更新不是新增辨识。

`summary.json`、`summary_source.py`、`summary_wrapper.py`、`summary_execution.json`、`summary_stdout.txt`保存第二位审查者一次只读复核：60,725 checks零失败，内部wall1.0529676999431103s/CPU.984375s，外部wall1.253389999968931s，wrapperCPU不含child。内嵌精确bytes/base64、输入hash、计时范围和命令；0失败重跑。

`tables.json`/`table_extraction_source.py`与`result_review.md`/`report_source.py`是随后各一次只读提取与报告，成本在原件中。风险和多步诊断保留自首次audit，summary不重新做模型预测或RLS数学重放。`protocol_cross_review.md`是采集前静态交叉审核原件，不代替实验审计。原review相对路径仍以external为基准，本归档按此文件所列映射保存字节，不改写原件。

覆盖与性能门均失败，保留short/old/hinge5/Euler。重排q域外93.5%、tracking均值仅改善0.422642%，low三seed退化。prefix约553N峰与软限位小越界均保留，零停止不证明安全。

[外层manifest](manifest.json)保存全部hash、嵌套清单、只读成本和累计账本202,850控制/2,028,500子步/9,000RLS。后续一次新最终评估，然后多关节；本批不结束持续目标。

复核审计写新路径，禁止覆盖首次原件：

```powershell
python scripts/audit_local_coverage.py results/cpu_validation/2026-10-11_local_coverage/development `
  --reference results/cpu_validation/2026-10-11_local_dose/development `
  --output external/new_coverage_audit.json
```
