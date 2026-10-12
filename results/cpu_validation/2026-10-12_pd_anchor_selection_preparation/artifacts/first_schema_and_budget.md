# FR4D saved-selection projection candidate

Preparation only. Root determines eligibility from the first formal FR4B result
and freezes the diagnostic protocol before any first execution. If all original
FR4B gates pass, this diagnostic is not executed. No gate is recomputed here.

```powershell
python external/fr4_selection_diagnostic_candidate/run_saved_selection_projection_first_once.py --repo . --source-commit <exact-FR4B-40SHA> --protocol-sha256 <frozen-diagnostic-64SHA> --capture external/fr4d_first_selection_projection
```

The wrapper refuses an existing capture, saves the first stdout/stderr and
`first_execution_receipt.json`, and invokes the projector once. Direct projector
CLI accepts the same repo/commit/protocol SHA arguments plus `--output` for a
fresh result directory. The only experimental file inputs are the fixed new
FR4B `manifest.json`, `run.json` and `trace.jsonl.gz`, each read once. Compressed
trace bytes are cached and streamed from memory through one gzip decoder.
No production source, protocol file, models, prediction journal or old result
is opened by the projector; its own source is read once for an identity pin.

Output `projection.json` uses `fr4_saved_selection_projection_v1` and includes
FR4D identity, three input pins, exact FR4B source commit, declared frozen
diagnostic protocol SHA, four bound production pins, tool source identity,
twelve matrix cells, all 1,200 fixed origin records, decoded phase counts,
engineering costs, bounds and the first failure. A failure additionally writes
`first_failure.json`; there is no retry or overwritten output.

The population is seeds 8101/8102/8103 × learned/cold × A/B. Learned's 600
origins are primary and cold's 600 are a declared descriptive comparator.
A covers active 0–999 and B covers 1000–1999, with origins every ten rows.
Every cell retains 100 planned origins, including missing/partial origins as
NA; the full trial's saved complete/status/stop/failure metadata is transcribed.
PD/zero and prefix rows contribute only decoded identity/phase counts.

For each present origin, restore p from current saved native q/v and target by
the public per-axis `clip(64*(target-q)-4*v,-.5,.5)` expression. Replace the
nearest original-index slot per axis and enumerate the 81 ordered pairs. Read
only the reconstructed anchor slot's saved candidate torque/feasible/cost.
`anchor_present_in_expected_slot` means its finite first torque equals restored
p exactly; it does not scan for a relocated anchor elsewhere. Missing native
input, decision, complete candidate list, slot record or finite torque gives
NA. A complete slot's different torque gives false. The saved feasible flag,
selection delta/torque/cost/fallback and their availability remain separate.
Literal-zero fallback is never relabeled as pure PD. Delta zero is considered
chosen only for a nonfallback saved selection with zero delta and first torque
equal to p; absent selection fields remain NA.

Selected-minus-anchor cost is one subtraction only when the anchor is present
and saved feasible, selection is nonfallback, and both saved costs are finite.
Each cell reports known/NA counts, exact sign counts, min/max and empirical
nearest-rank q25/q50/q75 without interpolation. The fixed denominator is 100;
the distribution's eligible denominator is stated explicitly. This describes
saved model-forecast selection costs, not counterfactual actual PD performance,
causality, tracking accuracy, effort, safety or adoption.

Bounds: 36,000 decoded rows, 1,200 fixed origins, twelve cells, 1,200 public-PD
pair restorations / 2,400 axis expressions, 21,600 nearest scalar distances /
2,400 nearest index selections, 97,200 pair enumerations, 1,200 anchor-record
inspections and at most 1,200 saved-cost differences / sorted distribution
values. JSON inputs are bounded to 16 MiB each, compressed trace to 512 MiB,
decoded trace to 2 GiB, and each line to 2 MiB. Raw reads and source identity
reads are separately charged. No other candidate feasible/cost is inspected,
and no rollout, original cost/tie, RMSE, gate, model, fit, RLS or physics is run.
This does not authorize changing weights/grid or extending the diagnostic.
