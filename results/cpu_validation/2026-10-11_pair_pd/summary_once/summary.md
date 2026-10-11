# Pair-PD one-pass independent descriptive summary

Source `f9f35fe9bb338aa398cc426e144eff048fde3746`; 198,435 checks /0 failures; maximum difference 1.1368683772161603e-13.

| Candidate | Kd shoulder/elbow | Eligible | Paid calls/substeps | Mean/worst joint RMSE | Mean actual squared effort |
|---|---|---|---|---|---|
| 0 | [0.0, 1.0] | False | 306 / 3060 | — | — |
| 1 | [0.0, 2.0] | False | 306 / 3060 | — | — |
| 2 | [0.0, 4.0] | True | 900 / 9000 | 0.0106604609807 / 0.0109354651708 | 1.21908688916 |
| 3 | [1.0, 1.0] | False | 306 / 3060 | — | — |
| 4 | [1.0, 2.0] | False | 306 / 3060 | — | — |
| 5 | [1.0, 4.0] | True | 900 / 9000 | 0.0111681580007 / 0.0114893886481 | 1.29753933475 |
| 6 | [2.0, 1.0] | False | 306 / 3060 | — | — |
| 7 | [2.0, 2.0] | False | 306 / 3060 | — | — |
| 8 | [2.0, 4.0] | True | 900 / 9000 | 0.0115180674684 / 0.0118072739222 | 1.43733789895 |

Statuses: {'terminated': 18, 'completed': 9}. Paid budget: {'control_calls_attempted': 4536, 'control_steps': 4536, 'physics_steps': 45360}. Picked: {'candidate': 2, 'kp': [64.0, 64.0], 'kd': [0.0, 4.0], 'eligible': True, 'sort_key': [0.010660460980685132, 0.010935465170751784, 1.2190868891622377, 2], 'paid_control_steps': 900, 'paid_physics_steps': 9000}.

Full/partial/missing windows retain original planned indices. Complete stopped endpoints can be scored but never qualify a truncated candidate. Per-axis effort, full-body risk, saturation, stopping q/v and all window endpoints are in summary.json.

Finite fixed-Kp damping-grid development only; no global optimum, body-model advantage, skill, adaptation or safety proof.
