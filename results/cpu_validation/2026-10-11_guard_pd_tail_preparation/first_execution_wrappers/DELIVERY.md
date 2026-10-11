# G 首次物理包装器工程交付

2026-10-11；只写 external/c4_g_first_wrapper_staging/，未改 tracked/canonical 文件，未执行 wrapper、子进程、模型、数学、实际档案审计或物理。

包装器：run_pd_tail_control_once.py，SHA256 `1bbcb4bd8d1dbb15c86c729a6d0c0e576e00c2673ac0a3604396b646de92775e`，3907bytes；同字节 original.py 已保存。旧 E 包装器原件 SHA256 `c33d7ca80380e31bbe6507725760dbaf0dcd2a158fa6d02d998bf8392ce5fd89`，3154bytes，仅作为源码参考，未执行。

运行时必须显式传入 `--expected-commit <exact clean SHA>`；未知正式提交没有硬编码。root 管理正式入口和开关，启动模块 `developmental_physics.pd_tail_control_development` 的 main，再调用 run_pd_tail_control_development。单线程 CPU 解释器路径沿原 external/cpu_physics_env/Scripts/python.exe。

统一独占输出根为 external/guard_pd_tail_control_20261011_first，外侧分别为 _runtime_source_freeze.json、_stdout.txt、_execution.json。沿原机制校核 HEAD/clean status、工作源码原字节与精确 commit Git blobs，拒绝已存在的任一输出；源码 freeze、合并 stdout/stderr 原字节及外侧 child status/exception 使用 exclusive 创建，不覆盖失败原件。

source 列表包含全部 physics Python/assets、G新独立审计、E原审计+原5支持、G协议与pyproject。staging 深度变化改用 pyproject 祖先寻找项目根。源码校核 opens/bytes 与 Git blob 次数/返回 bytes 单列；该成功 source freeze 阶段模型/更新/物理0，不把 child 真实物理说成0。

外侧 wrapper wall 沿原 child-launch 机制，明确排除源码/Git preflight、末 execution 写盘和打印报告读取；子进程费用与实际物理/规划/tail成本由 child 原件另记。前置 clean/byte/assert 失败会按原机制在 child 启动前退出；此工程没有扩展或执行新失败框架，也不据较少交互称学习或安全收益。

## 仅必要静态核查

STATIC_CHECK_01.json 首次 **9 passed /0 failed**：新模块、新统一路径、新源依赖、必选CLI、staging项目根、语法以及原 clean/exclusive、Git byte equality、combined输出/child launch AST 保留。只是 parse/compile/AST，不 import/execute wrapper；原数学、旧审计、物理没有复跑。

显式读取旧E/newG源码2 opens/7061bytes，wall .010607599979266524s；范围含这两份源读、parse/compile和静态检查至报告组装，排除末JSON序列化/写盘。工具exec wall .5214228s另含启动与输出范围。此前一次 Get-Content 旧E源码及文件名查找为静态阅读：首次广范围文件名输出被截断，随后root给精确旧E源码路径；这些不是实验数据读取或实验调用，不虚构为0源码工作。

原件、静态检查源码/结果及本交付说明由 INTEGRITY.json 一次封口。正式 clean commit 后是否首次启动由 root 执行，不自动启动，也不重跑小检查。
