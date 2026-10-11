# FR3B first saved-evidence audit candidate

Prepared only from the reviewed FR2 auditor source and new production source.
No raw artifact, model parameter or result was opened during preparation. The
root owns the first execution against the actual FR3B physical run, with its
exact source commit. The earlier zero-physics source-validation failure is a
separate preserved receipt and is not a 120-RMSE control population.

```powershell
python external/fr3b_audit_candidate/audit_full_request_pair_control.py --repo . --raw results/cpu_validation/2026-10-12_full_request_pair_control/raw --source-commit <FR3B_clean_commit> --output <fresh_audit_directory>
```

The candidate uses Python standard-library modules only. The raw path is fixed;
output must be fresh and outside immutable raw. It does not import project,
controller or model code. Caught errors and the first 128 failed checks are
preserved; no retry is provided.

## Identity and population

Seeds are 8001/8002/8003; methods are cold/learned/pd/zero. Trial IDs must use
`FR3_{seed}_control_{method}`. Manifest/run IDs are FR3B/control. The archived
19-dependency source set matches the new runner, collector, controller and
protocol plus shared unchanged sources; source ZIP bytes are checked against
manifest pins and exact Git objects. No FR3A, FR1/FR2 or suspended raw is read.

Only the new FR3B manifest, run/metrics/models JSONs, trace/prediction compressed
files and archived source ZIP are used. New B model snapshots receive the
original finite shape/count/frozen-fingerprint checks, without restoration,
prediction, fitting or RLS replay. Both compressed trajectories retain the old
hash pass and one bounded JSONL decode pass. Other original I/O, JSON, ZIP,
line-size and decoded-byte caps are unchanged.

The fixed population is 12 trials with 1,000 prefix + 2,000 active steps each:
at most 36,000 trace rows, 1,200 decisions, 11,772 conditional rows and 526,560
saved conditional pair path steps. Conditional groups remain 60, producing at
most 120 q/v RMSE vectors; tracking remains 12 populations and active actual
effort remains 24 two-axis vectors. Missing, stopped and unattempted evidence
retains original complete-first/unknown accounting and cannot be ranked.

## Preserved checks and new request mapping

Original stdlib body/native observation, snapshot schema, actual effort,
contact phase/block, tracking, conditional endpoint/RMSE, batch/forward ledger
and scientific gate helpers are retained. Only seed, trial/stage namespace,
source paths and the new dependency count change in those references.

The new checks evaluate the fixed public expression
`p=clip(64*(target-q)-4*v,-.5,.5)` on saved states as checksum arithmetic. They
never call a PD/controller method, advance a model, reconstruct candidate
trajectories, recompute candidate costs/ties or simulate a feedback sequence.

For each saved macro, the 81 candidate first requests are checked in the frozen
nine-by-nine nominal grid order (-.5 to +.5, spacing .125), using the same
`clip(p+(grid-p),-.5,.5)` roundtrip. A selected dynamic delta must be finite,
within +/-1, and match one nominal grid pair minus current clipped PD. Its saved
first request must be a feasible candidate. The selected 150-step saved request
path is checked from its saved predicted states: delta stays held for stages
0–9 and is zero for stages 10–149. All final requests remain within +/-0.5.
No equality of full candidate paths follows from equal first requests.

Actual cold/learned nonfallback and pd requests use saved native origins and
saved public PD; the request must equal clipped current PD plus held delta.
Held decision/macro indices remain every ten native steps. Fallback keeps
literal zero and missing saved PD is not filled. Zero remains descriptive.

Additional work is explicitly counted and bounded: 1,200 macro mappings,
97,200 candidate first-request pairs, 180,000 selected saved request steps,
18,000 actual request origins, and 198,000 clipped-PD pair expressions on saved
states. These are saved-value arithmetic, not new forward predictions or
physical interaction. No source fixture, old math test or audit is executed
during preparation.

## Scientific and stage boundaries

Original model contribution remains 20% with strict per-seed joint/axis
comparisons and both actual effort means <=1.05 times cold. Original PD
reference remains conditional on contribution, 5% joint improvement, per-seed
non-inferiority and both effort means <=1.05 times PD. Original required contact
and actual-effort complete populations remain unchanged. No self-prediction,
zero or request-check scientific veto is added to the experimental gate.

The four new stage keys are `fr3a_prediction_gate_passed`,
`fr3b_model_contribution_gate_passed`, `fr3b_pd_reference_gate_passed` and
`fr3_free_root_mechanism_validation`. The B metric's A flag must be false because
this stage does not redeclare A; it does not modify or invalidate the separate
FR3A prediction result. Source/execution failure preserves the original gate
veto. The five adoption/C4/C5 flags remain false. The audit verifies new saved
evidence consistency and does not release a scientific dependency or infer
causality from the new control parameterization.
