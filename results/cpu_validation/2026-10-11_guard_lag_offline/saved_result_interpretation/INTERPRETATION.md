# 首次 D 保存结果：只读解读

同开发数据；独立首审仍在进行。本文件不判科学门，不对停止控制排名，不宣称闭环通过。

三文件一次缓存读取：5770814 bytes。新增模型拟合/预测/物理/审计/Git/线性代数均0。

下表为 H1/H15 的速度RMSE比值（lag11 / 对应9D；<1为此保存轨迹预测更低）。括号为共同完整窗口数。

| seed | 原轨迹 | lag候选 | 肩H1 | 肘H1 | 肩H15 | 肘H15 | 原轨迹状态 |
|---|---|---|---:|---:|---:|---:|---|
| 0 | prediction | lag_sparse11 | 1.0537 (100) | 1.0397 (100) | 1.0198 (86) | 1.0220 (86) | completed |
| 0 | prediction | lag_continuation11 | 0.9412 (100) | 0.9423 (100) | 0.9827 (86) | 0.9803 (86) | completed |
| 0 | nominal_guard | lag_sparse11 | 1.1411 (200) | 1.1052 (200) | 1.0691 (186) | 1.0611 (186) | completed |
| 0 | nominal_guard | lag_continuation11 | 1.2758 (200) | 1.2536 (200) | 1.0501 (186) | 1.0492 (186) | completed |
| 0 | learned_sparse | lag_sparse11 | 1.1320 (106) | 1.1122 (106) | 0.9856 (92) | 0.9947 (92) | terminated |
| 0 | learned_sparse | lag_continuation11 | 0.7111 (106) | 0.7135 (106) | 1.1348 (92) | 1.1222 (92) | terminated |
| 0 | learned_continuation | lag_sparse11 | 1.1540 (4) | 1.1275 (4) | unavailable (0) | unavailable (0) | terminated |
| 0 | learned_continuation | lag_continuation11 | 1.0143 (4) | 1.0220 (4) | unavailable (0) | unavailable (0) | terminated |
| 0 | PDselected | lag_sparse11 | 1.2824 (200) | 1.0934 (200) | 1.0301 (186) | 0.9555 (186) | completed |
| 0 | PDselected | lag_continuation11 | 1.2915 (200) | 1.2544 (200) | 1.1685 (186) | 1.1446 (186) | completed |
| 0 | zero | lag_sparse11 | 0.9933 (200) | 0.9972 (200) | 0.9603 (186) | 1.0370 (186) | completed |
| 0 | zero | lag_continuation11 | 1.1570 (200) | 1.1570 (200) | 329.6336 (186) | 6.0010 (186) | completed |
| 1 | prediction | lag_sparse11 | 1.0484 (100) | 1.0359 (100) | 1.0180 (86) | 1.0205 (86) | completed |
| 1 | prediction | lag_continuation11 | 0.9404 (100) | 0.9409 (100) | 0.9839 (86) | 0.9824 (86) | completed |
| 1 | nominal_guard | lag_sparse11 | 1.0983 (200) | 1.0764 (200) | 1.0595 (186) | 1.0505 (186) | completed |
| 1 | nominal_guard | lag_continuation11 | 1.2196 (200) | 1.2087 (200) | 1.0366 (186) | 1.0372 (186) | completed |
| 1 | learned_sparse | lag_sparse11 | 1.1094 (106) | 1.0931 (106) | 0.9857 (92) | 0.9897 (92) | terminated |
| 1 | learned_sparse | lag_continuation11 | 0.7020 (106) | 0.7045 (106) | 1.1175 (92) | 1.1138 (92) | terminated |
| 1 | learned_continuation | lag_sparse11 | 1.1470 (4) | 1.1238 (4) | unavailable (0) | unavailable (0) | terminated |
| 1 | learned_continuation | lag_continuation11 | 1.0157 (4) | 1.0229 (4) | unavailable (0) | unavailable (0) | terminated |
| 1 | PDselected | lag_sparse11 | 1.2588 (200) | 1.1238 (200) | 1.0513 (186) | 0.9984 (186) | completed |
| 1 | PDselected | lag_continuation11 | 1.2572 (200) | 1.2299 (200) | 1.1871 (186) | 1.1579 (186) | completed |
| 1 | zero | lag_sparse11 | 1.0020 (200) | 1.0032 (200) | 0.9695 (186) | 1.0445 (186) | completed |
| 1 | zero | lag_continuation11 | 1.1963 (200) | 1.1924 (200) | 30.3453 (186) | 4.9237 (186) | completed |
| 2 | prediction | lag_sparse11 | 1.0540 (100) | 1.0400 (100) | 1.0200 (86) | 1.0221 (86) | completed |
| 2 | prediction | lag_continuation11 | 0.9557 (100) | 0.9583 (100) | 0.9772 (86) | 0.9740 (86) | completed |
| 2 | nominal_guard | lag_sparse11 | 1.1226 (200) | 1.1012 (200) | 1.0722 (186) | 1.0630 (186) | completed |
| 2 | nominal_guard | lag_continuation11 | 1.2229 (200) | 1.2283 (200) | 1.0443 (186) | 1.0458 (186) | completed |
| 2 | learned_sparse | lag_sparse11 | 1.1289 (106) | 1.1115 (106) | 0.9808 (92) | 0.9951 (92) | terminated |
| 2 | learned_sparse | lag_continuation11 | 0.7122 (106) | 0.7113 (106) | 1.1262 (92) | 1.1309 (92) | terminated |
| 2 | learned_continuation | lag_sparse11 | 1.1612 (4) | 1.1294 (4) | unavailable (0) | unavailable (0) | terminated |
| 2 | learned_continuation | lag_continuation11 | 1.0116 (4) | 1.0004 (4) | unavailable (0) | unavailable (0) | terminated |
| 2 | PDselected | lag_sparse11 | 1.2807 (200) | 1.1109 (200) | 1.0344 (186) | 0.9800 (186) | completed |
| 2 | PDselected | lag_continuation11 | 1.1725 (200) | 1.1452 (200) | 1.2089 (186) | 1.1768 (186) | completed |
| 2 | zero | lag_sparse11 | 0.9854 (200) | 0.9899 (200) | 0.9526 (186) | 1.0303 (186) | completed |
| 2 | zero | lag_continuation11 | 1.1293 (200) | 1.1285 (200) | 44.6550 (186) | 9.7097 (186) | completed |

JSON保留五predictor的各seed/轨迹/axis/H全部q/v RMSE、signed bias、最大误差、失败与窗口数，以及对应候选各项比值。H2/H5和不利结果没有省略。

Gram/系数/模态均直接摘录保存字段；未重新计算SVD、特征值或模型输出。单个局部谱半径不代表真实接触系统稳定性。

此初稿的研究解释待人工审阅上述正负结果补充；不得依据停止前预测误差采用控制器。
