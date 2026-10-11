# FR4 first PD-anchor parameterization contract

Preparation only. Root executes the new script once after static review:

```powershell
python external/fr4_controller_candidate/check_pd_anchor_mapping_once.py --repo . --output external/fr4_first_mapping_contract/contract.json
```

The default controller and Counted-adapter sources are the new production
`pd_anchor_pair_mpc.py` and `pd_anchor_pair_development.py`. The adapter class is
bound by source identity and exact AST, then defined alone; the physical
collector is not imported. No raw file, saved parameter or old result is read.

Four direct mappings cover on-grid identity, non-grid replacement, clipped
endpoints, and binary-exact equal-distance ties resolved by original index.
They check the original slot order, 81 unique Cartesian points, exactly one
delta-zero pair and unchanged nominal constant. No old mathematical check is
invoked.

Two new synthetic selection states cover non-grid PD and exact nearest ties.
Each runs scalar and the supported new-Counted batch implementation once:
four selector calls, at most 48,600 pair / 97,200 scalar predictions. The
contract checks new candidate roundtrip records, the current-PD anchor record,
static controller fingerprint, no model mutation, full scalar/batch decision
equality and matching Counted costs. It does not assert that the PD anchor is
feasible or selected and does not rerun old cost, tail or physical tests.

Each declared case has one attempt. Failures retain their first traceback,
completed checks and paid counters; the script refuses an existing output.
There is no automatic retry, fit, RLS, physics or saved-snapshot restoration.

The controller preparation receipt and derivation diff document source-only
AST comparison: both selector cores equal FR3 after removing the single new
candidate-generation assignment and restoring the iterated candidate name;
constructor, support checks and wrapper-code checks are unchanged.
