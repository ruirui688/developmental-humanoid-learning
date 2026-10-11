# FR3 collector and runner candidate

The root owns publication, the final protocol pin, first executions and archival
audits. These files are source-only candidates; no candidate has been imported
or executed during preparation. Production FR1/FR2 files are unchanged.

## Canonical files and stages

- Collector: `src/developmental_physics/full_request_pair_development.py`.
- Runner: `scripts/develop_full_request_pair.py`.
- Controller: `src/developmental_physics/full_request_pair_mpc.py`, supplied by the
  bounded-controller agent; the collector explicitly passes its own unchanged
  `CountedGuardModel` as `counted_model_type`.
- Protocol: `docs/FULL_REQUEST_PAIR_LEARNING_PROTOCOL.md`; its exact final bytes
  and SHA256 are required before a runnable published entry exists.
- FR3A = stage `prediction`; fixed raw pointer
  `results/cpu_validation/2026-10-12_full_request_pair_prediction/raw`.
- FR3B = stage `control`; planned raw output
  `results/cpu_validation/2026-10-12_full_request_pair_control/raw`.

All source dependencies for both stages must be committed together and validated
against a clean exact HEAD. Stage B checks the same dependency byte set against
stage A. FR0 engineering qualification remains required. The reader has no FR1,
FR2, 790x or suspended-snapshot pointer; FR3B may restore only its own fixed FR3A
three-seed cold/learned snapshots after the new prediction gate succeeds.

The seeds are fixed at 8001, 8002, 8003 after the root's single search of public
source/docs. That search did not cover raw or unpublished history, so this is a
new development bank rather than a claim of a globally untouched final bank.
Trial IDs are `FR3_{seed}_calibration`, `FR3_{seed}_prediction`, and
`FR3_{seed}_control_{cold|learned|pd|zero}`.

## Preserved mechanisms and one control change

The original Counted class, model restoration checks, cold prior, coupled phi9,
P100/lambda1, pulse schedules, qref, public joint limits, native inputs, 2ms step,
1,000-step zero prefix, 4,000-step calibration, 1,000-step prediction, 2,000-step
control, horizons/stride, body installation checks, StudyAbort, paid-first
capture, complete native/actual-effort/contact populations and gate arithmetic
remain unchanged. No old mathematical test is rerun during preparation.

The controller class changes to `BatchedFullRequestResidualPDPairMPC`. It offers
81 full first-request pairs from each axis's nine values -0.5 through +0.5 with
step 0.125. It converts the selected first request into a local dynamic residual,
which can reach +/-1; the actual native-feedback PD plus held residual is still
clipped to +/-0.5 each step. The residual is held for 10 steps and the remaining
140-step forecast tail uses public PD. The controller agent owns this exact
implementation and its new minimal fixture source. Boundary selection in FR2
motivates this single development candidate but does not identify a cause.

## Gate and payload schema

Default stage flags are independently false:
`fr3a_prediction_gate_passed`, `fr3b_model_contribution_gate_passed`,
`fr3b_pd_reference_gate_passed`, `fr3_free_root_mechanism_validation`.
Prediction sets only its new prediction gate; control does not manufacture a
prediction-gate result. A caught production failure vetoes all four stage flags.
The five original adoption/C4/C5 flags remain false in run, metrics and manifest.

Prediction preserves original strict H10v/H150q per-seed comparisons and 20%
three-seed raw-RMSE-mean requirements, with the original other-horizon vetoes.
Control preserves complete-first per-seed comparisons, 20% model contribution,
5% PD reference, 1.05 actual effort ratios, and original contact qualification.
Scientific gates are not relaxed. Incomplete populations cannot be ranked.

Artifacts retain the original schema: `run.json`, `metrics.json`, `models.json`,
`trace.jsonl.gz`, `predictions.jsonl.gz`, `paid_intervals.jsonl.gz`, `source.zip`,
installed XMLs and a failure payload when applicable. Manifest schema_version is
1, with FR3A/FR3B experiment IDs and matching stage/status. Run summaries omit
raw records and XML text, while models and paid/raw evidence remain separate.
All failures, stops, unattempted seeds, costs and unknown accounting remain
preserved without reset retries.

Upper budgets remain FR3A 21,000 control calls/substeps and 12,000 vector/24,000
scalar online updates, then FR3B 36,000 calls/substeps and zero updates. FR3B has
at most 1,200 decisions, 14,580,000 planning prediction pairs and 526,560
conditional prediction pairs. Stage A has 124,680 independent prediction pairs.
No teacher, policy update, fit, GPU or real-robot action is introduced.

## First-run commands after publication

```powershell
python scripts/develop_full_request_pair.py --stage prediction --repo . --output results/cpu_validation/2026-10-12_full_request_pair_prediction/raw --source-commit <clean_commit>
python scripts/develop_full_request_pair.py --stage control --repo . --output results/cpu_validation/2026-10-12_full_request_pair_control/raw --source-commit <clean_commit>
```

FR3B starts only if the first FR3A gate passes. Both files and controller/protocol
must already be frozen together; failure does not trigger a new seed, tuning or
rerun. The parent launcher preserves original stdout/stderr and exit status.
