# Staging integrity

All files written by this helper subtask are under
`D:\Codex_ws\robot_rl\external\c4_lag_model_staging\`, ignored by `.gitignore`
line 41 (`external/`). The old sources were read/imported only. Python ran with
`PYTHONDONTWRITEBYTECODE=1` to prevent import bytecode writes elsewhere.

The before/after source HEAD was
`5ea8df42b09588845760daf0dc1f270aef2a87f1`. The tracked status was identical at
the snapshots: four existing modified documentation files (`AGENTS.md`,
`README.md`, `docs/CONTINUOUS_EXECUTION_PLAN.md`, `docs/PROGRESS.md`) and the
existing untracked `docs/GUARD_EXPLORATION_DEVELOPMENT_RESULTS.md`. This subtask
performed no tracked edits, commits, checkout/reset, or push.

Five imported old-core files have identical before/after SHA-256:

| Source | SHA-256 |
|---|---|
| `src/developmental_physics/local_model.py` | `f51a43c36675980cddd0cbf1fcba576469dd015e0850833ae58ffc32479de2b1` |
| `src/developmental_physics/local_pair_model.py` | `81e0c9147bbfd7f825f14ad7439e6752c021bc08922abd04589a89b59fc509df` |
| `src/developmental_physics/guard_pair_model.py` | `2b8ae6f17aa12f1230daf38d8858f24bde3a3c21342e46a5b8fa6e91dc3da3b3` |
| `src/developmental_physics/guard_coupled_pair_model.py` | `7f234760e8f3d5b9cc799c871e84e7adfebecdf92e11f315735fad8b38ad78ed` |
| `src/developmental_physics/__init__.py` | `d2ee9d572836752f5f8404bfdf1fca8add0d62b9858f4c6dcd9cf7ddc6c53ea2` |

The first run's JSON contains the exact SHA-256 of the candidate and test
source, alongside per-event mathematical cost and environment information.
Numbered source copies preserve the tested byte sequences. No run failure
has occurred; the expected fault-injection cases are retained in the log and
per-event ledger with their actual proposal/publish cost.

The runner and helper never read any research raw file and perform no fit
bank, collector or physical query. No MuJoCo module was loaded. A JSON status
snapshot is provenance metadata, not scientific evidence.
