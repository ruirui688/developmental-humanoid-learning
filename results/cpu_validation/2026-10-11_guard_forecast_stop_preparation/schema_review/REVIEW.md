# H 有限 schema/API 核对

结论：未发现阻塞 H 首次诊断的字段或 API 失配；不建议新增修复。封口草稿未改动，已过十项小检查未重跑。

只读取公开 G manifest.json、metadata.json、seed_results.json 各一次，共 652,432 原字节。
各文件原字节 SHA256 与 schema 信息保存在 schema_01.json；读取是明确授权的静态 schema 核对，
不属于正式 H 轨迹描述。trace、sourceZIP 和 first_audit 原件均未读取；模型、数学重放、物理均为零。
标准库 JSON/SHA 与源码检查有非零计算，墙钟/CPU未单独计量，不声称零计算。

核对结果：

- manifest.files 的 payload 条目确为 sha256/bytes；公开 manifest SHA 与草稿 pin 精确相同。
- metadata 所有 H 必需字段存在，study_abort_spec 和 environment_config.physics_dt 命名一致。
- seed_results 是三项 bare list；每个 trial fresh_prefix_bindings.reference_q 是长度二的 list，
  evaluations 包含 status/completed/study_abort/metric_control_step_count。H没有借用其他trial的qref。
- PDTailMPCDecision 继承 PairMPCDecision.to_dict/asdict，附加 trajectory_requested_torque；
  collector 的 _archive_record 将 tuple/NumPy 转为 JSON list。H selected H15 三轨迹消费与源码一致。
- collector 独立诊断 prediction 是 (2,2) 的 q/v pairs，以模型名称写入 predicted_next_qv。
  H 每个 trial 取同名独立一步，selected stage0另列；fallback不补selected。
- native observation 字段为 joint_position/joint_velocity，肩肘就是轴0/1；H只用这两个原生端点。
- environment 输出 executed_substeps 和 applied_torque_history（逐子步八轴），physics_dt=.002。
  H按实际存在子步积分absolute/squared努力，partial保留付费努力而主20ms误差null，
  history缺失为unknown。metric_control_step_count原collector只数完整10子步，H现有full_count正确匹配。
- H先用git HEAD/expected_diagnostic_commit及committed script/protocol bytes绑定自身，
  再以固定G91dcf6c、manifest/first audit pins绑定保存来源；不要求G数据存在于旧物理提交。
  first_audit archive/input_file_sha256/budget/final_gates字段已从生成源码确认，未重读/重算原审计。

范围仅字段和生产源码静态检查，没有新fixture、整档审计、轨迹统计或科研采用。无需修订封口草稿。
