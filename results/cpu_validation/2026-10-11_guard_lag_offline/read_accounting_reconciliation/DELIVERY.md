# Original read-accounting byte reconciliation

First and only reconciliation: `first_reconciliation.json`, 50 checks, 0
failures. Original D audit remains 4,000,346 checks, 1 failure, unchanged SHA256
`668e6ec65c949f4d7a87349e5b6076dcfeae1d53e9f770364ae4fec943b15da5`.
Its original `data_consistency_verified=false` remains unchanged.

The source-bound collector opens gzip as UTF-8 text with Python's default
universal-newline conversion, then counts `len(line.encode("utf-8"))`. Its
86,621,644 byte counter is correct for normalized text. The original auditor
expected `len(gzip.decompress(...))`, 86,628,874 raw bytes. The difference is
exactly 7,230 bytes: all 7,230 original lines have CRLF, with no bare CR/LF.
The audit's byte expectation is wrong for the collector's executed semantics;
the collector field name `trace_decompressed_bytes` is ambiguous. No original
counter, file, source, audit result or scientific threshold was modified.

The certificate binds the pinned first audit, all nine D artifacts, the D
manifest, all six original C inputs, the frozen source ZIP and fourteen source
members. AST inspection verifies the two incompatible counting expressions.
One trace decompression and one UTF-8 text-buffer pass run; no trace JSON record
is parsed, no fitting/prediction/math audit/physics/Git or online module runs.

`effective_data_consistency_verified=true` means the original full audit plus
this sole byte-unit reconciliation verifies data consistency. It preserves
`first_audit_failed=1`, and conveys no scientific or closed-loop acceptance.

Tool SHA256:
`59fb967f51b50c5ba9f42ded7bea2a68ec958b76e85f0653cdd85740493ac420`.
First certificate SHA256:
`5b9fe0a4b443cab5bcc97dc4b735caef42655780ca39ed061f0560c7a87c46d0`.

```powershell
python external/c4_lag_read_accounting_reconciliation/reconcile_read_accounting.py --input external/guard_lag_offline_20261011_first --source-root results/cpu_validation/2026-10-11_guard_exploration --first-audit external/guard_lag_offline_20261011_first_audit.json --output external/c4_lag_read_accounting_reconciliation/first_reconciliation.json
```

The output already exists and must not be repeated or overwritten. Root may
archive these original bytes and use the certificate in a single thin summary.
The tool/report schema requested by root is implemented; the directory is
sealed, and source correction for any future run must be separately recorded.
