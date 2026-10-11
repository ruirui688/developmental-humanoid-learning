# Pair-calibration one-pass summary delivery

Output directory: `external/pair_calibration_20261011_summary_01/` (exclusive, first execution). It contains exact `tool_source.py`, `attempt.json`, `summary.json`, `summary.md`, and `execution.json`. Original metadata, episodes, manifest, source ZIP and compressed trace were each read exactly once; the existing audit JSON was read once. No auditor was imported or executed; no physics, fit, update or prediction calls occurred. No tracked/Git files were changed.

Independent descriptive recomputation:44,685 checks /0fail, maximum difference0; only three finite hand-calculation examples. Wrapper wall `.41032179980538785 s`, CPU `.34375 s`. Source before/after hash identical. Clean physical source commit is `86453c1280c986748717ca79ae4d4d3d45b52973`; original source hashes, input file hashes, dependency versions, zero audit/physics/update/prediction counters and paid interaction budget are preserved in the generated artifacts.

| Artifact | SHA256 |
|---|---|
| `summary.json` | `76038105eb1eec7c59abe365efb249f88470662aa88ce33353448b2c4b430fb5` |
| `execution.json` | `909522d13b2491023324a674bfeeca4a9cfcf2d34acb851d0f57ab9bbd91ca0a` |
| `tool_source.py` | `d5bb79517f01300652ef7c7988ee992814c27761f02576c401a72037a87f4248` |

Both predeclared schedules ran. Pulse2/zero8 terminated on all three seeds; pulse1/zero9 completed all three500-call trajectories and400 active endpoints, so pulse1 is selected by hierarchy. Total paid cost2586 calls /25860 substeps, including600 prefix calls /6000 substeps and1986 calibration calls /19860 substeps. There are no partial intervals, raw exception rows or environment stops;0 parameter updates. Existing audit is466,758 checks /0fail.

Every pulse2 stop occurs at control step361, active261, block13, slot1: the second pulse slot of the `.5 Nm` block with the same relative direction shape and fixed public-room signs `[-1,+1]`. All ten applied substeps are `[-.5,+.5]`, with no screening on that last command. The sole trigger is left-elbow speed: seed0 `1.0718069104957968`, seed1 `1.0713918786946433`, seed2 `1.0722683998426479 rad/s`; immediately before, elbow speeds are about `.6155–.6161 rad/s`. Shoulder final speed is about `-.546 rad/s`. Both position deviations remain below`.12 rad`. Raw q/v/reference, previous endpoint and last command histories are preserved per seed.

Pulse2 per trial:262 full active endpoints,160 screened substeps, requested absolute effort `[.20,.20] Nm s`, actual `[.20,.11]`; requested squared effort `[.07,.07] Nm2 s`, actual `[.07,.04]`. Each axis has340 nonzero requested substeps, while actual nonzero shoulder/elbow counts are340/180.

Pulse1 per trial:400 full active endpoints,150 screened substeps, requested absolute effort `[.18,.18] Nm s`, actual `[.18,.09]`; requested squared effort `[.06375,.06375] Nm2 s`, actual `[.06375,.031875]`. Each axis has300 nonzero requested substeps; actual nonzero shoulder/elbow counts are300/150. Thus half the elbow's requested nonzero substeps are screened. Final q/v being near their starting/resting values is not a demonstration of skill learning or a fitted coupled-body model.

This verifies the selected fixed calibration schedule's finite executability in this development matrix only. It supplies no controller comparison, new learned model, risk reduction, holdout or locomotion conclusion. The root task owns source-bound formal decisions, archive promotion and Git commits/pushes. Do not reexecute the tool or audit merely to regenerate these outputs.
