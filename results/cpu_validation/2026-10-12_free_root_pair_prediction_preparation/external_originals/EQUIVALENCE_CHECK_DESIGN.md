# 固定语义批处理 MPC 外部候选

本文件及实现尚未执行。候选只用于待冻结的新自由躯干协议，不能改判 Z2，也没有 20 ms 实时证据。原实现和数据保持原结论。无需新增库，沿用已有 NumPy。

## 保留的控制语义

- 原 9×9 residual `product` 顺序、81 个候选，H150 个 2 ms 预测步；前 10 步 residual 不变，后 140 步为原 PD tail。
- 原 PD64/Kd4,4、两轴 ±.5 Nm、当前目标、成本权重、首步完整请求变化成本、每轴逐阶段 Python float 累加次序。
- 原 KnownAngleGuard 在每个预测步重算，公开边界等号阻止向外力矩；不 clip q/v，不改步长、任务、门或候选。
- 位置 forecast 包含等号，速度 `>1.5` 才拒绝；先位置后速度，guard 失败仍计成功预测但不追加 trajectory。非有限成本是在追加该步后拒绝。
- 原 Python `min` 键完整保留：cost、首请求绝对值和、signed 首请求、signed residual、trajectory。无 feasible 候选仍是 literal zero fallback。
- 成功决策的 pair/scalar/feature/PD/candidate 与每候选拒绝计数保持原单位。淘汰行从下一阶段移除；没有 extra pair/scalar returns。独立 `last_batch_execution` 记录实际 stage kernel/feature row/dot，不代替原逻辑费用。

## 归约与合法模型

批处理仅替换无归约的 PD、公开 guard 与九列 features。每个活跃行仍构造原 two-head 九列 feature 布局、调用原 `_predict_output`，使用同一个九元 float64 向量 dot；Euler 也保留原二元素表达式。不用矩阵乘法、einsum、矩阵 sum 或累计成本归约。成本仍使用原 Python 表达式、幂运算及轴顺序。因而没有主动引入不同的 dot/cost 归约次序。

支持 exact FastFeedbackGuardCoupledPairBodyModel 和 exact CountedGuardModel（标准 Counter、原方法）；正式 CountedGuardModel 可以进入批处理，特征与 pair 计数显式保留，scalar 计数仍经过其原 head 包装。新自由躯干 collector 的 CountedGuardModel 通过显式 `counted_model_type=NewCountedGuardModel` 接入，不依赖模块名称；要求完整 class AST 被 root 冻结为与原类相同，候选另核相同父类 MRO 及四个计数包装方法的字节码。部署 caller 必须传入新类，否则会显式记录 fallback。其他模型、改写方法或候选网格进入原 scalar select，必须披露 fallback 是否发生。部署前检查完整选择过程没有模型状态发布变化。原方法依赖的 Python/NumPy 源码身份必须一起冻结。

候选按 stage 运行各行，原实现按候选完成全 horizon。纯确定性有限模型及已知 ValueError 预测拒绝的最终控制、记录和费用应相同；原代码没有对 Counter 的中间观察回调。异步中断、分配失败等非数学异常的已执行前缀会因执行顺序不同而改变，必须保留实际新前缀和 attached accounting，不宣称与原前缀相同，不自动重试。自定义可编程异常模型使用原路径。有限合成通过不能证明任意硬件/NumPy 版本逐位一致或真实闭环收益。

## 首次有界合成检查

root 审核并冻结后，执行脚本一次，写入全新 output；此处不执行。11 固定 fixtures，每例一个 reference 和一个 candidate，最多 22 次选择、267,300 logical pair attempts、534,600 scalar attempts；物理、RLS、snapshot restores 全零。系数仅为脚本公开常量，不读旧保存模型、轨迹或 FR0 raw。

fixtures 为 generic prior、有限耦合、混合早淘汰、head0/head1 overflow、forecast 等号、仅一个 ULP 越界、公开 guard 等号、精确 residual tie、未知 fake predictor 原路径回退及新域 Counted adapter。新域只从已 pin 的 collector 源码抽取相同 class AST，在纯数学 namespace 定义，不导入其物理环境。始终使用 81/H150，不缩小候选或 horizon。输出完整 decision 的 JSON float 表示需一致（包含 signed zero），CountedGuardModel cost 与 forward_counts 需一致；`allclose` 不能使失败通过。混合淘汰应恰好 82 pair returns，两个溢出应分别只有 81/162 scalar attempts，精确 tie 应保留 25 feasible 并选 (0,0)。任何首次失败保留并停止后续 fixtures，不重跑到通过。

计时逐例包括完整 select 与 decision 构建；只用于合成 CPU 费用描述，不设加速通过门、不宣称 20 ms deadline。必要新检查通过后，root 可单独决定是否把候选与新域协议同时冻结；未通过则保留外部负结果或进行有依据的单次修订，禁止用于正式物理。

计划命令：

```powershell
python external/batch_fast_feedback_candidate/check_batched_fast_feedback_equivalence.py --repo D:/Codex_ws/robot_rl --output external/batch_fast_feedback_check_01.json
```
