# Pair-PD once-only descriptive summary delivery

Exclusive directory: `external/pair_pd_20261011_summary_01/`. Exact tool bytes, attempt, stdout, JSON/Markdown outputs and execution record are preserved. Formal metadata, episodes, selection, manifest, source ZIP and compressed trace were each read once; first independent audit was read once. The tool imports only the standard library and never imports or executes collector/auditor, physics, fits or body-model predictions.

Source commit: `f9f35fe9bb338aa398cc426e144eff048fde3746`. Independent descriptive checks198,435 /0fail, maximum recomputation difference `1.1368683772161603e-13`; wall `.8815295998938382 s`, CPU `.84375 s`. Exactly three finite arithmetic examples cover paired RMSE, effort dose and stopped/full paid costs. Original source hashes, protocol, dependencies and input/output hashes are retained.

| Artifact | SHA256 |
|---|---|
| `summary.json` | `fcf9acdb07a3b0bb78691f869f6b63edaa72cb78f7194f86dd64a0dcace842e0` |
| `execution.json` | `329ec1468fcab09cdae23c70298a7e546a953b993d200e69ca444a1a050ed2fa` |
| `tool_source.py` | `2b7d07eba5613082adedfc8791427560790ea075841b9968972b0e59a8449279` |

27 predeclared trials yielded9 complete and18 study stops, no exceptions/partial intervals/blocked trials. Actual cost4536 control calls /45360 physics substeps /0 model, policy or gain updates; all27 prefixes are paid (2700/27000), with1836 active calls /18360 substeps. Eligible candidates2/5/8 each complete allthree200-active trials; other candidates0/1/3/4/6/7 each pay306 calls /3060 substeps across three102-call stopped trials. No truncated candidate is ranked by low RMSE.

Candidate2 selects fixed Kp `[64.,64.]`, Kd `[0.,4.]` with exact key `[0.010660460980685132,0.010935465170751784,1.2190868891622377,2]`: mean-seed joint RMSE, worst-seed joint RMSE, mean control actual squared effort, index. Candidates5/8 have joint mean RMSE about `.0111681580007/.0115180674684 rad`, respectively. First audit591,017 /0fail and validated_selection=True matches the independent summary's selection.

All18 stops are control step101 /active1 and left-elbow velocity triggers. Every failing damping candidate has elbow Kd1 or2, and its second request remains clipped to`[-.5,+.5]`. For eachseed these six candidates have identical physical stop endpoints; shoulder damping does not change the already saturated first two commands. Full q/v, raw PD outputs and ten applied substeps are preserved. This describes saturation and failure, not an independently proven causal advantage of any learned mechanism.

Selected candidate2 joint tracking RMSE by seed is `.01040144551998479`, `.010644472251318822`, `.010935465170751784 rad`. Its control guarded substeps are89/109/105; shoulder/elbow saturated scored calls are39/178,40/168,37/169. All200 control endpoints perseed have at least one native joint outside an exact public joint range (the independent environment stopping margin is different), and prefix force peaks around553N remain paid. Full-body speed/force/energy/penetration, per-axis requested/actual absolute and squared effort, complete/partial/missing windows and signed tail errors are retained in summary.json; these facts do not establish safety.

Project cumulative cost after this batch is232,184 formal control calls /2,321,840 physics substeps /12,852 scalar RLS updates, with no learning update in this PD batch. The conclusion is limited to fixed-Kp finite damping-grid development; no global optimum, body-method superiority, skill or adaptation claim. Root owns downstream selection-binding records, scientific comparisons, docs and Git publication. Do not rerun summary or first audit to regenerate the same artifacts.
