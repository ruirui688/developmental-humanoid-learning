# PD反馈尾工程草稿交付

候选尚未正式选择；`FORMAL_PD_TAIL_CONTROL_ENABLED=False`。root 将在 F 首次原生上下文诊断之后决定提升或放弃。本目录没有物理入口、实验协议冻结、真实数据读取或 tracked 修改。

## 最小结构

`pd_tail_pair_mpc.py` 的 `FixedPDTailGuardLagPairMPC` 继承旧显式history MPC的初始化、grid、bounds和fingerprint接口。h0请求为原81网格候选b；h1..14请求为固定 `clip((64,64)*(current target-own predicted q)-(0,4)*own predicted v,-.5,.5)`。不预览目标切换，不用真值校正预测；每候选独立起点和history，先predict再将old current v推进为previous_v。

原position/velocity/effort/change权重不改。stage effort以该stage requested torque计算，change仅首请求b对previous实际请求。forecast .15/1.5、H15、9x9 grid、权限.5、成本tie与zero fallback保留；不同时修订forecast契约。实际执行仅b，下一个20ms再观察并优化，未来执行不保证等于预测PD尾。`PDTailMPCDecision` 增加 `trajectory_requested_torque`，与选中predicted q/v逐stage对齐。

工程fixture只把horizon设为1、2或15，其他MPCConfig常数均用原默认。正式collector若被提升应冻结默认配置并审计spec，不能借可选工程config偷偷更改预算或规则。cold/learned正式比较必须同尾结构、同资产/qref/ranges/权限/target；草稿没有在线学习、gain选择或gain更新。已选PD的任务能力及此前gain开发预算必须披露，不把它说成身体模型本轮学得；PD尾不是教师数据。

## 一次新分支人工检查

`check_pd_tail_new_branches.py` 使用明确合成模型double，原在线model.predict、旧MPC.select及旧fixture不调用；double的零更新初始化和fingerprint也有非零计算。不是12trial人工整档矩阵，没有MuJoCo依赖。

首次且唯一 `engineering_01` 检查 **5通过/0失败**：H1按独立小手算退化为只有原第一请求；H2/H15各检查所有候选自身history、候选隔离，以及选中request trajectory、逐stage effort与仅首步change。针对新费用分支额外计算“错误地每stage收费第一请求”的代价，确认该错误与正确代价可区分。没有重复任何旧通过MPC人工fixture，也没有旧工程/物理重跑。

新数学费用：1458 synthetic pair model calls /2916 scalar outputs；81独立H1 reference pair /162 scalar；1215独立tail request向量计算；115独立stage cost endpoint计算；6 fingerprint调用。新增物理、RLS、archive读取、模型/gain更新、旧MPC.select和旧fixture均0。fixture wall .025703799910843372 s / CPU .03125 s；wrapper wall .29450220009312034 s / wrapper自身CPU .0 s（不含child；不能解释为零计算）。Python3.10.11、NumPy1.26.4。

首次检查前保存9源码payload原字节/hash于 `engineering_01/source_snapshot/`，89402bytes；wrapper另读stdout1536bytes；此后只投影新run.json一次4337bytes。加上开始时为新增decision字段读取local_pair_model.py的25148bytes，本工程阶段显式逻辑读取覆盖为120423bytes。Python import I/O未测量，非零启动/import计算已包含wrapper wall，不称上述覆盖为操作系统实际磁盘I/O。没有读取E/C/D/F数据。所有首次stdio、run账和执行前源码原件保留，不靠重跑补结果。

## 原件身份与边界

首次检查MPC源码 SHA256：`6d1af186eb02e033a31fcc294eedd38fa743a418a69d16744350fa02aec3beed`。
检查源码：`0d3d92654d9414f8585e2651864aeb78033959d1997e3f6a132d03d5f0dafd7a`。
wrapper源码：`2ef64ef289196ad82e59d065426a948e53eb5c3ead776de2506549fac747a4bc`。
依赖源码身份、实际执行HEAD、源码复制账和child原报告均在 `engineering_01/run.json`；这是external工程执行身份，不是正式clean实验冻结。

目前未做独立auditor、真实frozen snapshot控制集成、正式collector或物理验证。5个检查只证明这些新增人工分支，不证明无异常、控制改善或安全。D sparse11旧pulse20%门失败继续保留；即使未来控制子门通过也需另冻结新预测/必要校准与独立控制验收，不能替换旧门。E部分tracking不用于方法排名，C4/C5科学依赖未解除。
