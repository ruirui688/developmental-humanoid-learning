# M之后唯一下一开发：N输入列RMS尺度ridge

依据M已保存摘要（clean4d10eac；公开结果fdee433），三个seed的K肩/肘q/v训练残差均shrink>floor，
L均floor>shrink；K/L数值rank均29/25/4。L条件动作能量保留比例虽降，绝对能量仍在，
不能据rank/比例断言缺激励。L同C的floor增加且C/G交叉项非零，不能期待单改尺度消除全局模型缺口。

父任务已确定唯一N候选：只复用K原C400、Phi29与delta22，逐列未中心化
`s=sqrt(mean(Phi²))`、`Psi=Phi/s`，同`.01` ridge求B，映回`W_raw=B/s`。
全部29列与22递归输出保持；scale须finite且>0，零即停止，无floor/删列/lambda扫描/更多数据。
K保存W及D sparse11 snapshot只恢复；两基线重新预测并核指纹前后不变，不重拟合K。
同一线性函数空间不变；RMS使训练幅度成为惩罚先验，微小非零列可能放大噪声与外推变化。

直接以原单位双门N→K和N→D否定：H1 v/H15 q逐seed严格改善且每轴三seed均值≥20%，
H2/H5 q/v及H15 v逐seed不劣，所有三组须完整固定分母。H1 q仅描述。
仅公共C prediction100及合法历史；原生q/v/六轴IMU、已知请求，原prior与22闭合不改。
新开发成本3 solve/26,400重复scalar标签/1,914独立系数；归一化尺度、矩阵、递归与基线调用另计，
物理/RLS/MPC为0。单次freeze开发，无再诊断层、候选扩张或补跑到成功。
旧K/D/L失败与scientific_adoption/C4/C5=false保留；通过开发仍需新留出与完整控制。

实现/协议/必要新合成草稿在`external/c4_scaled_native_staging/`，尚未执行actual或合成。
