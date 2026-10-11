"""Explicit PD-source binding; no simulator, subprocess, or Git access.

Future promoted path: ``src/developmental_physics/pd_selection_binding.py``.
This helper verifies source identity and the previously validated selection. It
does not rerun the independent audit or inspect physics traces/episodes.
The caller must obtain ``tracked_paths`` from its separately verified clean
source commit. A supplied list is caller evidence, not a Git check by this module.

The only accepted selection JSON schema is::

    {
      "schema": "c4-pd-selection-v1",
      "status": "selected",
      "selected": {
        "candidate_id": 4,
        "joint_indices": [0, 1],
        "kp": [64.0, 64.0],
        "kd": [1.0, 1.0]
      },
      "protocol": {"path": "docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md", "sha256": "..."},
      "sources": {
        "manifest": {"path": "results/pd/manifest.json", "sha256": "..."},
        "audit": {"path": "results/pd/audit.json", "sha256": "..."}
      }
    }

The numbers above illustrate syntax only; they are never default gains.
All objects have exactly the listed keys. Hashes are lowercase SHA-256 of the
original bytes. Paths use canonical repository-relative POSIX spelling.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from types import MappingProxyType
from typing import Iterable, Mapping
import zipfile


PD_PROTOCOL_PATH = "docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md"
PD_AUDITOR_PATH = "scripts/audit_pair_pd.py"
PD_COMMON_AUDITOR_PATH = "scripts/audit_local_frozen.py"
PD_KD_CANDIDATES = [[shoulder, elbow] for shoulder in (0.0, 1.0, 2.0) for elbow in (1.0, 2.0, 4.0)]
PD_AUDIT_SCOPE = {
    "synthetic_fixture": False, "scientific_frozen": True,
    "suite": "pair_pd_development", "protocol": PD_PROTOCOL_PATH,
    "collector": "src/developmental_physics/pair_pd_development.py", "auditor": PD_AUDITOR_PATH,
    "seeds": [0, 1, 2], "kp": [64.0, 64.0], "kd_candidates": PD_KD_CANDIDATES,
    "prefix_steps": 100, "control_steps": 200, "joint_indices": [0, 1], "pose": "supine", "split": "development",
}
PD_METADATA_FIELDS = {
    "suite": "pair_pd_development", "synthetic": False, "backend": "MuJoCo CPU", "gpu": None,
    "pose": "supine", "joint_indices": [0, 1], "native_joint_count": 8,
    "seeds": [0, 1, 2], "split": "development", "kp": [64.0, 64.0], "kd_candidates": PD_KD_CANDIDATES,
    "prefix_steps": 100, "control_steps_per_trial": 200, "target_offsets_rad": [0.04, 0.08],
    "target_information": "own paid native qref plus direction; current target only; no preview or clipping",
    "study_abort_spec": {"active_only": True, "absolute_q_minus_qref_rad": 0.12,
        "absolute_velocity_rad_s": 1.0, "comparison": ">=", "any_axis": True,
        "feedback_action": None, "complete_terminal_scored_not_complete": True},
    "pd_controller_spec": {"implementation": "feedback_validate.pd_request per original j0/j1",
        "permission_nm": 0.5, "body_model_input": False, "gain_updates": 0},
    "parameter_updates": {"body_model": 0, "policy": 0, "gains": 0}, "model_updates": 0,
    "teacher_calls": 0, "external_demonstration_samples": 0,
}
PD_ENVIRONMENT_FIELDS = {"physics_dt": 0.002, "control_substeps": 10, "torque_limit": 0.5,
    "joint_speed_limit": 20.0, "joint_limit_margin": 0.08, "kinetic_energy_limit": 50.0,
    "reset_clearance": 0.005, "ground_contact_profile": "baseline"}


class PDSelectionBindingError(ValueError):
    """The explicit selected candidate or a required source is not bound."""


class PDSourceBinding(dict):
    """JSON-compatible public record retaining the exact validated source bytes."""

    def __init__(self, record: dict, source_bytes: Mapping[str, bytes]):
        super().__init__(record)
        self._source_bytes = MappingProxyType(dict(source_bytes))

    def archive_source_bytes(self) -> dict[str, bytes]:
        """Return the already validated bytes, without rereading any source."""
        return dict(self._source_bytes)


def _path_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PDSelectionBindingError(f"{label} must be a nonempty canonical relative path")
    if "\\" in value or ":" in value or "\x00" in value:
        raise PDSelectionBindingError(f"{label} must use repository-relative POSIX spelling")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise PDSelectionBindingError(f"{label} must be relative")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise PDSelectionBindingError(f"{label} contains a noncanonical path component")
    if posix.as_posix() != value:
        raise PDSelectionBindingError(f"{label} is not canonical")
    return value


def _hash_name(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise PDSelectionBindingError(f"{label} must be a lowercase SHA-256")
    return value


def _exact_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise PDSelectionBindingError(f"{label} must have exactly {sorted(expected)}")
    return value


def _gain_pair(value: object, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise PDSelectionBindingError(f"{label} must be an explicit two-element array")
    gains = []
    for gain in value:
        if isinstance(gain, bool) or not isinstance(gain, (int, float)):
            raise PDSelectionBindingError(f"{label} must contain finite nonnegative numbers")
        try:
            numeric = float(gain)
        except (OverflowError, ValueError) as exc:
            raise PDSelectionBindingError(f"{label} must contain finite nonnegative numbers") from exc
        if not math.isfinite(numeric) or numeric < 0:
            raise PDSelectionBindingError(f"{label} must contain finite nonnegative numbers")
        gains.append(numeric)
    return gains[0], gains[1]


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PDSelectionBindingError(f"selection JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise PDSelectionBindingError(f"selection JSON contains nonstandard numeric constant {value}")


def _json_record(raw: bytes, label: str) -> dict:
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                            parse_constant=_invalid_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PDSelectionBindingError(f"{label} must contain strict UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise PDSelectionBindingError(f"{label} must be a JSON object")
    return parsed


def _json_exact(left: object, right: object) -> bool:
    """JSON equality with type checks; bool/int and float/int cannot alias."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(_json_exact(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_json_exact(a, b) for a, b in zip(left, right))
    if isinstance(left, float) and not math.isfinite(left):
        return False
    return left == right


