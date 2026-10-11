# C2/C3：冻结单肩方案的新留出联合评价

2026-10-11；C2开发结束后、读取新最终20/21/22的真实结果前冻结。实现与独立审计完成相关检查、正常提交推送后，从干净源码执行一次。

## 研究范围

验证少量CPU身体辨识在单肩上的预测、同MPC控制贡献，并与开发选择的经典PD公平比较。模型有效域、各消融失败和全部候选成本保留。它不授予翻身、站立、行走或真机结论，也不因独立轨迹预测好就宣称闭环自身预测已解决。

唯一配方固定为 **short / old / hinge5 / endpoint_euler**。从clean `a2fe5c2c19602d759bd98b882000753036645432`完成C2-C，首次独立审计SHA256 `8a7935c9e8b094d4fb0169abe3b6e60da18774630ff5178e41d158ea4411f555`，963,372检查零失败、12历史锚点精确复现；覆盖与性能门均失败，重排tracking仅改善0.422642%、low速度三seed退化，q域外仍93.5%，按事前规则保留short。此前积分与剂量/结构修订同样未被采用；闭环模型有效域尚未解决，不能把本批说成修复已成功。

PD从先前九组开发唯一选择Kp64/Kd0，不再读新留出选择参数。最终阶段新seed20/21/22，supine/j0。每seed自己冷启动、真实校准，不复用开发theta/P或日志。只为标准库核验静态派生reset_seed，三值分别为1822509288/2605417566/1950464737（原NumPy SeedSequence规则），这一算术不读取初态、模型或任何真实留出指标，不改变种子选择。

## 共同信息、控制与预算

所有trial独立reset，派生reset seed保持原规则；100步真实零请求前缀计账，qref/s从自身前缀末原生encoder与公开限位一次确定，精确配对。身体、baseline接触、原环境保护、.5 N·m请求上限及其余七关节请求0不变。模型仅读step前q/v/请求u，next v只作校准标签；隐藏参数、接触/动能/未来实际力矩仅作诊断。

hinge5 theta=[1,0,.02,0,0]，P=100I，lambda1，折点.25固定。校准300完整转移各一次更新，prefix/partial/evaluation不更新。所有预测与控制用冷启动nominal、cal后冻结learned，恒速度持久性另列。MPC原H15/9候选/权重/预测域/回退/决胜不变，当前目标前100为qref+s*.04，后100为qref+s*.08，无预告；不可行目标失败不裁。PD=clip(64*(target-q),-.5,.5)，zero恒零，两者也接收相同当前目标/权限/保护。

全部active每次返回端点共享StudyAbort：abs(q-qref)>=.12或abs(v)>=1，等值触发、只停止无纠正动作；prefix只原环境保护。study/env停止分别记录，完整terminal允许更新/评分，partial只保存原生状态/known target误差和真实成本、不混完整20ms预测/RMSE。末计划步触发也不completed。零停止不证明安全。

每seed固定顺序calibration400、prediction_low200、prediction_full200、nominal_mpc300、learned_mpc300、tuned_pd300、zero_torque300，共7trial/2000控制/20000子步/300RLS；三seed21trial/6000控制/60000子步/900更新、120s模拟时间。prefix2100/21000，cal900/9000，pred600/6000，control2400/24000。名义/PD/零各自付费前缀独立继续；cal失败阻塞共享pred和learned控制，普通失败不补跑，中断/IO/trace错误fatal标剩余blocked。

相同控制权限、目标与评价时域不表示各方法同总成本：学习法每seed另需400次真实校准，PD不需要该阶段；共同预测是额外评价成本。分别报告各方法启动/校准/控制成本、九组PD调优及全部C2开发成本，不把本矩阵6000次总账均分后声称同交互预算优势。四种控制的每trial100前缀+200控制是配对评价窗口。

low/full固定100active、各五20步block的7正/3零/7反/3零，幅度分别[.25]*5、[.125,.25,.375,.5,.375]，选定时序对应的校准300命令完整符号直方图与努力不变。校准计划请求努力.55/.20，实际每子步重新计量，实际屏蔽/风险与未知遥测不能填零。全部规划、失败规划、离线诊断、源码、审计与依赖计账分开。

