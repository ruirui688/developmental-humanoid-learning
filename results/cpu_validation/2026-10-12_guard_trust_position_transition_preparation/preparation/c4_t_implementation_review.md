# T implementation static review

T is one new numerical candidate from frozen Q, with pinned S scientific kernel/population/runtime reused. Author did not import or execute T, self-check, model, objective, gradient, fitting or scientific payload. No physics or updates were added.

Final source: 46,376 bytes, SHA256 52d20acbb2de7be9909f983f8028d536c15133789082bfe0655c13a8a98a41f2.
Final protocol: 8,656 bytes, SHA256 cb1c43dfccc67e3afffa112fa8127c8494423b0fed2ee0130b99c501cc6e4b41.

Independent reviewer /root/next_control_direction/j_causal_contract_review read only the new T source once (45,671 bytes, f2cc34aea9419708b78711144c69ab4289376c5718095a645aeabd6570c08f86) and protocol once (8,441 bytes, eae81b960b1bd7269b2aa3237a699e9bd35b1058c0f82b11264352e0c999fc67). Reviewer did not read old source or saved scientific payload, or import/run any code. Total reviewer reads: 2 / 54,112 bytes; measured timing remains in reviewer ledger and is not fabricated here. Final static deltas were supplied as exact descriptions without rereading full source.

Reviewer fixes retained:
- Numerical failure cannot mask a structural/internal exception as time-budget stop. Only NonFiniteTrial for role=trial may take failed-objective exit time budget; other exceptions remain fatal, all accepted snapshots evidence only.
- Fixed input state/history/request/qref/weights failures stay fatal; the S conversion whitelist contains only computed numerical results.
- Every trial event records origin_objective_id at creation, including rejected numerical and crossing partial trials.
- Additional optimizer-only synthetic fixture requires a structural error after a genuine accepted update and outside time boundary to remain nonbudget failure/no candidate.
- Root confirmed archived S root manifest has no status field; only root hash/bindings and raw manifest/run failed statuses are checked.

The new optimizer has fixed normalized true-gradient direction, alpha=.001 reset, Armijo c=.0001, beta=.5, 10 trials/update, 30 accepted updates, 100 objectives/seed and 120s entry/exit/registration boundaries. Initial0 never publishes. All10 rejection and nonbudget failures publish no candidate even after accepted evidence. Post-persistence crossing cannot replace last registered accepted update. Always-recursive nonfinite JSON encoding covers completed runs with rejected partials; candidates independently require finite arrays. K/Q/D and the scientific loss/gates are preserved.

AST/compile, canonical new function references, frozen S pin literals, LF, trailing whitespace and protocol links passed. Four static author validation passes are all counted in c4_t_preparation_reads.json; repeated source reads arose only from necessary static review patches, with no repeated math or fixture execution. Parent owns first self-check, clean source/protocol freeze, first formal execution, saved evidence, Git and reporting. Static readiness is not scientific acceptance.

