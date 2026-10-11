# C4-A 身体学习审计核心交叉审查

2026-10-11。结论：本次审查范围内通过，没有发现阻塞提升的 joint adapter 或历史合法目标回归。当前肘部声明的增益仍为 None，正式肘 body 档案继续被拒绝；真实增益和新协议的冻结属于 root 后续工作，本报告不授权读取真实新 PD、20–22 或运行身体学习。

## 范围与原字节

读取 `external/c4a_body_staging/DELIVERY.md`，完整查看新旧核心 730 行统一差异，并复读改动所涉及的入口、来源、原生转移、风险、努力、RLS异常恢复、窗口与5/6/7门。核对生产 `src/developmental_physics/local_model.py` 的 planner 目标界限；相关新增合成测试仅作口径交叉核对，没有重复152项。

- 原 `scripts/audit_local_frozen.py`：`cfa33ae0703afac1861f9d1a6561cae4a5c7dbe64fb7d33e4229444cace9c966`。
- 新 ignored `external/c4a_body_staging/audit_local_frozen.py`：`272a88624edee38906efce070f64d1a5f20e26515ec7569a86a53db50a054a97`。

本次只新增此 ignored 审查报告，没有修改 tracked、核心或测试，没有提交/推送。纯标准库导入与断言没有导入MuJoCo或物理环境，没有打开真实档案、重放真实标签或读取20–22轨迹。

## 核对结果

1. `AuditSpec` 使用 frozen dataclass，seed/reset为tuple及tuple pairs；字典属性每次返回新对象，外部修改副本不能改变声明。默认肩声明直接固定j0、20/21/22、64/0和旧协议。AST核对全部函数后，旧 `SEEDS/RESET_SEEDS/PD_GAINS/FROZEN_FINAL_SCHEDULE` 没有运行时读取；六个主要入口/计划/门函数的默认参数都绑定同一个肩声明。没有全局赋值或观测重排。
2. `require_final` 先检查声明类型及 `require_frozen`，后读metadata。None增益、布尔增益及未冻结schedule不能进入ZIP或trace；suite/split/pose/joint/seeds/gain/protocol在来源前拒绝跨scope。CLI只有两个注册suite，没有自由joint/seed/gain选项。API显式声明属于可信源码配置，不能由archive自报配置反向构造。
3. 原生位置/速度、请求、实际history、公开range均按 `spec.joint_index` 传播。正常循环、StudyAbort、风险target屏蔽、努力恢复、conditional/tail、coverage、window/rollout，以及异常带item和无item RLS恢复都包含该索引。原8维顺序和qpos[7:]/qvel[6:]保持。剩余 `[0]` 分别是q/v二元坐标、限位下界、唯一异常命令、seed pair键、RLS矩阵/参数索引，没有遗漏的物理j0读法。
4. 特征/单输出RLS保持 `[v,q-qref,u,h(u),1]`。scalar prediction的第0维仍为q、第1维为v；RLS系数、协方差和特征维度没有改成物理joint索引。异常恢复仍要求完整native interval，item/noitem数学链使用所选关节；partial不能RLS或20ms主评分，已成功更新不因调用返回异常而自动归零。完整末计划转移触发停止仍不能complete。
5. source required集由静态base和所选协议组成；新肘协议替代旧肩协议，不能互相冒充。Git tree核验使用 `metadata.source_commit`，不是当前HEAD；旧档案不会被要求包含未来包文件。源码ZIP、SHA、Git原字节与输入不可改核验保留。标准库来源验证未改成导入归档源码。
6. 5个必要trial的same-MPC模型门、额外PD的6个trial门、完整7个trial矩阵都显式传播spec seed集合，阈值不变。PD/zero失败不删除有效的五trial模型贡献；zero失败可保留六trial门，七trial矩阵单独失败。默认肩门不接受development0/1/2伪装成最终seed。
7. 新MPC target gate是 `qref±.15` 与公共限位内缩.03的交集，和生产planner一致。负qref保持原值；目标非法直接拒绝，无裁剪。forecast容许公开限位外.03的原规则、9候选/H15、tie、cost与prediction计数未改。

## 本次新增的小合成核验

只执行一次纯标准库算术核验，未调用完整pytest矩阵：

- 8个合法planner输入逐字典与旧实现完全相等，含肩常见目标、负肘qref、public interior边界、local target边界、非零previous request、自身状态靠近域边界及较高速度；覆盖torque/cost/预测路径/可行候选/fallback/规划calls。
- 4个非法public/local target直接ValueError，未裁剪。
- `require_final`、`audit_archive` 两个入口的None增益都在不存在的合成路径产生冻结ValueError，未到metadata读取。
- AST legacy-global零引用、默认对象绑定和协议required-source隔离检查通过。
- 手造三个development seed的七种evaluation：全完整两门/矩阵通过；zero停止仅矩阵失败；再令PD停止仅保留五trial模型门；同一数据交给默认肩声明不能通过。所有值是人工合成，不是方法性能。

## 交付边界

数学与schema重构可提升至同一个原审计核心；不需要永久保留另一份完整审计轨，也不需要重算或更改旧肩档案。肘部正式运行仍需root在独立PD选择完成后一次冻结增益、来源与body协议，保持历史肩默认声明和原字节。新target gate对本次8个合法合成场景严格保持旧结果；这是代码回归证据，不是读取历史真实结果后的复验或安全结论。
