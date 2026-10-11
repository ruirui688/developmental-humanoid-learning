# FR0 最小实现草稿

这里只是待发布源文件，未 import、未执行工程 runner、未运行测试或 fixture、未调用 MuJoCo/model/fit/RLS。旧 Z 源码与协议保持不变。

| 草稿 | 拟生产路径 |
|---|---|
| free_root_fast_feedback_environment.py | src/developmental_physics/free_root_fast_feedback_environment.py |
| validate_free_root_fast_feedback_engineering.py | scripts/validate_free_root_fast_feedback_engineering.py |
| test_free_root_fast_feedback_engineering.py | tests/test_free_root_fast_feedback_engineering.py |

环境继承原 GroundBodyEnv 的 step/reset/observation/保护，唯一构造配置为 control_substeps=1。审计 floor-pair 查询仅在完整返回的2ms端点发生，不增加积分或 forward、不写 observation、不供 PD 使用。每 floor 配对的一次额外 mj_contactForce（含 Fn<=0）分别计尝试/返回/异常；左臂、feet、other分类固定，力单位N。

runner固定seed7800与1000zero+两段各1000active的6s预算。先付费并保存原生 after/diagnostics，随后做新接触审计与StudyAbort；native和contact完整性分别保存。审计失败仍保留已付费端点、原生actuator_torque样本努力和已确认子步，接触缺失显式unknown/已知下界；不补积分。paid_journal按native条目、audit annotation和failure annotation绑定index，不能把annotation再次记作物理。

实际努力字段明确为actuator_torque端点样本×2ms，不暗称未知区间内连续积分。requested努力按全部已确认子步；audit失败不缩小actual native已知分母。接触比例用实际已付费阶段分母，缺失endpoint时为下界；完整phase的分母固定1000。

source_gate在创建新输出目录前核对clean精确HEAD，随后核对必要生产source bytes与git show。所有production imports与环境构造在该门后。正式protocol路径固定docs/FREE_ROOT_FAST_FEEDBACK_ENGINEERING_PROTOCOL.md；现只缓存external候选9381bytes/SHA41e9c323c51e4c3bc0e1f6cf4ea7e47c72b2c60777f3d8f2762839a0ff9011d3，`PROTOCOL_PIN=None`故不能正式运行。主代理只修正发布header后绑定最终字节pin，再做首次新纯检查、静态review和冻结提交；不先测试后改协议pin。

新tests只准备：公共权限/目标不可行、partial窗口拒绝、三phase接触及四MAE门、audit失败付费/native/努力保留、prefix无StudyAbort和active等号停止、wrapper保持原积分且audit无额外forward。它们只使用新纯函数、合成API端点或AST，不是物理实验/模型学习。测试路径以正式仓库布局为准，草稿目录中不能运行。

全局scientific flags均false。正式工程资格即使通过也只允许另冻结接触域辨识；旧C4、C5–C7及真机结论未通过。不编写后续学习recipe，不扫描seed/目标/增益/安装/物理，不自动打开真实采样。
