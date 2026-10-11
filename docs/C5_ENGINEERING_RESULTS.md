# C5 动力学事件：零学习工程检查完成

本批次验证隐藏输入缩放与关节 armature 变化的实现、原生感觉、子步力矩与计账一致性。四组全部完整，工程门通过；没有身体模型、策略更新或适应收益评价。

## 事前计划与单次执行

[冻结协议](C5_ENGINEERING_PROTOCOL.md)和[源码绑定](C5_ENGINEERING_BINDING.json)在运行前提交。首轮从 clean `652f9d59ce8e13d552327a0b19f331270fd85aa9` 执行一次，没有补跑。此前 `d17f255` 的 staged 检查发现测试末尾空行，检查退出码未阻止提交；随后单独提交 `652f9d5` 修复空行及绑定字节，`git diff --check` 通过后才开始物理执行。没有改写已推送历史。

四个 fresh 环境均为 supine、development seed 0、reset seed 3757552657；每组 100 次已计账零输入前缀和 20 次共同肩—肘脉冲。最终权限 .5 N m、控制时序 .002 s×10、原研究停止 .12 rad / 1 rad/s 全部保持。

| 组别 | 边界100事件 | 完整控制调用 | 实际子步 | 停止 / 异常 |
|---|---|---:|---:|---:|
| base_identity | 不改变参数 | 120 | 1,200 | 0 / 0 |
| wrapper_identity | gains 全1 | 120 | 1,200 | 0 / 0 |
| gain_half | j0/j1 gains=.5 | 120 | 1,200 | 0 / 0 |
| armature_double | j0/j1 armature .01→.02 | 120 | 1,200 | 0 / 0 |

实际合计 **480 控制 / 4,800 子步 / 0 RLS / 0 策略更新 / 0 教师调用**，unknown kernel attempt=0。MuJoCo 3.15.0，CPU；collector wall 1.9760225999634713 s、process CPU 1.875 s，外层 wall 2.8642813998740166 s。完整依赖版本在原始 metadata 中。

## 工程结论与信息边界

base 与 gains=1 wrapper 的全部120行原生观测、q/v及子步实际历史精确相同，79,800个数值叶比较的最大差为0。参数事件没有改变 live q/v/ctrl/time/counters/previous_command；gain从下一请求生效。armature 在同q、scratch MjData的完整广义质量矩阵上仅使选定两个DOF的对角线各增加 .01，未添加积分步。原生 joint ID / qpos / DOF 由模型名称查询，独立审计再按冻结资产核对。

每子步独立记录角度、公开请求、隐藏缩放、实际ctrl和返回后的unit-motor force，重新计算 .03 rad guard。actor没有读取隐藏参数、接触或质量矩阵；这些仅作工程诊断。

每轴请求绝对努力为 .05 N m s、平方努力 .0125 N²m²s。base/wrapper/armature 的实际肩/肘绝对努力分别 .05/.025、平方努力 .0125/.00625；gain_half 为 .025/.0125 与 .003125/.0015625。肘负向请求被公开guard屏蔽，因此请求努力与实际努力不同。gain减半带来的较低实际努力属于环境变化，不能算作学习或成熟优势。

## 独立核验、原件与后续

首次标准库独立审计 **481,538项 / 0失败**，最大重算差见原件，工程门通过，学习/适应标志为False。audit wall 1.026587599888444 s、CPU .578125 s，新增物理与更新均为0。审计原件 SHA256：`c74ddf28dec74ac4f6133090605a1fea9ecb672ecb8b007ea53fa03b95535e40`。源码ZIP的12份文件均核对运行提交的Git blob；独立审计脚本自身SHA也纳入绑定。

随后一次独立只读summary的39项一致性检查零失败；原件SHA256 `739e9ce157a4712ae603e1e285f03d804cb7ddca3aece1b4be946f7ea832b3eb`，wall .0061001 s、CPU 0.0 s（短任务低于Windows计时分辨率）。它没有再次调用audit、物理或模型。质量矩阵声明差的最大误差为1.734723475976807e−18。

相关合成检查99项通过；最终审计与来源检查33项通过。源ZIP污染测试的duplicate-name warning为预期注入。草稿所有尝试、错误API stub首轮通过与后续修复、独立审计fixture首轮失败、来源fixture范围修正以及完整stdout全部保留，不能把这些合成证据称为物理效果。

原始轨迹、事件、首次audit、独立summary、来源和合成失败归档于 [证据清单](../results/cpu_validation/2026-10-11_c5_engineering/manifest.json)。不重新运行物理或audit来生成归档。正式物理研发累计现为 **225,062 控制 / 2,250,620 子步 / 12,852 scalar RLS**，测试与离线诊断另列。

继续 C4 的有限双轴PD阻尼搜索、2/8与1/9短脉冲校准可执行性，然后比较公共guard本身、身体学习与耦合的贡献。C5科学对照还需另冻结冻结/在线模型的变化适应协议，至少两类变化、统一任务与权限，并报告恢复成本、预测、控制、努力和失败。工程完成不结束[持续目标](CONTINUOUS_EXECUTION_PLAN.md)。
