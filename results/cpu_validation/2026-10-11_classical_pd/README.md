# 九组PD开发证据

[冻结协议](../../../docs/CLASSICAL_PD_DEVELOPMENT_PROTOCOL.md)；[结果与限制](../../../docs/CLASSICAL_PD_DEVELOPMENT_RESULTS.md)。仅development0/1/2；新最终留出未运行。

`development/` 完整复制原始采集字节，含全部27个trial、原生前后状态、请求/原始PD、qpos/qvel、子步遥测、计划/实际ledger、源码ZIP、依赖和原manifest。采集源码clean `abc537ae80e7101cec5a0c88e400c660b5655d9d`，8,100调用/81,000子步，18.186229 s wall，0更新。

`audit.json` 是首次独立审计原字节：255,331 checks、0 failed。验证全部候选及Kp4/Kd.2与旧v2 development的精确原生轨迹；所选candidate6，Kp64/Kd0，原始tracking均值.0163076221 rad。

`summary.json` / `summary_source.py` 保存首次标准库只读汇总及精确源码，3.262870 s wall、物理/更新0，全部候选与历史v2 development的full/prefix/control风险、真实努力、饱和及逐seed指标均公开。`audit_source.py` 是审计的精确源码。首次审计内部时间未测量，不回填CPU时间。[外层清单](manifest.json)覆盖本目录全部证据；内部原始清单保持原样。

审计复现须写新文件：

```powershell
python scripts/audit_feedback_development.py `
  results/cpu_validation/2026-10-11_classical_pd/development `
  --reference results/cpu_validation/2026-10-11_local_learning/v2_development `
  --output external/new_pd_audit.json
```

调优PD属于开发搜索，全部候选成本都计入；不能称它或跨历史开发对比为未见方法优势。风险峰包括付费前缀；控制期诊断单列。部分异常遥测如果缺失必须保留下界和付费成本；本批27trial均完整。
