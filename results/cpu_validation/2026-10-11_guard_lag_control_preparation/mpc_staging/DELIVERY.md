# E MPC staging delivery

`guard_lag_pair_mpc.py` is ready for root-only promotion to
`src/developmental_physics/guard_lag_pair_mpc.py`. No old source was modified.
The new controller inherits the old specification and fingerprint methods and
copies initialization and selection with only model type / explicit-history
input and recurrence changes. Both returned dataclasses are reused unchanged.

Source SHA256:
`2f6c9f4f7f7f128157897f67d40a6cfef09fef582aaeac55945d28399a59d97d`.
Protected old MPC/core file SHA256:
`81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df`.

First and only small handwritten engineering execution:
`engineering_01/run.json`: **9 passed / 0 failed**. Source snapshots are retained
inside that directory. It checks default H15/81 metadata without rolling out
that matrix, independent candidate histories with a three-step two-candidate
fixture, original cost, signed and magnitude tie order, bounds/fallback,
known/unknown head failures, known/unknown fatal propagation, mandatory input
validation, and a two-step frozen zero-lag prior. Wall .09488689992576838 s;
CPU .03125 s.

Mathematical budget, including deliberately injected failure cases:

| Category | Attempts | Successes |
| --- | ---: | ---: |
| Artificial model pair calls | 21 | 17 |
| Artificial scalar heads, known lower bound | 38 | 36 |
| Real frozen prior pair calls | 2 | 2 |
| Real frozen prior scalar heads | 4 | 4 |

There were two unknown-head-accounting failures and two known second-head
failures; they are intentional fixtures, not test failures. The independent
hand reference additionally performed six pair steps / twelve scalar velocity
steps and six summed-cost reference steps. Physical queries, RLS updates,
training and raw-data reads were all zero. No D/C result files were opened.

One subsequent AST-only check, `source_ast_01.json`, **5 passed / 0 failed**,
confirms old/new init and select equivalence after removing exactly the new
model type/history changes, original inheritance, required previous velocity,
and absence of stored controller history. Model imports and predictions were
zero. `verify_source_once.py` retains the exact transformation; its output uses
exclusive creation so it cannot overwrite the first record.

There is no new scientific result or acceptance-gate decision in this helper
delivery. Root handles protocol freezing, formal collection, independent audit,
archival and Git. Promotion should use source/AST/signature checks only; do not
repeat the passed mathematical fixtures. The engineering folder is not a
substitute for an E physical control result.
