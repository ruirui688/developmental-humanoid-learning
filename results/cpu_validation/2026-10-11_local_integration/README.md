# 同参数位置积分消融证据

[冻结协议](../../../docs/LOCAL_INTEGRATION_ABLATION_PROTOCOL.md)；[结果与限制](../../../docs/LOCAL_INTEGRATION_ABLATION_RESULTS.md)。仅development0/1/2，新最终20/21/22未执行。

`development/` 完整复制18个trial的原始字节，含原生前后状态、请求、子步遥测、RLS、所有预测/控制、源码ZIP、依赖、ledger与原manifest。采集源码clean `11410862f7cc450322d143abfd1eb7102a222212`，5,400控制/54,000子步/900更新，wall19.7389011001 s。

`audit.json` / `audit_source.py` 为首次独立标准库审计原件/精确源字节：707,642 checks、0 failed，最大差6.590283874e-13；12条历史原生锚点精确复现。审计wall9.7877663998 s、CPU8.78125 s，无新增物理/学习。采用门`validated_pass=false`，保留endpoint_euler；一致性通过不等于科研门通过。

`c2a_review_*` 与 `result_review.md` 保存第二位审查者的两轮离线指标复核及提取脚本。第一轮原程序文本从已执行命令保存，未另存管道传输字节，完整stdout和逐项记录缺失；initial_summary明确其来源。第二轮在运行前保存详细脚本，新产生1,440项带标签结果，不能冒充首轮原件。两轮各0failed、最大差9.9920072216e-16，wall分别2.1527191000/2.2457508999 s、CPU2.15625/2.21875 s；提取脚本时间unknown。全部新增物理/拟合均0。

[外层manifest](manifest.json)覆盖原始字节，不改原路径、dirty标志或嵌套清单。`result_review.md`原件的相对链接仍以原external位置为基准，其采集/审计在本归档分别对应`development/`和`audit.json`，不改写原报告字节。累计正式物理188,450控制/1,884,500子步/3,600 RLS；重放日志审计、测试与规划计算另报。

审计复现应写新文件：

```powershell
python scripts/audit_local_integration.py `
  results/cpu_validation/2026-10-11_local_integration/development `
  --reference results/cpu_validation/2026-10-11_local_learning/v2_development `
  --output external/new_integration_audit.json
```

后续单独冻结校准剂量/模型结构，不因本批负结果放宽采用门或重复揭晓新留出。持续目标继续。
