# 单肩冻结方案的新最终评价证据

[协议](../../../docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md)；[结果](../../../docs/LOCAL_FROZEN_VALIDATION_RESULTS.md)。clean `449079af0961d5dbc47afc9e26d9db424aafa947`，seed20/21/22首次执行后均为已见。

`final/`保存21完整trial原始字节：原生trace/子步遥测、计划及真实账本、模型/P/更新、源码/协议ZIP、依赖与内部manifest。6,000调用/60,000子步/900RLS、wall17.08101089997217s/CPU17.0625s；没有停止、异常、补跑。`collection_stdout.txt`为采集原输出。

`audit.json`/`audit_source.py`/`audit_stdout.txt`是首次独立标准库审计原件及精确源码：843,775 checks零失败，最大差6.590283874e−13，Git来源开启；wall7.369839200051501s/CPU6.625s。三门分别为同MPC贡献通过、PD比较失败、完整矩阵通过。

`summary.json`/`summary_source.py`/`summary_wrapper.py`/`summary_execution.json`/`summary_stdout.txt`保留第二位审查者一次只读汇总：56,411 checks零失败、内部wall.9615617999807s/CPU.90625s、外wall1.18640650017187s。精确源码bytes/base64、输入hash、命令和计时范围均在原件；0新物理/预测/RLS拟合，不覆写首次audit。

`tables.json`/`table_extraction_source.py`和`result_review.md`/`report_source.py`/`report_provenance.json`保存随后各一次表提取与报告。完整逐seed风险、1/5/15/50多步、覆盖、24尾窗及各自分母保留。`protocol_cross_review.md`为运行前审查原件；其中external路径按此README的映射归档，字节不重写。`archival_source.py`保存只复制字节/验证来源的脚本。

同MPC tracking降低29.5051543%；相对PD仅2.6743993%，未过5%门。full位置预测与闭环自身一步预测仍退化、q域外97%，prefix约553N峰与软限位小越界保留，不能称安全或全身技能。

[manifest](manifest.json)核对证据hash及17个ZIP/Git源码文件，累计正式物理208,850调用/2,088,500子步/9,900RLS，全部计算成本另报。后续固定左肘/肩—肘协调，不重跑当前留出调参，不结束持续目标。

若需要再次核验，输出新路径，保留首次原件：

```powershell
python scripts/audit_local_frozen.py results/cpu_validation/2026-10-11_local_final/final `
  --output external/new_final_audit.json
```
