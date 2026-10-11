# G 首审与薄汇总工具封口

仅准备工具；未执行审计、实际档案读取、物理、模型或统计重算。两个syntax/API字段存在检查通过，没有镜像fixture或旧数学/测试重跑。

首审wrapper：`run_guard_pd_tail_control_first_audit_once.py`，SHA256 `d94e927108e53dc037209cda35ae4264f4572b9d32d90dcc5d2be6cd49019866`。运行必须显式传入 `--expected-source-commit <clean G source commit>`；只调正式 `scripts/audit_guard_pd_tail_control.py`，input固定 `external/guard_pd_tail_control_20261011_first`。输出统一为 `external/guard_pd_tail_control_20261011_first_audit.json`、`..._first_audit_stdout.txt`、`..._first_audit_execution.json`；exclusive reservation、stdout/execution x模式和auditor拒绝覆盖保留一次尝试。wrapper保存自己的源码、auditor源码及首审输出SHA、外层wall/CPU、source/output读取字节和异常。

薄汇总：`summarize_guard_pd_tail_control_saved_once.py`，SHA256 `90311e2ea5b431bbf319c3c7579a62c7d07b6581d41a52ed4530804cd3d7aa14`。参数沿E：`--raw`、`--audit`、`--output external/guard_pd_tail_control_20261011_summary_01`、`--expected-source-commit`、`--expected-audit-sha256`、`--expected-raw-manifest-sha256`。保留E投影，新增仅复制 `audit.archive.paid_tail_request_accounting` 并声明G suite；不派生新统计、tail次数、预测或门。额外记录自身源码读入字节，四个实际input读取与source读取分开计账；失败独立保存first_failure.json。

准备读取：两E参考源码7371bytes；正式G auditor源码两次静态API查看152750bytes；新工具两份一次syntax/API查看12174bytes，共172295bytes（逻辑内容覆盖，非OS磁盘I/O）。参考原件、source记录与API_CHECKS原件均保留。最终INTEGRITY封存hash读取费用另记，不执行工具。

正式auditor API已静态确认`--input/--output`，新增字段位于archive层。当前工具不替代root首物理/首审授权，不改变科学门。G准备归档完成、clean提交首物理之后，root才能首次运行；不为封口预跑。
