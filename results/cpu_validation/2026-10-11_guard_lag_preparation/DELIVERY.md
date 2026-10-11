# C4 explicit velocity-history candidate — ignored staging delivery

This is an unpromoted, pure NumPy helper and a small handcrafted mathematical
check suite. It is not a collector, fitted research model, controller, adoption
result, or evidence of body/control learning.

## Candidate and causal interface

`guard_lag_pair_model.py` defines `GuardLagPairBodyModel`, independently of
`PairBodyModel`'s supported structures. It does not modify the old core.

The existing global columns remain
`[v0,v1,q0-qref0,q1-qref1,startG0,startG1,hG0,hG1,1]`.
The only added columns are `[v0-previous_v0,v1-previous_v1]`. Both output heads
have zero cold coefficients in these two columns. The unchanged cold own-axis
velocity/command coefficients are `1/.02`; other cold coefficients are zero.
The prior covariance is `100 I11`, forgetting factor is `1`, hinge threshold
is `.25 Nm`, complete interval is `.02 s`, and position prediction uses
endpoint Euler. Prediction uses an ordinary 11-column NumPy dot. The proposal
arithmetic reuses unchanged `PairBodyModel._propose_update`.

The exact interfaces are:

```python
predict(q, v, u, previous_v)
update(q, v, u, next_v, previous_v, *, transition_id)
clone_frozen()
```

`previous_v` has no default. Unknown/reset history cannot be filled with zero.
The caller must first possess two consecutive native velocity endpoints from
the same uninterrupted 20 ms sequence. This helper checks shape/finiteness,
but temporal provenance must be validated by a future source-bound caller.
The future prefix must retain its returned native endpoints and pay for all
prefix interaction without calling this update method. No prefix controller
or source reader is implemented here.

The model stores no history. A future MPC caller must begin each candidate
with the same native history and, after each predicted step, assign the old
current velocity to `previous_v`. The old `FixedPairMPC` cannot yet consume this
new explicit-history API and was not modified or run.

`next_v` is only an RLS label. Features contain current q/v, immediately prior
native v, the already known request and the public start-angle guard. There
is no input for future realized torque or simulator state. The start guard
still does not reveal within-interval switching or average realized torque.

Both heads, covariance and cumulative count are published through one
immutable state reference only after both proposals validate. Frozen clones
copy all parameter/covariance/count state, initial coefficients and public
configuration, without sharing arrays with the source.

## First artificial run

`run_001_math.log` records 8 tests, 0 failures, 0 errors. Tests cover the cold
prior/explicit feature order; zero-lag same-coefficient old9 equivalence;
independent scalar one-transition RLS calculation; missing/invalid history;
second-head rejection and IO failure; interruption immediately before/after
the sole publish; frozen clone ownership; and repeated prediction/three-step
history advancement purity.

The six fixed zero-lag cases had maximum absolute prediction difference `0`
against old9 on this NumPy build. The assertion is `rtol=1e-12, atol=1e-14`,
because 9-column and 11-column floating-point summation need not be bitwise
identical on other builds. This is mathematical/roundoff equivalence, not a
new fit or a physical comparison.

The test runner instruments the caller, not the helper. `run_001_math.json`
retains each feature/prediction/proposal/update event and per-test totals,
including imported old9 reference prediction calls:

| Actual mathematical cost | Attempts | Successful calls/proposals |
|---|---:|---:|
| Feature evaluation | 45 | 35 |
| Pair prediction | 31 | 26 |
| Scalar output prediction | 52 | 52 |
| RLS scalar proposal | 16 | 14 |
| Update API call | 15 | 4 normal returns |

There were 5 committed handcrafted vector updates / 10 scalar updates.
The after-publish interruption contributes one committed vector update even
though the caller raised `KeyboardInterrupt`; the before-publish interruption
contributes zero. Other expected rejected/invalid/frozen update calls publish
zero. The 11 failed update API calls are deliberate test cases, distinct from
the suite's zero test failures. Four successful numerical output proposals
were not published in the before-publish interruption and second-head failure
checks. Proposal success and committed update cost therefore remain separate.

Measured inside the test process: wall `0.0878874 s`, process CPU `0.046875 s`
(`0.03125 s` user + `0.015625 s` system). Python startup/import time is excluded
from these internal values. Environment: Python `3.10.11`, NumPy `1.26.4`,
`D:\Python3.10\python.exe`, Windows CPU. MuJoCo was not imported.

Formal research additions are zero: 0 real raw-data reads, 0 physical control
calls/substeps, 0 real online/offline scalar updates. The artificial arithmetic
above is retained separately and does not change the formal cumulative ledger.

## Reproduction and retention

From the repository root, run only this small artificial suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'D:\Codex_ws\robot_rl\src'
python external/c4_lag_model_staging/test_guard_lag_pair_model.py
```

Every invocation creates a new numbered log/JSON and copies of both source
files before testing. It retains failures and their exact source hashes;
existing run files are not overwritten. Only `run_001` has been executed.
See `INTEGRITY.md` and `source_before.json` / `source_after.json` for the old
source checksums and unchanged Git status captured around this delivery.

No tracked promotion, Git mutation, old test matrix, raw-data fit, or physics
was performed. Any future offline replay or physical validation requires its
own frozen protocol and separate actual cost ledger. Mathematical pass does
not resolve the previous C4 control failures or pass C5/C6 scientific gates.