def _read_bytes(root: Path, name: str, label: str) -> bytes:
    try:
        path = (root / name).resolve(strict=True)
        path.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise PDSelectionBindingError(f"{label} is missing or resolves outside the repository: {name}") from exc
    if not path.is_file():
        raise PDSelectionBindingError(f"{label} must be a regular file: {name}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PDSelectionBindingError(f"cannot read {label}: {name}") from exc


def load_pd_binding(
    root: str | Path,
    *,
    expected_selection_path: str,
    tracked_paths: Iterable[str] | None = None,
    expected_selection_sha256: str | None = None,
    expected_protocol: dict | None = None,
    expected_manifest_path: str | None = None,
    expected_audit_path: str | None = None,
) -> PDSourceBinding:
    """Load an explicitly selected PD and bind its original source evidence.

    ``tracked_paths`` is mandatory caller-verified evidence for the independent
    selection file. No fallback candidate exists. Optional expected source paths
    and selection hash let a frozen collector enforce its additional bindings.
    The result has ``kp``, ``kd``, ``selected_id`` and ``source_records`` at top
    level and serializes with ``json.dumps``. Its ``archive_source_bytes()`` method
    supplies the exact byte strings already checked, for a source ZIP.
    ``expected_protocol`` must be the frozen original-PD protocol path/hash.
    The original audit schema remains unchanged. Only metadata and source ZIP
    bytes are read under raw/: trace/episodes are never opened. Their recorded
    hashes must exactly match the existing independent audit input hashes.
    """
    selection_name = _path_name(expected_selection_path, "expected_selection_path")
    if tracked_paths is None or isinstance(tracked_paths, (str, bytes)):
        raise PDSelectionBindingError("tracked_paths must be supplied from caller-verified clean source")
    tracked = {_path_name(path, "tracked_paths entry") for path in tracked_paths}
    if selection_name not in tracked:
        raise PDSelectionBindingError("independent PD selection is not in caller-verified tracked_paths")
    try:
        root_path = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PDSelectionBindingError("repository root is missing or cannot be resolved") from exc
    if not root_path.is_dir():
        raise PDSelectionBindingError("repository root must be a directory")

    raw_selection = _read_bytes(root_path, selection_name, "selection")
    selection_hash = hashlib.sha256(raw_selection).hexdigest()
    if expected_selection_sha256 is not None:
        expected_hash = _hash_name(expected_selection_sha256, "expected_selection_sha256")
        if selection_hash != expected_hash:
            raise PDSelectionBindingError("selection bytes do not match expected_selection_sha256")
    selection = _exact_keys(_json_record(raw_selection, "selection"),
                            {"schema", "status", "selected", "sources", "protocol"}, "selection")
    if selection["schema"] != "c4-pd-selection-v1" or selection["status"] != "selected":
        raise PDSelectionBindingError("selection requires schema c4-pd-selection-v1 and status selected")
    selected = _exact_keys(selection["selected"], {"candidate_id", "joint_indices", "kp", "kd"}, "selected")
    candidate_id = selected["candidate_id"]
    if type(candidate_id) is not int or not 0 <= candidate_id < len(PD_KD_CANDIDATES):
        raise PDSelectionBindingError("selected candidate_id must explicitly identify integer candidate 0..8")
    indices = selected["joint_indices"]
    if (not isinstance(indices, list) or len(indices) != 2
            or any(type(index) is not int for index in indices) or indices != [0, 1]):
        raise PDSelectionBindingError("selected joint_indices must be exactly [0, 1]")
    kp, kd = _gain_pair(selected["kp"], "selected.kp"), _gain_pair(selected["kd"], "selected.kd")
    if not _json_exact(selected["kp"], [64.0, 64.0]) or not _json_exact(selected["kd"], PD_KD_CANDIDATES[candidate_id]):
        raise PDSelectionBindingError("selected gains do not match the frozen candidate index")
    protocol = _exact_keys(selection["protocol"], {"path", "sha256"}, "selection.protocol")
    if _path_name(protocol["path"], "selection.protocol.path") != PD_PROTOCOL_PATH:
        raise PDSelectionBindingError("selection protocol must be the original frozen pair-PD protocol")
    _hash_name(protocol["sha256"], "selection.protocol.sha256")
    expected_protocol = _exact_keys(expected_protocol, {"path", "sha256"}, "expected_protocol")
    if not _json_exact(protocol, expected_protocol):
        raise PDSelectionBindingError("selection protocol does not match caller frozen expected_protocol")
    sources = _exact_keys(selection["sources"], {"manifest", "audit"}, "sources")
    source_bytes = {selection_name: raw_selection}
    source_records = {selection_name: selection_hash}
    bound_sources = {}
    for label, expected_path in (("manifest", expected_manifest_path), ("audit", expected_audit_path)):
        source = _exact_keys(sources[label], {"path", "sha256"}, f"sources.{label}")
        name = _path_name(source["path"], f"sources.{label}.path")
        expected_hash = _hash_name(source["sha256"], f"sources.{label}.sha256")
        if expected_path is not None and name != _path_name(expected_path, f"expected_{label}_path"):
            raise PDSelectionBindingError(f"sources.{label}.path does not match frozen expected path")
        if name in source_bytes:
            raise PDSelectionBindingError("selection, manifest, and audit must be three independent source files")
        raw = _read_bytes(root_path, name, label)
        actual_hash = hashlib.sha256(raw).hexdigest()
        if actual_hash != expected_hash:
            raise PDSelectionBindingError(f"{label} bytes do not match selection SHA-256")
        source_bytes[name], source_records[name] = raw, actual_hash
        bound_sources[label] = {"path": name, "sha256": actual_hash}
    archive_dir = PurePosixPath(selection_name).parent
    if any(PurePosixPath(record["path"]).parent != archive_dir for record in bound_sources.values()):
        raise PDSelectionBindingError("selection, archive manifest, and audit must be in the same frozen archive directory")
    manifest = _json_record(source_bytes[bound_sources["manifest"]["path"]], "manifest")
    audit = _json_record(source_bytes[bound_sources["audit"]["path"]], "audit")
    if not _json_exact(manifest.get("protocol"), protocol):
        raise PDSelectionBindingError("archive manifest protocol does not match selected original protocol")
    if (audit.get("validated_selection") is not True or audit.get("source_git_verification_enabled") is not True
            or type(audit.get("failed_checks")) is not int or audit["failed_checks"] != 0
            or not _json_exact(audit.get("immutable_scope"), PD_AUDIT_SCOPE)):
        raise PDSelectionBindingError("original audit is not a validated selection under the exact frozen PD scope")
    audit_selection = audit.get("selection")
    if not isinstance(audit_selection, dict) or audit_selection.get("status") != "selected":
        raise PDSelectionBindingError("original audit has no selected candidate")
    picked = _exact_keys(audit_selection.get("picked"),
        {"candidate", "kp", "kd", "eligible", "sort_key", "paid_control_steps", "paid_physics_steps"}, "audit.selection.picked")
    if (type(picked["candidate"]) is not int or picked["candidate"] != candidate_id
            or picked["eligible"] is not True or not _json_exact(picked["kp"], selected["kp"])
            or not _json_exact(picked["kd"], selected["kd"])):
        raise PDSelectionBindingError("original audit picked candidate/gains/eligibility does not exactly match selected")
    key = picked["sort_key"]
    if (not isinstance(key, list) or len(key) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in key[:3])
            or type(key[3]) is not int or key[3] != candidate_id):
        raise PDSelectionBindingError("original audit picked sort_key is invalid")
    if (type(picked["paid_control_steps"]) is not int or picked["paid_control_steps"] != 900
            or type(picked["paid_physics_steps"]) is not int or picked["paid_physics_steps"] != 9000):
        raise PDSelectionBindingError("eligible original PD candidate must contain its three full paid trial budgets")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise PDSelectionBindingError("archive manifest requires nonempty files mapping")
    raw_records = {}
    for relative, file_record in files.items():
        relative = _path_name(relative, "manifest.files path")
        file_record = _exact_keys(file_record, {"kind", "source", "bytes", "sha256"}, "manifest.files record")
        digest = _hash_name(file_record["sha256"], "manifest.files sha256")
        if (not isinstance(file_record["kind"], str) or not file_record["kind"]
                or not isinstance(file_record["source"], str) or not file_record["source"]
                or type(file_record["bytes"]) is not int or file_record["bytes"] < 0):
            raise PDSelectionBindingError("archive manifest file metadata is invalid")
        if relative.startswith("raw/"):
            local_name = relative.removeprefix("raw/")
            if "/" in local_name:
                raise PDSelectionBindingError("original PD raw sources must be direct local filenames")
            raw_records[local_name] = digest
    input_hashes = audit.get("input_hashes")
    if not isinstance(input_hashes, dict) or not _json_exact(input_hashes, raw_records):
        raise PDSelectionBindingError("archive raw file hashes do not exactly match original audit input_hashes")
    required_raw = {"metadata.json", "source_snapshot.zip", "manifest.json", "episodes.json", "selection.json", "trace.jsonl.gz"}
    if not required_raw.issubset(raw_records):
        raise PDSelectionBindingError("archive manifest lacks original PD core sources")
    loaded_raw = {}
    for local_name in ("metadata.json", "source_snapshot.zip"):
        relative = f"raw/{local_name}"
        name = _path_name((archive_dir / relative).as_posix(), "bound raw source path")
        raw = _read_bytes(root_path, name, f"original {local_name}")
        digest = hashlib.sha256(raw).hexdigest()
        if digest != raw_records[local_name] or len(raw) != files[relative]["bytes"]:
            raise PDSelectionBindingError(f"original {local_name} bytes/length do not match archived source record")
        loaded_raw[local_name] = raw
        source_bytes[name], source_records[name] = raw, digest
    metadata = _json_record(loaded_raw["metadata.json"], "original PD metadata")
    if any(not _json_exact(metadata.get(name), value) for name, value in PD_METADATA_FIELDS.items()):
        raise PDSelectionBindingError("original metadata 8D, target, seed, gain, or update scope does not match frozen PD conditions")
    if not _json_exact(metadata.get("environment_config"), PD_ENVIRONMENT_FIELDS):
        raise PDSelectionBindingError("original metadata dynamics timing and control permissions do not match frozen PD conditions")
    if not _json_exact(metadata.get("protocol"), protocol):
        raise PDSelectionBindingError("original metadata protocol does not match selected original protocol")
    if metadata.get("source_snapshot_sha256") != raw_records["source_snapshot.zip"]:
        raise PDSelectionBindingError("original metadata does not bind the source ZIP bytes")
    source_hashes = metadata.get("source_sha256")
    audit_hashes = _exact_keys(audit.get("audit_sources_sha256"), {"auditor", "common"}, "audit.audit_sources_sha256")
    if not isinstance(source_hashes, dict):
        raise PDSelectionBindingError("original metadata lacks source member hashes")
    member_records = {}
    try:
        with zipfile.ZipFile(io.BytesIO(loaded_raw["source_snapshot.zip"])) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(source_hashes):
                raise PDSelectionBindingError("original source ZIP does not have exact unique metadata coverage")
            for name in names:
                _path_name(name, "source ZIP member")
                _hash_name(source_hashes[name], "source ZIP metadata hash")
            for name in (PD_PROTOCOL_PATH, PD_AUDITOR_PATH, PD_COMMON_AUDITOR_PATH):
                digest = hashlib.sha256(archive.read(name)).hexdigest()
                if digest != source_hashes[name]:
                    raise PDSelectionBindingError("original required source ZIP member hash does not match metadata")
                member_records[name] = digest
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError) as exc:
        raise PDSelectionBindingError("original source ZIP lacks readable required source members") from exc
    if member_records[PD_PROTOCOL_PATH] != protocol["sha256"]:
        raise PDSelectionBindingError("original source ZIP protocol member does not match selected original protocol")
    if (audit_hashes["auditor"] != member_records[PD_AUDITOR_PATH]
            or audit_hashes["common"] != member_records[PD_COMMON_AUDITOR_PATH]):
        raise PDSelectionBindingError("original validated audit sources do not match original source ZIP members")
    return PDSourceBinding({
        "schema": "c4-pd-source-binding-v1", "status": "selected", "selected_id": candidate_id,
        "joint_indices": [0, 1], "kp": kp, "kd": kd,
        "selection_path": selection_name, "selection_sha256": selection_hash,
        "selection_tracking_evidence": "caller_verified_tracked_paths",
        "sources": bound_sources, "source_records": source_records,
        "protocol": protocol, "archive_member_records": member_records,
        "audit_selection_confirmed": True, "audit_reexecuted": False,
        "raw_trace_or_episodes_read": False,
        "remaining_original_bytes": "not reread; manifest hashes matched existing independent audit input_hashes",
    }, source_bytes)
