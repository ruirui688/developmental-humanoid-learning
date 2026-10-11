# J 有限静态审查

已读 J 草稿脚本/协议及必要纯模型、C/G生成源码；无阻塞数据流或评分问题。未改草稿，未执行拟合或预测。

- 每seed只用C calibration_sparse完整400拟合；C prediction/G只评分，不进入训练或特征归一化。
- phi仅current observation_before六IMU；q/v、已知请求和连续过去端点构成基模型输入。
  actual_next只供actual-base_v标签/评分，不用未来IMU、实际力矩、contact/root特权状态。
- Phi400×6、Y400×2，normal6×6/cross6×2，一seed一次共享两rhs solve，共3次/36系数。
- D snapshot用trainable=False恢复，并核完整snapshot；末尾指纹检查，无base/RLS update。
  G只复用原learned_sparse11独立一步，并核指纹、q/v/request/previous_v/history；缺失不改为新predict。
- C/G native连续性与完整子步检查正确，当前完整停止端点保留、此前停止后不再提样。
  base/corrected共用同样本；主门只C共同prediction完整100，逐seed/轴严格改善、各轴三seed相对均值>=20%。
  G只描述，未以部分轨迹排名；科学门保持false。
- C flat manifest、G files manifest、D sparse snapshot和G model_input_diagnostics字段与生成源码一致。
  当前helper predict是纯运算，无模拟器导入；所有实际来源pin检查留给冻结后的首次执行。

有限提示（正常固定输入路径无阻塞）：

1. 作者正在修异常算术计数，尚未seal；本次不重复其必要小检查。
2. source_already_verified只有frozen_sources成功返回后才发布；身份检查早期失败会留下空对象。
   可沿I最小声明记录requested J commit、expected C/D/G pins，并明确未返回源码记录为unknown；
   inputs_already_read当前已通过外层共享dict逐文件保留。
3. frozen_base_restorations在三seed全部恢复后才+=3，失败时可能漏报此前已完成的恢复。
   若补全该账，只将attempt/return计数移入每seed恢复边界；不改snapshot、预测或评分。

本次G/C/D实际payload读取、模型调用、fit/solve/物理、旧审计及必要小检查重跑均为0。
一次源码定位查询引用不存在的scripts/diagnose_guard_lag_offline.py（rg exit2），没有执行该文件；
已从现有G恢复源码和纯模型确认相关API。静态源码读取有非零计算，wall/CPU未单独计量。
