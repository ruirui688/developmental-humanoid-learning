# FR4A first saved-evidence audit candidate

Prepared only; not imported or executed. Root runs this new audit once with the
clean source commit recorded by the first FR4A run:

```powershell
python external/fr4a_audit_candidate/audit_pd_anchor_pair_prediction.py --repo . --raw results/cpu_validation/2026-10-12_pd_anchor_pair_prediction/raw --source-commit <exact-40-character-FR4-source-commit> --output external/fr4a_first_saved_audit
```

The output must be new and outside the immutable raw directory. The sole raw
input directory is the new FR4A directory above; seeds are 8101/8102/8103.
Nineteen source members must match the new runner dependency list and the
archived source commit, including the PD-anchor controller, collector, runner
and protocol. The new protocol bytes/hash match the runner's fixed pin.

This is a namespace/path/seed derivation of the FR3A source auditor. All 25
top-level class/function AST units remain identical after those documented
substitutions. Import statements, prediction/RLS/snapshot/effort/contact
arithmetic, serialization tolerances, complete-population requirements and
original scientific gates are preserved. No model is imported, restored or
called; no fit, RLS update or physical step is performed.

Bounds remain 21,000 trace records, 2,886 prediction records, 124,680 saved pair
path steps, 30 model/horizon groups, six trials, three seeds and nineteen
source members/Git reads. Only new saved prediction RMSE and the unchanged
new FR4A gate arithmetic are checked; no old scientific result is recomputed.
Stops, missing populations, paid counters and NA remain present; there is no
partial ranking or automatic retry. An audit pass establishes saved-evidence
consistency, not a scientific or control-gate pass.

The preparation receipt records eight static source contracts and the exact
auditor identity. The first missing preparation-document lookup is retained
separately; it did not execute an auditor or read any raw/model parameters.
