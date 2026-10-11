# C4 提升后合成接口联调 01

结论：本次唯一执行完成 **352,150 项独立检查，仅 1 项失败**。唯一失败为 `clean_collection_source`，对应冻结前未提交源码；其余原生布局、公开限位、数学、日志与成本检查均一致。没有忽略或豁免任何非 dirty 差异，也不报告正式验证通过。

本次明确使用 tracked `SyntheticEnv` 和原始 `FixedPairMPC` H15/81 数学。没有调用真实 GroundBodyEnv、MuJoCo step 或真实机器人。development seed 0；每 trial 100 prefix、calibration 400 active、两个 prediction 各 100 active，控制长度显式缩为 2。nominal 第一个 active 返回端点注入肘速度恰好 1.0 的 StudyAbort；该完整 terminal 端点仍评分，但 nominal trial 不完成。其余模型与控制按既定顺序继续。本 fixture 不能替代正式三 seed、200 active 控制评价。

| 记录 | 合成值 |
| --- | ---: |
| attempted / returned control | 1,409 /1,409 |
| 合成 physics substeps | 14,090 |
| committed scalar /vector updates | 1,600 /800 |
| 独立检查 /失败 | 352,150 /1 |
| **真实物理预算增加** | **0** |

原生 8D q/v 与 qpos[7:]/qvel[6:] 精确一致，两个目标轴权限及其余六轴零请求得到核验；公开 rad 范围与资产一致，原生略负的肘 qref 未裁剪。两模型的完整 RLS/P、冻结参数、81 候选精确 MPC、实际努力、phase/trial/batch、完整 terminal 与未完成状态均通过一致性检查。无需将旧 fake layout/range 或 stub planner 差异放宽为可接受。

两审计脚本及 collector/core 都存在于原字节 source ZIP，metadata SHA 与本次执行源文件及 ZIP 字节逐一匹配。动态 common 依赖还通过 `audit_dependency_sha256` 单独记录。全部 tracked 输入在执行前后 hash 稳定。

源码 commit：`46077b1d30089d68f1c935e3fc547dfdfa4c4e66`，dirty=true。合成审计明确 `git_root=None`，不声称 dirty 源码能与该 Git commit 的 blob 完整一致。ZIP/SHA、原生数据与独立数学仍完整校核；只保留 dirty 源码失败。所有正式 `validated_pass` 均为 false。

本次 collector 墙钟 2.323939 s；独立审计 1.982656 s；driver 总墙钟 4.777220 s、当前进程 CPU 4.453125 s。driver 计时不含进程启动、driver 首次导入及最终报告/hash 写入；审计另有自身精确计时范围。这些不增加真实交互预算。

未修改 tracked 文件或 Git，未运行普通 51 项审计测试，也未读取真实 PD、20–22 或 pair 物理档案。没有重新执行本 fixture。driver 的 sentinel 拒绝在同一输出目录重复运行。

执行命令：

```powershell
external/cpu_physics_env/Scripts/python.exe external/c4b_pair_promoted_schema_01/run_promoted_schema.py
```

交付包含 `run_promoted_schema.py` 原脚本、`tracked_fixture_source.py` 原字节 fixture 快照、`stdout.txt`、`execution_started.json`、`execution.json`、`audit.json`、独立 `archive/` 和 `hashes.json`。archive 内的 manifest 未被修改，报告与 driver 文件位于 archive 外，不破坏其精确覆盖。

UTC：2026-10-11T06:59:45.900429+00:00

| 关键文件 | SHA-256 |
| --- | --- |
| `run_promoted_schema.py` | `73ee2fdc413f5b43331222b2160c856ff6d2029bc471650b10917f04fc02ec9b` |
| `audit.json` | `0a8ac227d1b854e502077c8ad198e7ae8f728c7ce5795a86af369b201cfe1f01` |
| `execution.json` | `d8bc59e286f087c78dfbaada61fec56ee504b6fe080e6579c94117c4f1f5845d` |
| `stdout.txt` | `326f271552976dfa276ba62ccbf6c489223d8bdc30599b778b98d295e52b39be` |
| tracked `scripts/audit_pair_frozen.py` | `53f220f229f234d573dd7c867a7491b3da3ed5c68c43a084a59da4393f2a2c23` |
| tracked `scripts/audit_local_frozen.py` | `b5fea70d3733a1bab77e49bf559432475899436693cf6c1b0b4767369c913461` |
