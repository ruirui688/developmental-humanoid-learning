# C4-A left-elbow classical PD development evidence

2026-10-11. Exact-byte archive of one clean-source collection and its first audit and one independent summary. No physical, audit, summary, prediction or fitting replay was performed during archival.

- Frozen source: `91223b39c86fbeb09f7bc399229789b1e00ce181`; supine / j1, development0/1/2, nine fixed PD candidates.
- 27 attempted trials: 24 complete, 3 native StudyAbort; 7,521 calls /75,210 substeps /0 parameter updates. All gain-development costs and paid prefixes remain included.
- Candidate8 Kp64/Kd1 selected; raw three-seed RMSE mean0.006209216810408326rad. Candidate6 Kp64/Kd0 failed in all seeds and cannot be ranked by its truncated RMSE.
- First audit352,833 checks /0 failures; independent summary84,356 /0. These are consistency and development evidence, not safety, body-learning, full-body or unseen-seed claims.

## Files

- [Raw development archive](development/manifest.json): metadata, all27 outcome records, compressed native traces and original-byte source ZIP.
- [First audit](audit.json), [audit source](audit_source.py), [audit stdout](audit_stdout.txt), [collection stdout](collection_stdout.txt).
- [Independent summary](summary.json), [executed source](summary_source.py), [wrapper](summary_wrapper.py), [permanent attempt lock](summary_attempt_lock.json), [stdout](summary_stdout.txt), [execution provenance](summary_execution.json).
- [Delivery report](result_delivery.md), its [formatting source](report_source.py) and [execution](report_execution.json). Formatting reads only the saved summary; it does not redo the raw summary.
- [Protocol](protocol.md), [static protocol review](reviews/protocol_cross_review.md), [technical preparation plan](reviews/technical_plan.md).
- [Pre-collection full regression stdout](tests/full_regression_stdout.txt): 880passed /13skipped /119.00s. The two test sources in tests/ are exact Git blobs from the collection commit. preparation/ retains the earlier staged source bytes and is not presented as the final executed implementation.
- [Final manifest](manifest.json) covers every file except itself, with byte count, SHA256 and exact copying source. [Archival source](archival_source.py), [stdout](archival_stdout.txt) and [execution record](archival_execution.json) describe read-only copying and verification.

[Results and scientific limits](../../../docs/ELBOW_PD_DEVELOPMENT_RESULTS.md). Source ZIP content is this repository's own code/assets; no external datasets or pretrained checkpoints are added. Git `-text` protects original bytes.
