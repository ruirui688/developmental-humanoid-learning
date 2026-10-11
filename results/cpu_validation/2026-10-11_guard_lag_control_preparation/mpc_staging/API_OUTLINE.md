# E explicit-history MPC API

Production destination: `src/developmental_physics/guard_lag_pair_mpc.py`.

```python
from developmental_physics.guard_lag_pair_mpc import FixedGuardLagPairMPC

mpc = FixedGuardLagPairMPC(lag_model, public_joint_ranges)
decision = mpc.select(q, v, target_q, previous_v,
                      previous_torque=previous_requested_torque)
```

`lag_model` must be a `GuardLagPairBodyModel`; the collector supplies a frozen
model. `previous_v` is required and contains the immediately preceding native
velocity endpoint, 20 ms before current `v` in the same uninterrupted sequence.
On reset or unknown history, acquire two native endpoints before selection;
do not substitute a zero vector. The mathematical core validates the finite
pair, while uninterrupted native provenance is the collector's responsibility.

Each candidate independently initializes from supplied `q`, `v`, `previous_v`.
Before each prediction retain `old_current_v`; call
`model.predict(predicted_q, predicted_v, torque, rollout_previous_v)`; only after
the successful prediction assign `rollout_previous_v = old_current_v`.
Model and controller store no mutable history. No future observed force, state
or target enters planning. The target is the current two-axis target.

The original default H15, nine torque values per axis, Cartesian-product order,
81 constant-vector candidates, .5 N m permission, position/velocity bounds,
summed per-axis cost, first-step-only command-change cost, exact-cost/L1/signed
torque tie order, fallback and failure accounting are unchanged. Optional
`MPCConfig` follows the old interface; E must freeze the default protocol values.

The return type is the unchanged `local_pair_model.PairMPCDecision`, including
the original `PairCandidateRecord` array. `decision.to_dict()` fields:

- `torque`, `feasible_candidates`, `fallback`, `cost`, `predicted_q`, `predicted_v`;
- `pair_prediction_attempts`, `pair_prediction_successes`;
- `scalar_prediction_attempts`, `scalar_prediction_successes`;
- `failed_pair_prediction_attempts`, `scalar_counts_complete`,
  `scalar_counts_is_lower_bound`, `unknown_scalar_failure_count`;
- `candidate_records`: `torque`, `feasible`, `cost`, `rejection_reason`,
  `completed_prediction_steps`, `pair_prediction_attempts`,
  `scalar_prediction_attempts`, `scalar_counts_complete`.

Successful mathematical predictions rejected by forecast bounds are counted
as successful pair/head calls but are not appended to the trajectory.
`PairPredictionError` contributes its exact attempted/successful scalar heads.
Unknown `ValueError` rejects the candidate and marks scalar counts as lower
bounds. Other exceptions retain their original semantics and propagate with
`pair_planning_accounting`; an existing `pair_prediction_accounting` is used.

`spec()` inherits the original spec and adds `history` metadata.
`parameter_fingerprint()` inherits the original digest of `spec()`.

No physical querying, online/offline fitting, stored-data loading, hidden
simulator state, RLS update, or policy training is implemented by this helper.
