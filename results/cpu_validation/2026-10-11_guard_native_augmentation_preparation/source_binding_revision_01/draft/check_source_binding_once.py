"""One new synthetic D manifest-identity contract check; no old checks."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REVISION = Path(__file__).resolve().parent
STAGING = REVISION.parent
spec = importlib.util.spec_from_file_location("repaired_L_source_binding", STAGING/"develop_guard_native_augmentation.py")
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)


if __name__ == "__main__":
    output = REVISION/"CHECK_SOURCE_BINDING_01.json"
    if output.exists():
        raise FileExistsError("preserve first source binding check")
    actual = {"bytes": 111, "sha256": "a"*64}
    annotated = {**actual, "original_path": "synthetic/archive/diagnostics.json", "copy_verified": True,
                 "annotation": "extra notes never establish identity"}
    checks = {
        "extra_archive_fields_accepted": L.file_identity_matches(annotated, actual),
        "bytes_tamper_rejected": not L.file_identity_matches({**annotated, "bytes": 112}, actual),
        "hash_tamper_rejected": not L.file_identity_matches({**annotated, "sha256": "b"*64}, actual),
        "missing_bytes_rejected": not L.file_identity_matches({"sha256": actual["sha256"], "copy_verified": True}, actual),
        "missing_hash_rejected": not L.file_identity_matches({"bytes": actual["bytes"], "copy_verified": True}, actual),
        "annotation_only_rejected": not L.file_identity_matches({"copy_verified": True}, actual),
    }
    result = {"synthetic_only": True, "new_contract_check_count": 1, "checks": checks,
        "passed": all(checks.values()), "actual_trace_or_weights_reads": 0, "model_restorations": 0,
        "fit_calls": 0, "model_predictions": 0, "physics_calls": 0, "RLS_updates": 0,
        "old_four_branches_repeated": False, "K_math_checks_repeated": False,
        "source_sha256": {name: hashlib.sha256((STAGING/name).read_bytes()).hexdigest() for name in (
            "develop_guard_native_augmentation.py", "GUARD_NATIVE_AUGMENTATION_DEVELOPMENT_PROTOCOL.md")},
        "check_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": {"python": sys.version, "numpy": L.np.__version__}}
    output.write_bytes(L.json_bytes(result))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if not result["passed"]:
        raise SystemExit(1)
