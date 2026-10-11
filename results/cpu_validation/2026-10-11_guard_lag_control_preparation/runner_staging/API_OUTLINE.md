# E runner delivery API

Runner staging remains closed: `FORMAL_CONTROL_ENABLED=False`. Root alone may
promote the runner and release a clean, frozen formal execution. This delivery
does not authorize physics.

## Public interfaces

- `run_guard_lag_control_development(output, *, protocol_path=None)` rejects
  immediately when the formal flag is false, before source reads, Git, output
  creation or environment construction.
- `load_d_models(repository_root)` reads six pinned D files once, restores three
  complete sparse11 final snapshots and initializes three independent cold11
  models. It performs no prediction, update, refit or old-audit replay.
- `restore_lag_snapshot(snapshot)` checks all state, constants and fingerprint;
  only the archived `trainable=True` flag is normalized to frozen `False`.
- `run_trial(result, models, episode, writer, pd, *, env_factory,
  mpc_factory=None)` accepts explicit hand environment/planner injection. The
  fixed two model names and original PD gains are checked. No monkeypatch of
  the old collector is needed.
- `native_history(endpoints, observation, trial_id, step_index)` requires two
  contiguous, complete, unstopped past native endpoints. Unknown history raises.
- `target_pair(active, qref, directions, ranges)` retains the original C inline
  target rule, including the active100 switch without preview.

Formal paths are `src/developmental_physics/guard_lag_control_development.py`,
`src/developmental_physics/guard_lag_pair_mpc.py`,
`docs/GUARD_LAG_CONTROL_DEVELOPMENT_PROTOCOL.md`, and
`scripts/audit_guard_lag_control.py`. Five audit support paths are recorded in
the runner. Root supplies the formal protocol/auditor and owns Git checks.

## Matrix and accounting

The fixed twelve trials use three seeds and four groups: cold11,
learned_sparse11, PDselected and zero. Each fresh trial has 100 prefix and 200
active steps. Maximum physics is 3,600 calls / 36,000 substeps / zero updates.
Two diagnostic model calls occur independently at every active start in all
groups: maximum 4,800 pair predictions. Two MPC groups add at most 1,458,000
planning pair predictions. Constructing/restoring/cloning immutable models is
nonzero computation and is separately recorded.

Preserved conditions: supine/baseline, j0 shoulder and j1 elbow, other requests
zero, 20 ms control / ten 2 ms substeps, target .04 then .08, per-axis .5 Nm,
native position .12 or speed 1 research stops including equality, H15,
81 constant-vector candidates, unchanged costs/ties/fallback, and PD Kp=(64,64)
with Kd=(0,4). The runner never declares scientific gates.

## Serialized schema

`episodes.json` and `seed_results.json` are bare lists; `metadata.json` is a
dictionary. Trace rows are JSON in gzip. Regular rows retain old C physical
fields and add `history`, both `predicted_next_qv`, guard/native-history
`model_input_diagnostics`, frozen fingerprints, planner input/decision, and
cumulative diagnostic accounting. `exploration_diagnostics` and `model_update`
are explicitly null.

`history` contains `current_v_rad_s`, `previous_v_rad_s`,
`history_transition_ids`, and `native_contiguous=true`. At the first active
step, endpoint IDs are trial:98 and trial:99. Models use native current and
previous velocities; no future realized torque or privileged plant state is
read by the model.

Exception rows expand `_exception_snapshot(env)` at top level. They retain
`returned_step_diagnostics`, observations, target, predictions, history,
planner input/decision and failure accounting when available. There is no
nested `exception_snapshot` field. Ordinary exceptions stay local; write/IO,
interrupt and system exit are fatal. All seed ledgers are initialized in
advance; fatal remaining trials/evaluations become blocked.

Actual effort and valid full endpoint errors are accumulated before `_emit`.
A unique complete returned-but-unwritten endpoint can therefore appear in
stored metrics while its trial remains exception/ineligible. Partial intervals
are paid and kept outside full metrics. Missing or invalid actual torque
histories remain explicit lower bounds; missing histories are never zero-filled.

## Canonical test adapter

`test_guard_lag_control_development.py` is for promotion to
`tests/test_guard_lag_control_development.py`. It imports the canonical runner,
uses `pytest.importorskip('mujoco')`, and calls only the original explicit fake
environment fixtures. Its public-entry rejection fixture temporarily sets
the formal flag to false and restores the prior value in `finally`, so a
promoted true flag cannot launch physics during pytest. This adapter receives
AST-only verification here, not a second fake execution.
