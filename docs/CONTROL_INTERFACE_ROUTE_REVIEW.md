# X/Y 后的一次有限控制接口路线判断

本次仅静态审阅源码、公开资产及其他代理缓存的 PD/action/model 接口，不读取旧 raw/metrics，不运行模型、物理、fit、装配或测试，不修改冻结 X/Y。主代理转录：Y0 从 clean `1ef7bbe3df016b01b47b0bea0ccc27821c0d7091` 返回203控制/2,030子步（100prefix+103active），`Y0_seed7500:202` 肘速度 `1.1258089506362488 rad/s` 触发原1rad/s停止。Y0 工程失败，Y1/Y2关闭；此前 X0 肩超速失败也保留。两个失败不能识别采样周期、增益、接触或模型的因果。

## 源码确认的接口

[GroundBodyEnv.step](../src/developmental_physics/environment.py#L265) 在入口 clip 一次请求，然后在10个2ms子步内保持该 accepted 请求。每子步重新执行公开角度方向 guard，可把相应请求置零；它没有根据新速度重新计算 PD。积分后 `mj_forward` 刷新原生感觉、捕获诊断，并执行基础保护。因此 **2ms积分/保护不等于2ms动作反馈**。

[基础保护](../src/developmental_physics/environment.py#L249) 的默认速度门为20rad/s；研究中的 `.12rad/1rad/s` StudyAbort 只在 X/Y collector 的完整 active20ms返回端点判断，prefix只走基础保护，属于不同层次。新接口若每个完整 active2ms执行原 StudyAbort，阈值不变但判断时间更密、停止延迟更短，应公开这一改变，不能声称所有旧停止语义完全相同；prefix不暗中新增研究速度门。

[资产](../src/developmental_physics/assets/ground_body.xml) 声明 `implicitfast`、2ms timestep、原生关节 damping `.15` / armature `.01` 及 gear1、ctrlrange `±.5` 的 motor；XML没有声明速度伺服、activation滤波、电流环或传感/执行延迟。静态声明不等于已经独立核对所有编译后执行器动态；本轮未编译或测量。实际 actuator force 和应用请求已分别记录，不能把请求直接当未测实际努力。

[SupportedGroundBodyEnv](../src/developmental_physics/supported_environment.py#L27) 要求整个配置与 baseline 相同；悬挂环境继承该保护/capture核心。更快反馈不能靠原 X/Y 路径偷偷修改配置实现，需另名接口，明确新配置边界、来源与时间账。

## 有限结构选择

合理的下一项工程候选是：保持2ms物理、同 PD64/Kd(4,4)、同权限及任务，在每个2ms端点用新的原生 q/v 重算下一请求。这缩短已知的恒请求区间，不估最优增益，也不修改旧 X/Y。它引入更高反馈频率、更多观测/计算及经典控制任务能力，不能称学习得到的反射，也不能保证小角度任务通过。

主代理提出保持真实 prefix2s、两个目标段各2s：1,000prefix+2,000active、共3,000控制/3,000子步，末窗仍0.4s但各200端点。这是时间尺度一致的**另名工程接口候选**，不属于同安装 Kp/Kd/seed/目标/权限扫描。控制调用与反馈机会相对完整 Y 上限增加10倍，MAE采样也改变；不同 seed 加上 X/Y 不完整，不能证明频率改善的因果或等计算效率。此处只判断合理性，不冻结物理协议或承诺成功。

独立底层速度反馈也有合理动机，但会将外层动作改成速度/位置目标或残差，而非当前恒扭矩。仅靠 native v 的阈值制动缺少加速度、延迟和最小制动能力界，不能直接声称速度不变集或安全证明。本轮不把速度屏障与反馈频率一起改变，不继续扫描参数。

## 后续身体模型的公平比较

PD/action/model 代理以缓存确认：旧 `predict(q,v,u)` 的 u 是20ms起点的已知请求，`q_next=q+.02*v_next`；原 H15 是300ms，未描述2ms闭环重算。同一个起点饱和请求还可能对应不同目标和后续反馈轨迹，不能用未知未来实际力矩补模型输入，也不能直接沿用旧 snapshot。

将来必须先选择并冻结新动作语义与模型时间尺度：如果2ms为学习步，H15只有30ms，标签、RLS次数及规划负担都改变；若保留20ms外层而内环2ms反馈，需建模 `(q,v,current_target,known held residual)` 到20ms端点的闭环映射。两种设计不能混写，本次不选择新的科学配方。

cold/learned/经典对照必须共享内环频率、传感时点、动作权限、目标、支撑和保护，只允许模型是否更新不同。比较应同时报告真实时间/子步、采集标签/更新、原生观测、反馈调用、规划前向和实际努力；不把300与3,000控制调用当同预算，不用停止轨迹排名。经典反馈自身已有能力单列，旧20%/PD5%门不能凭改步长追认通过。完整自由 root接触C4及C5–C7依然未验收。

## 本轮读取边界

core只读 `environment.py`15,822、`supported_environment.py`11,642、`suspended_environment.py`7,076及XML3,430 bytes，共37,970已知源字节；PD/action/model代理复用缓存，本轮其新增源/raw读取为零。正文事实由主代理转录，精确commit只读解析；7600整数字边界公开源码/文档搜索无匹配，未读raw。Git/搜索/编辑器与OS IO未知。后续文档格式/链接和新源码窄review由单独receipt记账；本次0实验执行不等于0读取/计算。
