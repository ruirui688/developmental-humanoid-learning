# C4 L：固定数据增量开发记录

按[协议](GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_PROTOCOL.md)，从 clean `2dce248f23d5f2b622106ecfff94f0c33a6794cb`
首次启动。来源校验在 `D root/raw binding mismatch` 停止，尚无拟合、预测或科学分数。
这是来源检查的实现故障，不能解释为模型开发门通过或失败。

## 首次来源故障与保留费用

全部12个输入的固定哈希吻合，源文件及 clean commit 已核；D 归档根清单的 payload 记录含 `copy_verified` 等注释字段，
实现把完整记录与只含 bytes/sha256 的身份记录比较，误拒绝一致输入。
修复应只严格比较 bytes 和 sha256，继续保持文件整体 pins；不改变数学、数据选择、门或预算。

首次读取12文件/19,147,304原字节、解析10个JSON文档，9源文件/144,129字节、11次Git查询。
没有解析实际轨迹行，没有恢复K/D模型、生成拟合标签、求解或预测；新增物理/RLS也为0。
内部wall/CPU .538751/.171875秒；外层wall .767556秒。输入读取费用保留，不按0模型计算将它归零。

四个新增合成工程分支首次通过，没有重跑旧K数学。[准备原件](../results/cpu_validation/2026-10-11_guard_native_augmentation_preparation/manifest.json)
12payload，26次读取/174,062字节，复制零失败。

首次输出契约核对保留一个检查错误：它对来源失败且预测为空的运行要求完整3,429条记录。
该完成态断言不适用于本次来源故障；仅对此断言做[有限补充](../results/cpu_validation/2026-10-11_guard_native_augmentation/execution/c4_l_failure_contract_supplement_01.json)，
确认空预测符合尚未计算的状态，其余已过检查未重复。原检查、补充和源码全部保留。

[首次失败原件](../results/cpu_validation/2026-10-11_guard_native_augmentation/manifest.json)
15payload、30次读取/42,670字节，复制零失败；raw manifest SHA256
`6e73de28b8de76515196b9091ee62d7c412ff3b7642c34d80ae30b05756ec509`。
首次stdio、已读输入身份、失败manifest和空参数/预测均保留。

正式物理累计仍252,690控制/2,526,900子步；历史在线22,452和离线7,200 scalar RLS不变。
L拟合计算尚为0；后续修复须先提交精确新源码，再使用新输出目录，不能覆盖或表述为原首跑成功。
C4、C5依赖和科学采用保持false，持续目标仍active。
