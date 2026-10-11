# Pair calibration finite descriptive summary

Source commit: `86453c1280c986748717ca79ae4d4d3d45b52973`. Independent descriptive checks: 44,685, failures 0; maximum difference 0.

This reads each original input once, recomputes finite facts, and does not execute the auditor, physics, fitting or predictions.

| Trial | Status | Calls / substeps | Full active endpoints | Stop active / block / slot | Final shoulder v | Final elbow v | Guarded substeps |
|---|---|---|---|---|---|---|---|
| pulse2_seed0_calibration | terminated | 362 / 3620 | 262 | 261 / 13 / 1 | -0.546075148445 | 1.0718069105 | 160 |
| pulse2_seed1_calibration | terminated | 362 / 3620 | 262 | 261 / 13 / 1 | -0.545647190695 | 1.07139187869 | 160 |
| pulse2_seed2_calibration | terminated | 362 / 3620 | 262 | 261 / 13 / 1 | -0.5463971689 | 1.07226839984 | 160 |
| pulse1_seed0_calibration | completed | 500 / 5000 | 400 | — | 2.09895389873e-05 | -1.11882713099e-06 | 150 |
| pulse1_seed1_calibration | completed | 500 / 5000 | 400 | — | -4.8736351126e-05 | -1.11938887998e-06 | 150 |
| pulse1_seed2_calibration | completed | 500 / 5000 | 400 | — | 8.9413486382e-05 | -1.11742747219e-06 | 150 |

Selected pulse: 1; both candidates were executed, and selection uses all three complete trials rather than truncated effort.

All per-axis requested/actual absolute and squared efforts, prefix/calibration budgets, exact stop q/v/reference, command histories and input/source hashes are retained in summary.json and execution.json.

These results establish finite calibration executability for the selected short schedule. They do not establish safe exploration, learned coupled dynamics, controller improvement or locomotion.
