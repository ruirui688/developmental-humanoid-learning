# L 来源契约修复 01

首次正式clean `2dce248` 来源失败已保留于 `external/c4_l_native_augmentation_01`。
本修复不称该次成功；其0恢复/0拟合/0预测/0物理事实及已经读取的输入费用不变。

此次仅读取 D root manifest 身份结构：22159 bytes，SHA-256
`38df6b99e15c3667a33d6c9995a8efd664f70ce59be8a511fa49def59727a4d7`。
其中 `raw/manifest.json` 与 `raw/diagnostics.json` 记录均含 `original_path` 归档注释；
bytes/SHA与冻结pins匹配。全dict等于只含bytes/SHA的实际读取记录会因注释而拒绝。

新增纯函数仅逐字段要求 bytes 与 sha256 身份相同，用于D root/raw和raw diagnostic两处。
允许额外注释，但缺失/篡改任一身份字段仍拒绝；没有以copy_verified等注释代替身份验证。
原script、protocol和首INTEGRITY的精确字节已保存为before文件，script/protocol的完整diff单列。
所有pins、拟合公式、数据、递归及两个门未变。

只新增一次纯合成来源契约检查，覆盖额外字段接受、bytes/hash篡改、必要字段缺失和只有注释拒绝。
首CHECK与stdout/stderr保留；未重复原四枝、K数学或实际fit/predict/trace重放。
读取真实D snapshot、C/G trace、K weights，模型恢复、拟合、预测、物理均0。
