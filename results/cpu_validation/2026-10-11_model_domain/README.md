# C1 开发模型有效域归档

仅 E1 v1/v2 development seed 0/1/2；新增物理交互、RLS逐步调用、策略更新均为0。详见 [结果解释](../../../docs/MODEL_DOMAIN_RESULTS.md)。

所有报告按原字节复制，嵌入的本机绝对路径、源码 dirty 状态和时间均保持原样；本目录文件名映射及 SHA256 见 [manifest](manifest.json)。`public_*.py` 是公开 CLI 第三轮候选/第二轮多步分析的精确源码；其他源码是已保留的历史版本。

- `local_model_domain_development*.json` 与各自窗口 gzip 是两轮只读自由递推分析。各有28,116个重叠窗口，解压记录完全相同。首轮计算时间 unknown，第二轮的计时范围见 execution 字段。
- `local_model_domain_analysis_runs.json` 保留两轮计算账本和原路径。
- `closed_loop_development_diagnosis_public.json` / `.md` 是公开 CLI 重算；未带 public 的是第二轮原件。三轮累计36次岭求解、10,800次样本暴露、22.308 s wall；900个唯一转移。
- 第一轮候选诊断完整源码/报告未单独保留，仅后续历史中有脚本hash和成本。不能将第二轮或回构结果冒充第一轮原件。

重算必须使用新输出路径，不覆盖本归档或输入：

```powershell
$env:PYTHONPATH = 'src'
python scripts/analyze_local_model_domain.py `
  results/cpu_validation/2026-10-11_local_learning/v1_development `
  results/cpu_validation/2026-10-11_local_learning/v2_development `
  --output external/new_domain_replay.json
python scripts/diagnose_closed_loop_development.py `
  --output external/new_candidate_replay.json `
  --markdown external/new_candidate_replay.md `
  --history-report results/cpu_validation/2026-10-11_model_domain/closed_loop_development_diagnosis_public.json
```

多步输入是离线记录的未来请求序列，不能供在线控制提前读取。窗口重叠且复用相同seed；轴范围是覆盖诊断，不是安全集。候选回放没有执行自己的动作，不证明新闭环成功。
