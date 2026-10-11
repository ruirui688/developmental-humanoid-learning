# K 有限实现静态审查

结论：无阻塞、无必要修复，可进入首次必要工程检查。未改草稿或tracked文件。

- 拟合仅C calibration_sparse400；prediction数据不进设计/标签或参数选择。
- 八轴qref来自本trial完整、连续、未停止的100prefix末端；核cal/pred八轴一致及D的两轴qref。
- 完整history核同trial、step相邻、10子步、过去未停止及全22原生端点一致。
- rollout22只接起点/过去v/请求；未来22状态全部自身预测，previous_v推进为旧current v。
  q为独立残差输出，IMU没有回填未来实际值；cold22持久仅作披露的固定prior参考。
- window未来原生值只判可用性/评分，实际未来请求明确标为条件化输入，不宣称因果规划。
- H1/H2/H5/H15固定100/99/96/86起点；完整优先、两轴逐seed门与三seed均值规则吻合。
- source/input绑定、逐seed恢复attempt/return、拟合失败、预测失败/unknown及部分path均保留；
  外层失败flush已有参数/预测/不可用，并保留已读来源和未返回source的unknown声明。

未来shadow若改变请求，只能描述工程因果与动作差异；不能用真实终端作为同请求预测优劣标签，
不能让shadow过旧预测/控制门。控制收益仍需新冻结物理对照。

本次只读K草稿源码及一次git status；没有重读协议/旧数学、actualpayload、模型/fit/solve/物理或检查执行。
