# C4-A body freeze increment: independent static review

Outcome: static freeze increment review complete; no blocking issue found in the reviewed code, synthetic test increments, or exact elbow body protocol. This is a readiness conclusion, not a formal experimental result or independent verification of the PD archives.

## Scope and boundaries

Reviewed the current tracked auditor, runner, and synthetic test increments against the already-reviewed local-joint refactor. Read the runner's native action/observation selection and its regular, partial-interval, exception, and final checkpoint paths; read the corresponding independent audit reconstruction.

No tests, physics, training, model fitting, frozen-log replay, formal summaries, historical shoulder reevaluation, or real elbow/20–22 archive inspection were performed during this incremental review. The PD source identifiers and costs below are trusted frozen declarations supplied by the root agent; this reviewer did not verify them against real archives.

## Findings

1. The elbow declaration is native joint index 1 (`left_elbow`), supine, development seeds 0/1/2, with exact reset-seed pairs. The native eight-joint order stays unchanged. Joint-index selection is applied to encoder q/v, requested and applied torque, public joint range, reference/direction, prediction, planner, effort, and partial/exception RLS paths. Free-body `qpos[7:]` and `qvel[6:]` remain the independent all-joint correspondence; this increment does not reorder observations to disguise the elbow as shoulder zero.
2. Runner and auditor agree on `short`/`old`/`hinge5`/`endpoint_euler`, elbow PD 64/1, and the exact repository-relative elbow protocol path. The runner checks an existing exact resolved protocol path before output creation or environment construction. The auditor requires the declared metadata scope/protocol/gains before opening any ZIP or trace.
3. The immutable PD provenance tuple matches between runner and auditor: source commit `91223b39c86fbeb09f7bc399229789b1e00ce181`, audit SHA `d84ad31b28f7fcc4ded8003b2503138a3cacc9f9b2fed33bf675758e43100571`, summary SHA `5aaefe21d6aa8314673a5560522e8865123acda318e833b4951f4c5d00efc3e8`, candidate 8, paid development control calls 7,521, physics substeps 75,210, and body-model updates 0. `AuditSpec` rejects mutable/non-tuple pairs, duplicate keys, and bool values. `pd_source_matches` requires both dictionary equality and exact value types, so JSON `false` cannot impersonate integer zero despite Python's `False == 0`; JSON `true` cannot impersonate integer one. Missing, changed, or incorrectly typed elbow provenance is rejected before ZIP/trace reads.
4. Historical shoulder acceptance remains bound to its own immutable j0, supine, final-holdout 20/21/22, PD 64/0, and historical protocol. Its empty provenance declaration deliberately permits old shoulder metadata without the new field. This is static compatibility, not renewed validation of historical outcomes; no 20–22 file was read.
5. The runner still charges attempted control calls and paid physics substeps inside `finally`, retains partial parameter snapshots and successful atomic updates after later failures, refuses to score or fit a shortened interval as a complete 20 ms transition, and constructs a learned integration view only after the calibration completes. Nominal/PD/zero baselines remain independent of successful calibration. The auditor reconstructs complete or exceptional successful native updates, checks partial no-update records, reconciles paid-versus-returned phase costs, and preserves lower-bound/completeness flags rather than replacing lost telemetry with zero cost. These paths are unchanged by this freeze increment.
6. The already-reviewed gate structure stays independent: five required trials for the same-MPC model contribution, six for the PD comparison, seven for matrix completeness. Zero or PD failure cannot erase a valid five-trial model contribution. The code matrix is 21 trials, with complete-run caps 6,000 control calls, 60,000 physics substeps, and 900 calibration updates; actual/failed costs must still be reported.
7. The synthetic test increments address unfinished None gains, exact wrong protocol, runner/auditor declaration equality, immutable provenance rejection, and missing/wrong/bool provenance before trace access. In particular `bool_updates=False` tests the easily missed bool-zero equality case. This review only inspected these tests; the root agent owns test execution.

## Exact protocol cross-check

Read the completed `docs/ELBOW_BODY_DEVELOPMENT_PROTOCOL.md` in full. It matches the declared native j1/supine development 0/1/2 scope, unchanged eight-joint ordering, cold-start recipe and initial coefficients/covariance, PD 64/1, complete provenance tuple and all-candidate paid PD cost. It explicitly separates method startup/calibration/control from shared prediction evaluation and PD tuning, prohibits historical shoulder parameter/log reuse, and says a formal run requires committed clean sources.

The fixed trial/phase totals agree with the runner's seven-trial matrix: 21 trials, 6,000 control calls, 60,000 substeps, 900 updates, 120 simulated seconds; prefix 2,100/21,000, calibration 900/9,000, prediction 600/6,000, control 2,400/24,000. The schedule's stated request efforts (0.55 absolute and 0.20 squared units) are consistent with ten amplitudes and 10 nonzero 20 ms calls per block. Native stop thresholds, prefix exception, terminal and partial handling, dependencies, failure continuation and fatal blocking agree with the runner/auditor paths reviewed above.

The 5/6/7 gates reproduce the code's trial completeness, per-seed and mean-RMSE thresholds, PD active actual effort limits, and zero-denominator semantics. They are explicitly independent and make no locomotion, real-robot, unknown-dynamics or safety claim. Full-body diagnostic reporting does not become a full-body learned-controller claim. The declared cumulative baseline 216,371/2,163,710/9,900 and projected complete total 222,371/2,223,710/10,800 are arithmetically consistent; their historical base is not independently verified by this static reviewer. Protocol-relative Markdown targets exist; their contents/results were not read as part of this increment review.

## Snapshot

UTC: 2026-10-11T06:26:50.041895+00:00

HEAD: `91223b39c86fbeb09f7bc399229789b1e00ce181` (working-tree code snapshot; hashes below disambiguate uncommitted changes)

Final protocol-review UTC: 2026-10-11T06:27:27.867204+00:00

| File | SHA-256 |
| --- | --- |
| `scripts/audit_local_frozen.py` | `b5fea70d3733a1bab77e49bf559432475899436693cf6c1b0b4767369c913461` |
| `src/developmental_physics/local_frozen_validation.py` | `369e44371dd7b4e5a91010fd2f8dae515cf390fd2fbe171257414a5c94aabf1a` |
| `tests/test_local_frozen_audit.py` | `7873bda08fd7076aa18b3853c5ce00ab87869395693db4d0a8f05f2dec65f2ea` |
| `tests/test_joint_frozen_audit.py` | `f9fb6dbc85dec58d697dbd40ccfbd8402bc126bca002afce9279654750fa0df3` |
| `tests/test_local_frozen_validation.py` | `018f0bedfff98c04c65be7126dd251abc31ea885d3940bb9b02b48abfb83bad8` |
| `docs/ELBOW_BODY_DEVELOPMENT_PROTOCOL.md` | `e94227a9d657a6700b1fa0fd89cfad761bfec01dfd160ed6ee2ba61352cc7996` |

Prior full refactor static review: `external/c4a_body_audit_cross_review.md`, SHA-256 `7422470b64e75788207bb07ae93592f5d97dff689a00028404b558fca0d3a57b`. This report covers the freeze increment and does not repeat that review's checks.