## 两个命题与门

一致性门：源commit/clean/原字节ZIP及SHA、协议、派生seed、所有前缀、原生日志、实际努力、RLS/P、frozen参数/MPC/PD/target、phase/trial/batch真实与失败成本、StudyAbort、partial与日志完整通过独立标准库重算。历史锚点复现只针对已见开发档案，不能再跑新seed。

局部模型贡献门：三seed的calibration、两prediction、nominal/learned MPC共五个必要trial均完整且无study/env stop、异常、非法请求/非有限；low与full的learned v RMSE逐seed<=.8nominal；200步learned tracking逐seed严格小于nominal，三个原始RMSE均值至少降低20%。该门继承初期学习贡献标准并扩展到full幅度，PD比较独立，不预先保证成立。

经典控制比较门：局部模型贡献门通过，且三seed的PD均完整无任何停止/异常/非法非有限；learned tracking逐seed<=PD且三seed原始均值至少低5%，控制active实际绝对/平方努力均值各<=1.05PD。若失败，公开PD与learned真实误差/努力；只在模型贡献通过时称同MPC中的模型贡献，不能称超越强基线。zero及三seed全部七trial的complete_matrix单独输出；PD/zero失败不能抹去完整的同MPC比较，也不能被局部门成功掩盖。风险不设事后容差，原值全报，不把努力门称风险下降。

零分母改善保持未定义，努力PD=0只允许learned=0。全部门事前冻结；不追加seed、动作、调参或剔除失败。性能未过仍归档，未来修订另编号并用另一个新留出bank，不再称20/21/22未见。

速度门按上述乘法判定；nominal速度误差0且learned0时可满足数值门，但百分比改善仍未定义，不报告降低20%。tracking均值分母0时均值改善门失败；原始严格逐seed条件不以epsilon替代。

## 完整诊断及接续

共同low/full、cal in-sample、每个控制自身/配对轨迹的1/5/15/50步q/v端点/路径RMSE，合法/排除/terminal窗口数与block/幅度/切换/保持分箱；未来日志请求仅offline条件，不能作为在线预知。q/v支持包络、并集域外率与q nearest距离按完整active输入，不能把包络当安全集或准确性保证。

full/prefix/cal/pred/control子步接触峰/冲量、穿透、动能、八关节速度、软限位/屏蔽、饱和/回退/停止，两个目标窗口和各自最后20个计划端点（active80–99、180–199）的跟踪RMSE、平均有符号/最大绝对误差均报。每尾窗计划分母20，只有完整20ms转移评分；partial或早停缺失保留返回/完整/缺失数与未完成标记，完整末端触发stop也不能称无停止窗口。尾窗为描述性指标，不改变收益门。zero保留被动变化，共同prefix峰不掩盖active风险。三seed只作冻结协议下的局部结论，不推统计显著性或未见动力学泛化。

先冻结推送，再从clean执行一次、独立审计/归档结果并推送；立即继续C4固定左肘和肩—肘协调，随后C5/C6/C7，不以本批局部结果结束持续目标。

```powershell
$env:PYTHONPATH = 'src'
external/cpu_physics_env/Scripts/python.exe -m developmental_physics.local_frozen_validation `
  --suite shoulder_final --output external/local_frozen_20261011_final `
  --protocol docs/LOCAL_FROZEN_VALIDATION_PROTOCOL.md
```

正式物理累计基点为202,850控制调用/2,028,500子步/9,000RLS；本批完整执行后为208,850/2,088,500/9,900。测试与纯算术派生、离线冻结诊断、规划、审计成本另列。相关路线：[持续目标](CONTINUOUS_EXECUTION_PLAN.md)、[时序开发协议](LOCAL_COVERAGE_ABLATION_PROTOCOL.md)、[经典开发结果](CLASSICAL_PD_DEVELOPMENT_RESULTS.md)。
