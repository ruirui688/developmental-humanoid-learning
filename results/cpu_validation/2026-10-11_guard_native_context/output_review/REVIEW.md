# F 首次保存输出的有限契约核对

2026-10-11；F 从 clean `734ab7dab53563327b7dc072378551d2045b68ac` 首次完成。本次只读取该 F 的 manifest.json、run.json、description.json 及其原字节副本，不读取 derived、trace、E/C/D 数据，不执行 diagnostic，不重算 Pearson、norm、均值或旧数学。

首次有限检查共 **50,255 项 / 24 失败**，原件及 FIRST_OUTPUT_CONTRACT_CHECK.json 原样保留，没有重跑 F 或补跑检查到通过。唯一失败类型是 24 个 `learned_sparse11/earlier/B` 空分段没有非空 `empty_window_reason`：三个 seed、两轴、两个 predictor、q/v 各组合。检查器要求每个空分段有显式原因；原协议可能只要求整个 earlier 窗口为空时说明。因此这是需要 root 判定的描述契约差异，不能未经判定声称 F 原统计错误，也不能删除此次失败或追认本首次检查零失败。

这些分段的保存样本数为 0，配对/bin 分母及 Pearson null 原因的核对均通过。原 F 数学、描述结果和科学门不修改。科学采用仍 evaluated=false/passed=false，关联与分层不能解除 C4/C5 或追认 D/E 科学门。

## 有限核对范围

- manifest 所列 run、description 的实际原字节 SHA256 与 bytes 相符；derived 只用于 manifest 已存 bytes 加法，未读或验证 derived 内容。
- F 保存来源为上述 clean commit，source `15ffc878f918a7927b09c5ede14b6ac5b57b09bab43b4ff4342ac11a20cdff96`；绑定与协议 SHA 保存一致。此次没有另读 Git 或源码，属于保存身份核对。
- manifest/run/description 的 scientific_adoption 均 false；保存费用中物理、模型 predict、RLS、策略/增益/门控更新及 C/D raw reads 全部 0。F 本身仍有描述计算和读取成本。
- 288 分组的条件笛卡尔键无缺失/重复：12 trial 各有两轴×两 predictor×q/v×A/B 的 all；三个 learned 停止 trial 另各有 tail20/earlier。864 score 统计块、12 event、24 input-quality 分组的键与分母一致。
- 完整区间+partial=returned、returned+unreturned=saved，score valid+missing=saved，paired+missing-with-valid-error=valid-error。所有保存 bin n 加总为 paired，bin fractions 使用 paired 分母；没有重算 bin 所含数值或相关性。
- 保存 active 合计 2,112，partial=0；三个停止 trial 各 104 active、tail20=20、earlier=84，terminal ID 为 step203。A/B 分段的 all=100/4、tail20=16/4、earlier=84/0；其余九 trial 全部 200 active。
- 原 E 四 gate 结构、各三 seed 行、轴/努力字段与未评价/未过状态保留；原预算 3,312/33,120、0更新，事件预算相加一致。未重新读取 E 原件或重算其门指标。

## 原件与费用

| F 文件 | bytes | SHA256 |
|---|---:|---|
| manifest.json | 1868 | 4363934feadb964839ebfaeb902342262aeac70b428e10e3ce3bb17262875565 |
| run.json | 12842 | fc90269c3a72dfd6d7eb144b8907f57b6f38b1e171e55fb7b29c3c1b99e98540 |
| description.json | 3171743 | 26c90bbb0cf2c8197f3b5ecd5722a87a645c288810cb0ff895e4224c56a63413 |

输入首次读取/快照 3 opens、3,186,453 bytes；一次有限检查再读这三个快照，合计 **6 opens / 6,372,906 bytes**。另有首轮三个文件 metadata path queries；三个原字节快照写入 3,186,453 bytes 单列。无其他实验数据读取。

首次 read/hash/JSON parse wall `0.022004200145602226s`；本次 read/hash/parse wall `0.040528299985453486s`；一次契约检查 wall `0.06086000008508563s` 包含本次读取与结构/代数检查，不含结果序列化、写盘、stdout 或人工阅读。工具 exec wall 分别为 `.4951981s` 与 `.7949042s`，含启动/输出范围，不能替代完整人工审阅计时。INPUT_SOURCE_RECORD.json 与 FIRST_OUTPUT_CONTRACT_CHECK.json 保存这些费用及限制。

本核对没有新科学统计计算、模型、物理、拟合或旧审计；整数计数加法与 bin 配对分母除法只检验保存契约。未自动修 F、重跑或为得到零失败更改原检查器。原输出及此首失败先封口，后续若说明契约差异应另留补充，持续推进有依据的 G 独立控制审计工程。
