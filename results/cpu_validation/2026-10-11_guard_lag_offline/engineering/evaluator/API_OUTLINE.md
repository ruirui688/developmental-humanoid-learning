# Single-lag offline evaluator: proposed binding and output interface

Ignored development staging only; no real C fitting or prediction has run.
Canonical proposed runner: `src/developmental_physics/guard_lag_offline_development.py`.
Root promotes/freezes this runner, helper, protocol, independent auditor and core
sources before the one formal execution. Staging `FORMAL_OFFLINE_ENABLED=False`.

`run_single_lag_offline(output, *, source_root, protocol_path,
source_freeze_path, execution_context)` creates a new output directory only.
`source_root` is the sealed `2026-10-11_guard_exploration` archive, containing
`raw/` (six original files), `first_audit.json`, and `summary_once/summary.json`.
The pinned summary/audit bytes, collection commit and all six raw hashes are
checked before model import or arithmetic. `source_freeze_path` is root's JSON
mapping `source_sha256` from repo-relative paths to exact frozen SHA256, plus
`source_commit`; execution_context supplies root's independently verified Git
commit/clean status. This evaluator runs no Git command or physical simulator.

Outputs (JSON strict finite encoding; nonfinite diagnostics use explicit strings):

- `attempt.json`: start, source identities, and execution context before work.
- `source_binding.json`: exact six raw + summary + audit identities, source
  freeze, source-read bytes/rows and native-history boundary rules.
- `source_snapshot.zip`: every root `source_sha256` entry in its original byte
  content, plus exact `runtime_source_freeze.json`; source_binding records SHA.
- `calibration_updates.jsonl.gz`: one record per attempted new 11D vector update,
  input q/v/u/previous_v, original row IDs, returned label, helper update or exact
  failure accounting, per-call ledger delta and committed fingerprint.
- `diagnostics.json`: each seed/cal nine-column native design diagnostics before
  new fitting, old saved snapshots 100/200/300/400 and coefficient changes/local
  F4 modes; then 11-column diagnostics, lag snapshots and F6 modes. Original9
  models are restored from published snapshots and never refitted.
  Coefficient scales equal centered RMS for nonconstant columns, one for an
  identically-one bias, and zero for other constant columns. Snapshot drift
  begins at each saved cold initial coefficient array (update0).
- `rollouts.jsonl.gz`: one record per seed/trial/origin/predictor, common maximum
  available H, native current/previous row identity, saved request sequence,
  every predicted endpoint/known start-G and history update, exact saved one-step
  reuse provenance or new per-call accounting, retained numerical failure.
- `summary.json`: fixed five predictor slots, every seed/trial/H1/2/5/15,
  per-axis q/v RMSE, signed prediction-minus-observation bias, max absolute error,
  common complete-window count, mathematical failures and unavailable reasons.
  Descriptive grouping uses native start-G sign and nonzero request age
  (zero/1/2/3-5/6+ complete active steps, per axis). No selection or science gates.
- `run.json`: status, six cal completions/failures/unexecuted updates, separate
  offline RLS internal preupdate and evaluation pair/scalar costs, reuse counts,
  feature/design/linear-algebra costs, new physics/refit/control/PD-teacher zero.
- `manifest.json`: SHA256 and bytes for every output, final status.

Calibration update records contain original transition IDs and model snapshots
at update100/200/300/400. Rollout original9 fingerprint and saved-input exactness
are mandatory for reuse; native endpoint provenance initializes every origin.
Each predictor rolls only once to the origin's highest available H, using its
own predicted q/v/history thereafter. Future requests are offline conditioning
only. Every model shares source windows; failure cannot remove a window.

The small artificial suite will exercise history/continuity/reuse/rollout/cost
logic with hand-written continuous native fixtures and instrumented fake models.
It will not collect a large FakeEnv archive or run the saved C matrix.
