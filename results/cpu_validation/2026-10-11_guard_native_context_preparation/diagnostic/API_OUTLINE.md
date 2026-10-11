# F saved native-context diagnostic API

Canonical destination: `scripts/diagnose_guard_native_context.py`.
Staging keeps `FORMAL_DIAGNOSTIC_ENABLED = False`.

```powershell
python scripts/diagnose_guard_native_context.py `
  --archive results/cpu_validation/2026-10-11_guard_lag_control `
  --binding docs/guard_native_context_source_binding.json `
  --source-manifest-sha256 <root-frozen-E-outer-manifest-SHA256> `
  --output external/guard_native_context_first
```

The binding path/name above is illustrative; root freezes its actual committed
path. Required binding schema:

```json
{
  "schema_version": 1,
  "archive_relative_path": "results/cpu_validation/2026-10-11_guard_lag_control",
  "e_source_commit": "<40 lowercase hex>",
  "source_manifest_sha256": "<64 lowercase hex>",
  "first_audit_sha256": "<64 lowercase hex>",
  "summary_sha256": "<64 lowercase hex>",
  "raw_manifest_sha256": "<64 lowercase hex>",
  "protocol": {"path": "<committed F protocol path>", "sha256": "<64 lowercase hex>"}
}
```

Formal execution requires clean tracked HEAD and exact committed bytes of the
executing canonical script, binding, and F protocol. The external CLI manifest
SHA must agree with the committed binding; a self-computed current manifest SHA
cannot authorize an input. Before any descriptive math, hash/size-check E outer
manifest, first audit, once-saved summary, raw manifest, metadata, episodes and
trace; verify the exact first-audit `archive.source_commit/input_hashes` schema,
saved summary copies and original physical ledger. No alternate field fallback.

Source binary files are read once into a new task cache, with actual SHA/size
retained even on preflight failure. Only the cache is parsed/decompressed;
compressed cache bytes and binary decompressed bytes are separately measured.
Seed results and source ZIP are not parsed, imported or replayed; their sealed
manifest/first-audit byte identities are cross-bound only.

Engineering core `diagnose_rows(rows, episodes, fee=None)` consumes supplied
row objects without any I/O. It returns all fixed seed/kind/axis/predictor/q-v/
target-segment/window groups, three fixed score descriptions, fixed bins,
signed/absolute Pearson descriptors, full denominators, event tables,
exception notifications and derived rows. No model or simulator is imported.

Regular endpoints have unique original transition identities. Exception notices
with duplicate or missing ID are retained separately. A unique exception row
is considered a new returned endpoint only when the original episode's returned
and unwritten ledger proves it; no endpoint is inferred from diagnostics alone.
Two previous full, contiguous, unstopped endpoints and original history IDs/v
are required for a valid saved 20 ms prediction error. Native acceleration
changes only use before/previous-before. Partial intervals never enter full
error/correlation/bin statistics. Stop windows require source status terminated;
exception outcomes with stop flags remain separately disclosed.

Runtime output: `derived.jsonl`, `description.json`, `run.json`, `manifest.json`,
and the immutable task source cache. First failure/logs are preserved; existing
outputs cannot be overwritten. Scientific adoption is always unevaluated/false;
saved E gates are copied only and never re-evaluated by F.
