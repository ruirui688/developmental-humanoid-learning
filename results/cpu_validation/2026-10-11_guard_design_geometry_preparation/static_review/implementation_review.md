# M 有限静态实现审查

最终结论：**限定范围内无剩余阻塞，必需最小修复为无**。首份脚本的两项计账/失败保存缺口已按最小范围修复；最终仅重新核对新增计账及异常处理段，没有重审旧数学或扩大数据/检查。此结论不预判正式结果。

对象：`external/c4_design_geometry_staging/diagnose_guard_design_geometry.py` 与同目录 `GUARD_DESIGN_GEOMETRY_DIAGNOSTIC_PROTOCOL.md`。只读源码/协议，未读actual parameter/trace/预测payload，未执行代码、SVD、投影、fit、检查或物理；未重审旧K数学或旧检查。

## 首审缺口与修订确认

1. **完整投影估计的attempt/return（已修复）。** 首稿只有第一次坐标matmul的label用途计数，不能代表第二投影与残差已返回。最终稿分别增加native/command projection estimation attempt、return、failure；return仅在对应完整投影与残差形成后增加，原label用途与matmul费用继续分列。没有更改公式或参数。
2. **派生量失败保存（已修复）。** 首稿可能在严格JSON阶段才遇到非有限派生量，逃逸实验异常归档。最终稿以 `np.errstate(over="raise", invalid="raise", divide="raise")` 包裹整个 `diagnose`，位于既有捕获范围内；结合既有输入/SVD/矩阵乘法有限验证，使残差、平方能量、交叉项和比率等派生浮点异常在发布坏值前进入失败归档。已完成合法原件与付费operations保留，不转坏值为0，不重试实际计算。

同时确认新增全六套输入资格返回状态（验证器未返回仍unknown）、分列wall/CPU耗时及六次native/六次command估计预期成本；这些修订没有形成科学通过门或新候选。

## 已核对的一致路径

- **来源/输入隔离：** 固定K/L的manifest/run/parameters文件字节与hash；K/L completed、clean源身份和共有C/D绑定；L使用的K输入与本轮K原件一致。首次L来源失败仅绑定归档manifest，不读其failure payload。没有控制器helper导入、trace读取或旧rollout路径。
- **资格先于计算：** 三个有序seed、固定state/feature名称和`.01`、K400与L600完整训练IDs、L的C400/G200标签、finite float64形状；K400与L前400的Phi/Delta/qref逐值精确相等。不匹配直接停止，不修配。全部六套资格在任何SVD前完成。
- **固定计算：** Phi的机器精度ranktol、保留Ur投影与固定ridge shrink；Z为0…21/26…28，A为22…25。六套各3次SVD、6次矩阵乘法；无扫描、子组重拟合或参数空间新W。归档W只核训练残差，22输出均保留。
- **费用解释：** 六套66,000 native标签用途，另12,000 command投影响应及66,000归档ridge前向输出；当前matmul/SVD按实际形状、attempt/return与逻辑乘加请求计费。最低残差投影明确是新增无正则估计，不称零拟合或免费。
- **科学边界：** ALL和C/G子组记录floor/shrink交叉项、重构与原ridge差异；截断残差不当作唯一线性失败证据。单位分列、未汇总混合单位优势；纯训练几何不宣称泛化、动作因果或覆盖单因素结论，无新增科学门，旧K/L/D失败与C4/C5=false保持。

非阻塞解释注意：`A_perp`极小但非零时，按其自身最大奇异值定义的相对ranktol仍可能显示满秩；必须结合绝对/相对能量解读，满秩本身不证明充分激励。四基函数只有两物理动作通道，rank<4同样不能直接解释成两关节缺激励。

## 审查版本绑定

静态首读后，仅再次读取新增计账/异常处理和归档元信息段；未执行checks。确认时SHA-256：

- script：`a1003ca0b51af14d117ee0a459f159df3b8cd45a35ba72443b5e691919d31ec3`
- protocol：`b0735cd0544f81fe4f8a80d373ef691b4dc0d4e2ee418105da3ba93bd3f9bfbc`

哈希若随后改变，结论不自动覆盖新修订。本文无任何实际payload读取或SVD/fit/检查执行。
