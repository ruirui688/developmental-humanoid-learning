# E runner delivery and evidence limits

Scope is the ignored `external/c4_lag_control_runner_staging/` directory only.
Root owns promotion, formal execution, audit, archiving, Git and pushing. No
tracked core, old collector, D/C archive or scientific stop/permission changes
were made by this delivery. Runner formal permission remains false.

## Executed engineering evidence

1. `engineering_attempt_01`: the default D:\\Python3.10 interpreter lacked
   MuJoCo and failed during import. Wall .194044 s / CPU .15625 s. Fake calls,
   predictions, updates, physics, D reads and Git were zero. Original output
   and execution record remain. Only source/test hashes were saved then;
   the original runner bytes are unavailable. Current runner bytes must not
   be represented as attempt01 source.
2. `engineering_attempt_02`: the existing CPU environment (MuJoCo 3.15.0,
   NumPy 1.26.4) ran six hand checks once: 304 fake calls attempted, 303
   returned control steps, 3,028 fake substeps, 6 real mathematical pair
   diagnostics / 12 scalar predictions, MPC select zero, RLS zero, D reads
   zero, real physics zero, Git zero. Wall .5846141 s / CPU .453125 s. Original
   output and execution record remain. Source/test bytes are recovered after
   execution only when their current hashes match the original saved hashes;
   `recovered_execution_hash_equivalent/` states that later recovery explicitly.
3. `preflight_d_loader_01`: one explicitly authorized read-only loader check
   succeeded. Six pinned D reads / 5,690,368 bytes; three sparse11 restores,
   three cold11 initializations; no per-trial clones, prediction, update, MPC,
   physical calls, Git or old-audit replay. Construction, arrays/copies,
   snapshot/hash comparisons were nonzero computation. Wall .301057 s /
   CPU .203125 s. Runner bytes were copied before this check and are retained
   in `loader_source.py`; `execution.json` records identities and budgets.

The current small-check wrapper was not hashed or copied during attempt02.
Its later saved bytes are a current reconstruction/reference, not a proven
execution-bound original. For attempt01 the test hash matches the recoverable
test bytes, but the runner hash differs and its original bytes remain missing.
No test rerun is used to hide either provenance limitation.

## Preparatory D schema reads

Before the authorized loader preflight, schema inspection made eight successful
stdlib JSON reads: manifest twice (2 x 22,159), first audit twice (2 x 9,669),
reconciliation once (9,198), summary once (4,608,845), raw manifest once (1,220),
raw diagnostics once (1,039,277). Total 5,722,196 bytes. An initial wrong root
path for `first_reconciliation.json` raised FileNotFoundError; the correct
path is `read_accounting_reconciliation/first_reconciliation.json`.
These counts and the path failure are reconstructed from session tool output,
not an independently captured original stderr file. No fit, prediction, update,
physical interaction, Git or old-audit replay occurred in these reads.

Combined successful preparatory/preflight D reads are 14 / 11,412,564 bytes;
one failed path attempt is listed separately. Formal loading remains a future
cost and is not covered by this preflight budget.

## D binding and scientific interpretation

Six D file hashes and source commits are fixed in the runner. The D first
audit's original failed=1 (`exact_source_or_causal_identity` at
`runner_original_read_accounting`) remains unchanged. Supplemental
reconciliation was 50/0 with effective consistency verified; bound summary
was 51/0 with effective consistency verified. Loader acceptance does not
rewrite the original failure or amount to replaying its audit.

Selected sparse11 had 400 archived vector updates per seed and is frozen.
Cold11 starts with zero updates and the same qref/ranges/prior/P100/lambda1,
zero lag weights. E performs no new fit. The selected sparse11 D common-pulse
20% prediction gate failed; continuation11 is not selected for E and must
not be described as though every D model failed every prediction gate.
Even a useful E control result cannot make the full C4 scientific gate pass
while this selected model's prerequisite remains unmet.

## Final static preparation

Canonical pytest adaptation changes import/path/API handling only. It disables
the public formal flag for its rejection fixture and restores the prior value
in finally; no 304-fake rerun, D reload or physics is performed. The static
record checks unchanged fake trial/classes, unchanged main blocks apart from
that guarded flag fixture, parse/compile success, original recorded hashes,
and the runner's false formal flag. Final inventory records each delivery
file's bytes/hash. API and schema are in `API_OUTLINE.md`.

This delivery is engineering evidence only. It does not independently validate
all exception branches, numerical MPC searches, a full twelve-trial matrix,
physical control gains, scientific gates, safety or real robot behavior.
