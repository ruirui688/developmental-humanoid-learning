# I 有限静态审查

已审阅 `external/c4_h_residual_diagnostic_staging/diagnose_guard_pd_tail_native_residual.py`
及同目录协议；未改草稿。无阻塞的信息泄漏、评分或分母问题。

- current corrected q/v 只取 current base 与 previous 原 base 速度残差。
  current actual 仅评分，随后才发布 original-base 残差；没有递归 corrected 残差。
- previous 按固定 trial 隔离；首行不补零，partial/missing 清除历史，非连续当前行只重建历史。
- base/corrected 同 pair 评分；ALL 每 pair 仅计一次。A/B按 current active，cross另列。
- 速度主门逐 seed/轴严格改善，各轴三个 seed 的相对 RMSE 改善算术平均至少20%；
  空或零baseline不能通过。cold同门独立，q/其他分段没有替代主门。
- I 自身canonical路径、HEAD与两源码 committed bytes校验独立于H/G冻结身份；
  四份允许H输入绑定和窗计数不访问G或额外H文件。

非阻塞来源提示：异常 failure.json 目前只有exception/cost，不带已验证的I own_source
或load_h中已读inputs；成功run身份齐全。若主任务补全失败溯源，最小做法是让读取身份
增量写入run层状态，并将已取得的own_source/inputs及固定H/G commit纳入failure，
不改变修正/评分/分母，也不需要重跑已过八项检查或读取实际数据。

本次只读上述两份准备文本及一次git status；G/H payload读取、模型调用、数学执行、物理、
旧fixture和八项小检查重跑均为0。源码静态读取有非零计算，wall/CPU未单独计量。
