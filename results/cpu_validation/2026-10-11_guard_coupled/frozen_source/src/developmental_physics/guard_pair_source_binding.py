"""DRAFT C4 B binding to one already audited A archive (stdlib only).

No model, collector, simulator, subprocess or Git is imported. Production
tracked_paths is caller-verified evidence; this module cannot establish Git
cleanliness itself. Every returned JSON record is a defensive deep copy.
Missing/incomplete calibration blocks only its seed, without supplying a prior.
The A scientific contribution gate is deliberately not a prerequisite.
"""
from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from types import MappingProxyType
import xml.etree.ElementTree as ET
import zipfile

A_ROOT = "results/cpu_validation/2026-10-11_guard_pair/"
A_MANIFEST_PATH = A_ROOT + "manifest.json"
A_AUDIT_PATH = A_ROOT + "first_audit.json"
A_RAW_NAMES = ("metadata.json", "episodes.json", "seed_results.json", "trace.jsonl.gz", "source_snapshot.zip", "manifest.json")
A_COLLECTOR_PATH = "src/developmental_physics/guard_pair_development.py"
A_PROTOCOL_PATH = "docs/GUARD_PAIR_DEVELOPMENT_PROTOCOL.md"
A_AUDITOR_PATH = "scripts/audit_guard_pair_development.py"
A_AUDITOR_SUPPORT_PATHS = ("scripts/audit_local_frozen.py", "scripts/audit_pair_frozen.py")
ASSET_PATH = "src/developmental_physics/assets/ground_body.xml"
PUBLIC_SOURCE_PATHS = frozenset({ASSET_PATH, "pyproject.toml"} | {
    "src/developmental_physics/" + n for n in (
        "environment.py", "collect.py", "probes.py", "local_model.py", "local_pair_model.py", "guard_pair_model.py")})
CURRENT_SOURCE_PATHS = PUBLIC_SOURCE_PATHS | {A_COLLECTOR_PATH, A_PROTOCOL_PATH, A_AUDITOR_PATH, *A_AUDITOR_SUPPORT_PATHS}
SHARED_SOURCE_PATHS = CURRENT_SOURCE_PATHS
BASE_REQUIRED_SOURCES = PUBLIC_SOURCE_PATHS | {"src/developmental_physics/" + n for n in (
    "__init__.py", "local_integration.py", "local_frozen_validation.py", "feedback_validate.py", "pd_selection_binding.py")}
PD_ROOT = "results/cpu_validation/2026-10-11_pair_pd/"
PD_SOURCE_PATHS = frozenset(PD_ROOT + n for n in ("selection.json", "manifest.json", "first_audit.json", "raw/metadata.json", "raw/source_snapshot.zip"))
REQUIRED_SOURCE_PATHS = BASE_REQUIRED_SOURCES | CURRENT_SOURCE_PATHS | {"docs/PAIR_PD_DEVELOPMENT_PROTOCOL.md"}
RESET_SEEDS = {0: 3757552657, 1: 1641411168, 2: 2001025171}
BASELINE_KINDS = ("nominal_guard", "learned_guard", "PDselected", "zero")
KINDS = ("calibration", "prediction", "nominal_raw", "learned_raw", *BASELINE_KINDS)


class ASourceBindingError(ValueError):
    """A original bytes, source identities or transition semantics disagree."""


def audit_scope(synthetic=False):
    return {"suite": "guard_pair_development", "pose": "supine", "seeds": [0, 1, 2],
        "joint_indices": [0, 1], "split": "development", "protocol": A_PROTOCOL_PATH,
        "collector": A_COLLECTOR_PATH, "auditor": A_AUDITOR_PATH,
        "synthetic_fixture": synthetic, "scientific_gates_frozen": not synthetic,
        "prefix_steps": 100, "calibration_steps": 400, "prediction_steps": 100, "control_steps": 200,
        "input_bases": {"nominal_raw": "raw_request", "nominal_guard": "known_angle_guard",
            "learned_raw": "raw_request", "learned_guard": "known_angle_guard"},
        "pd_selection": PD_ROOT + "selection.json", "calibration_pulse_zero": [1, 9],
        "prediction_velocity_ratio_max": .8, "contribution_tracking_mean_improvement_min": .20,
        "pd_tracking_mean_improvement_min": .05, "pd_actual_effort_ratio_max": 1.05}


def _fail(message):
    raise ASourceBindingError(message)


def _path(value):
    if (type(value) is not str or not value or value != value.strip() or "\\" in value
        or ":" in value or "\0" in value or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).drive or any(x in ("", ".", "..") for x in value.split("/"))):
        _fail("canonical relative POSIX path required")
    return value


def _hash(value):
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        _fail("lowercase SHA-256 required")
    return value


def _digest(blob):
    return hashlib.sha256(blob).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            _fail("duplicate JSON key")
        result[key] = value
    return result


def _json(blob):
    try:
        return json.loads(blob.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _: _fail("nonstandard JSON constant"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ASourceBindingError("strict UTF-8 JSON required") from exc


def _equal(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return set(a) == set(b) and all(_equal(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    return a == b and not (type(a) is float and not math.isfinite(a))


def _exact(obj, keys, label):
    if type(obj) is not dict or set(obj) != set(keys):
        _fail(label + " requires exact keys")
    return obj


def _vector(value, size, label):
    if type(value) is not list or len(value) != size:
        _fail(label + " requires finite native array")
    for x in value:
        if type(x) not in (int, float):
            _fail(label + " requires finite numbers, excluding bool")
        try:
            if not math.isfinite(x):
                _fail(label + " requires finite numbers")
        except OverflowError as exc:
            raise ASourceBindingError(label + " numeric overflow") from exc
    return value


def _read(root, name):
    try:
        path = (root / _path(name)).resolve(strict=True)
        path.relative_to(root)
        if not path.is_file():
            _fail("bound source must be a regular file: " + name)
        return path.read_bytes()
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, ASourceBindingError):
            raise
        raise ASourceBindingError("bound source missing or outside root: " + name) from exc


def _request(active, directions, kind):
    block, slot = divmod(active, 20)
    sign = 1 if slot == 0 else (-1 if slot == 10 else 0)
    if kind == "calibration":
        shape = ((1, 0), (0, 1), (1, 1), (1, -1))[block // 5]
        amplitude = (.125, .25, .375, .5, .25)[block % 5]
    else:
        shape = ((1, 0), (0, 1), (1, 1), (1, -1), (1, 1))[block]
        amplitude = (.125, .25, .375, .5, .375)[block]
    return [directions[i] * shape[i] * sign * amplitude for i in range(2)] + [0.] * 6


def _public_ranges(blob):
    try:
        xml = ET.fromstring(blob)
        compiler = xml.find("compiler")
        factor = math.pi / 180. if compiler is None or compiler.get("angle", "degree") == "degree" else 1.
        entries = {}
        for joint in xml.findall(".//joint"):
            if joint.get("name") in ("left_shoulder", "left_elbow"):
                name = joint.get("name")
                if name in entries:
                    _fail("duplicate public asset joint")
                entries[name] = [float(x) * factor for x in joint.get("range", "").split()]
        result = [entries[name] for name in ("left_shoulder", "left_elbow")]
        for item in result:
            _vector(item, 2, "asset public range")
            if item[0] >= item[1]:
                _fail("ordered public asset range required")
        return result
    except (ET.ParseError, KeyError, ValueError) as exc:
        if isinstance(exc, ASourceBindingError):
            raise
        raise ASourceBindingError("public joint ranges missing from archived asset") from exc


class ASourceBinding:
    """Read-only cache; no dict subclass or public mutable internal container."""
    __slots__ = ("_seeds", "_record", "_sources")

    def __init__(self, seeds, record, sources):
        self._seeds = MappingProxyType(deepcopy(seeds))
        self._record = deepcopy(record)
        self._sources = MappingProxyType(dict(sources))

    def seed(self, seed):
        if type(seed) is not int or seed not in RESET_SEEDS:
            _fail("known integer development seed required")
        return deepcopy(self._seeds[seed])

    def record(self):
        return deepcopy(self._record)

    def source_bytes(self):
        """Original archive and archived member bytes, never reread from disk."""
        return dict(self._sources)


def _seed_record(seed, sr, episodes, rows, audit_seed, ranges):
    tid = f"seed{seed}_calibration"
    cal_ep = episodes.get(tid)
    cal = rows.get(tid, [])
    qref = sr.get("reference_q")
    directions = sr.get("direction")
    if qref is not None:
        _vector(qref, 2, "original reference_q")
        if (type(directions) is not list or len(directions) != 2
            or any(type(x) is not int or x not in (-1, 1) for x in directions)):
            _fail("original signed directions required")
        expected = [1 if ranges[i][1] - qref[i] >= qref[i] - ranges[i][0] else -1 for i in range(2)]
        if directions != expected:
            _fail("original direction differs from public range rule")
    elif directions is not None:
        _fail("direction without native qref")
    snapshots = [models[n] for key in ("initial_models", "nominal_models", "calibration_models", "learned_models")
        for models in [sr.get(key, {})] for n in ("nominal_guard", "learned_guard") if n in models]
    for snapshot in snapshots:
        if not _equal(snapshot.get("qref_rad"), qref):
            _fail("guard snapshot qref identity mismatch")
        mapping = snapshot.get("input_mapping", {})
        guard = mapping.get("public_guard", {})
        if (mapping.get("basis") != "known_angle_guard" or mapping.get("guard_used_by_model") is not True
            or not _equal(guard.get("public_joint_ranges_rad"), ranges)
            or guard.get("angle_margin_rad") != .03 or guard.get("request_clip_per_axis_nm") != .5
            or guard.get("q_clipped") is not False or guard.get("future_actual_input") is not False):
            _fail("guard public basis identity mismatch")
    prefix_observation = None
    active = []
    for kind in ("calibration", "prediction"):
        regular = rows.get(f"seed{seed}_{kind}", [])
        stopped = False
        for i, row in enumerate(regular):
            index = row.get("step_index")
            if type(index) is not int or index != i:
                _fail("returned transition order has a gap or duplicate")
            if stopped:
                _fail("returned transition after terminal interval")
            if index >= (500 if kind == "calibration" else 200):
                _fail("transition exceeds frozen interval count")
            for label in ("observation_before", "observation_after"):
                obs = row.get(label)
                if type(obs) is not dict:
                    _fail("returned interval requires original native observation")
                for key in ("joint_position", "joint_velocity"):
                    _vector(obs.get(key), 8, "native " + key)
            if i and not _equal(row["observation_before"], regular[i - 1]["observation_after"]):
                _fail("original native transition chain mismatch")
            diagnostic = row["diagnostics"]
            n = diagnostic.get("executed_substeps")
            if (type(n) is not int or not 0 <= n <= 10 or type(diagnostic.get("terminated")) is not bool
                or (n != 10 and not diagnostic["terminated"])):
                _fail("invalid returned interval substep/terminal identity")
            command = _vector(row.get("requested_torque"), 8, "requested_torque")
            if index < 100:
                if row.get("phase") != "prefix" or any(x != 0 for x in command) or row.get("model_update") is not None:
                    _fail("prefix must be zero request without learning")
            else:
                if qref is None or row.get("phase") != kind:
                    _fail("active transition without original reference or phase")
                if index == 100:
                    if row["observation_before"]["joint_position"][:2] != qref:
                        _fail("active native prefix endpoint differs from original reference")
                    if kind == "calibration":
                        prefix_observation = row["observation_before"]
                if command != _request(index - 100, directions, kind):
                    _fail("known fixed 1/9 schedule mismatch")
                if kind == "prediction" and row.get("model_update") is not None:
                    _fail("evaluation prediction may not fit any model")
                if kind == "calibration":
                    active.append(row)
            stopped = diagnostic["terminated"] or row.get("study_abort") is not None
    complete_rows = (len(cal) == 500 and all(r["diagnostics"]["executed_substeps"] == 10
        and not r["diagnostics"]["terminated"] and r.get("study_abort") is None for r in cal))
    declared = sr.get("calibration_completed")
    if type(declared) is not bool:
        _fail("calibration completion must be explicit boolean")
    ready = declared and complete_rows and cal_ep is not None and cal_ep.get("status") == "completed" and cal_ep.get("completed") is True
    if declared and not ready:
        _fail("declared complete calibration has missing/terminal original transitions")
    if ready and (not snapshots or "learned_guard" not in sr.get("learned_models", {})
        or sr.get("calibration_vector_updates") != 800 or sr.get("calibration_scalar_updates") != 1600):
        _fail("completed calibration must bind both original model update counts and guard snapshot")
    plant = None if cal_ep is None else cal_ep.get("environment_fingerprint_before")
    if plant is not None:
        _hash(plant)
    for episode in episodes.values():
        if episode["seed"] == seed and episode.get("environment_fingerprint_before") is not None:
            p = _hash(episode["environment_fingerprint_before"])
            if plant is not None and p != plant:
                _fail("A trial plant differs from calibration plant")
            if episode.get("environment_fingerprint_after") != p:
                _fail("A physical parameters changed within a trial")
    return {"seed": seed, "reset_seed": RESET_SEEDS[seed], "reference_q": deepcopy(qref), "direction": deepcopy(directions),
        "public_joint_ranges": deepcopy(ranges), "environment_fingerprint_before": plant,
        "native_prefix_observation": deepcopy(prefix_observation), "calibration_ready": bool(ready),
        "calibration_block_reason": None if ready else {"type": "ACalibrationBlocked", "message": "missing or incomplete original A calibration", "original_episode": deepcopy(cal_ep)},
        "calibration_transitions": deepcopy(active),
        "prediction_transitions": deepcopy([r for r in rows.get(f"seed{seed}_prediction", []) if r["step_index"] >= 100]),
        "prediction_episode": deepcopy(episodes.get(f"seed{seed}_prediction")),
        "reused_baselines": {k: deepcopy(sr.get("evaluations", {}).get(k)) for k in BASELINE_KINDS},
        "reused_audit_metrics": {k: deepcopy(audit_seed.get("evaluations", {}).get(k)) for k in ("prediction", *BASELINE_KINDS)},
        "A_original_seed_result": deepcopy(sr)}


def _load_a_source_binding(root, *, synthetic=False, tracked_paths=None, current_source_bytes, expected_runtime):
    """Strictly bind literal A paths; source bytes and runtime come from caller.

    expected_runtime has exactly environment_config/dependencies/mujoco_version.
    current_source_bytes includes SHARED_SOURCE_PATHS; additional B sources
    are ignored because they did not exist in A. Production requires caller-verified tracked paths
    for all archived source members and all read archive files. No path guessing,
    input clipping, parameter fitting or scientific gate recomputation occurs.
    """
    if type(synthetic) is not bool:
        _fail("explicit boolean synthetic flag required")
    if type(current_source_bytes) is not dict or not CURRENT_SOURCE_PATHS.issubset(current_source_bytes):
        _fail("explicit complete current public and audit source bytes required")
    for name, blob in current_source_bytes.items():
        _path(name)
        if type(blob) is not bytes:
            _fail("current source content must be original bytes")
    _exact(expected_runtime, {"environment_config", "dependencies", "mujoco_version"}, "expected_runtime")
    if not synthetic and (tracked_paths is None or isinstance(tracked_paths, (str, bytes))):
        _fail("production requires caller-verified tracked_paths before archive read")
    tracked = set() if tracked_paths is None else {_path(p) for p in tracked_paths}
    required_archive = {A_MANIFEST_PATH, A_AUDIT_PATH} | {A_ROOT + "raw/" + n for n in A_RAW_NAMES}
    if not synthetic and not (required_archive | SHARED_SOURCE_PATHS).issubset(tracked):
        _fail("production archive or source identity is untracked")
    try:
        root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ASourceBindingError("existing repository root required") from exc
    sources = {n: _read(root, n) for n in (A_MANIFEST_PATH, A_AUDIT_PATH)}
    manifest, audit = _json(sources[A_MANIFEST_PATH]), _json(sources[A_AUDIT_PATH])
    if type(manifest) is not dict or type(audit) is not dict:
        _fail("outer manifest and first audit must be objects")
    files = manifest.get("files")
    if type(files) is not dict or not files:
        _fail("outer manifest.files required")
    raw_records = {}
    for relative, record in files.items():
        _path(relative)
        _exact(record, {"kind", "source", "bytes", "sha256"}, "outer manifest record")
        _hash(record["sha256"])
        if (type(record["bytes"]) is not int or record["bytes"] < 0
            or any(type(record[k]) is not str or not record[k] for k in ("kind", "source"))):
            _fail("invalid outer manifest record")
        if relative.startswith("raw/"):
            local = relative[4:]
            if "/" in local:
                _fail("A original raw requires direct filenames")
            raw_records[local] = record["sha256"]
    if set(raw_records) != set(A_RAW_NAMES) or "first_audit.json" not in files:
        _fail("outer manifest must bind exact A six raw files and literal first_audit.json")
    for relative in ("first_audit.json", *("raw/" + n for n in A_RAW_NAMES)):
        name = A_ROOT + relative
        blob = sources[name] if name in sources else _read(root, name)
        record = files[relative]
        if len(blob) != record["bytes"] or _digest(blob) != record["sha256"]:
            _fail("outer manifest byte length/hash mismatch: " + relative)
        sources[name] = blob
    if (type(audit.get("failed")) is not int or audit["failed"] != 0
        or audit.get("violations") != [] or not _equal(audit.get("immutable_scope"), audit_scope(synthetic))
        or audit.get("final_gates", {}).get("data_consistency_verified") is not True
        or audit.get("execution", {}).get("source_git_verification_enabled") is not (not synthetic)):
        _fail("A zero-failure independent data audit identity required")
    archive = audit.get("archive")
    if type(archive) is not dict or not _equal(archive.get("input_hashes"), raw_records):
        _fail("A audit input_hashes differs from exact archived raw bytes")
    raw = {n: sources[A_ROOT + "raw/" + n] for n in A_RAW_NAMES}
    local_manifest = _json(raw["manifest.json"])
    if not _equal(local_manifest, {n: raw_records[n] for n in A_RAW_NAMES if n != "manifest.json"}):
        _fail("A original raw manifest identity mismatch")
    metadata = _json(raw["metadata.json"])
    required_meta = {"suite": "guard_pair_development", "synthetic": synthetic, "seeds": [0, 1, 2],
        "split": "development", "pose": "supine", "joint_indices": [0, 1], "native_joint_count": 8,
        "prefix_steps": 100, "calibration_steps": 400, "prediction_steps": 100, "control_steps_per_trial": 200,
        "source_status": "", "source_dirty": False, "gpu": None}
    if type(metadata) is not dict or any(not _equal(metadata.get(k), v) for k, v in required_meta.items()):
        _fail("A metadata frozen scope/source cleanliness mismatch")
    if not synthetic and (type(metadata.get("source_commit")) is not str or re.fullmatch("[0-9a-f]{40}", metadata["source_commit"]) is None or metadata.get("backend") != "MuJoCo CPU"):
        _fail("formal A clean source commit/backend required")
    if any(not _equal(metadata.get(k), v) for k, v in expected_runtime.items()):
        _fail("A config/dependencies/MuJoCo version differs from current explicit runtime")
    hashes = metadata.get("source_sha256")
    required = REQUIRED_SOURCE_PATHS | (set() if synthetic else PD_SOURCE_PATHS)
    if type(hashes) is not dict or not required.issubset(hashes):
        _fail("A required archived source coverage missing")
    if metadata.get("source_snapshot_sha256") != _digest(raw["source_snapshot.zip"]):
        _fail("A metadata source ZIP hash mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(raw["source_snapshot.zip"])) as z:
            names = z.namelist()
            if len(names) != len(set(names)) or set(names) != set(hashes):
                _fail("A source ZIP requires exact unique metadata members")
            members = {}
            for name in names:
                _path(name)
                blob = z.read(name)
                if _digest(blob) != _hash(hashes[name]):
                    _fail("A source member hash mismatch")
                if not synthetic and name not in tracked:
                    _fail("A archived source member not caller-verified tracked")
                members[name] = blob
    except (zipfile.BadZipFile, KeyError, OSError, RuntimeError) as exc:
        raise ASourceBindingError("A unreadable source ZIP") from exc
    for name in SHARED_SOURCE_PATHS:
        blob = current_source_bytes[name]
        if members.get(name) != blob:
            _fail("A/current public source identity mismatch: " + name)
    if (metadata.get("protocol") != {"path": A_PROTOCOL_PATH, "sha256": hashes[A_PROTOCOL_PATH]}
        or metadata.get("independent_auditor") != {"path": A_AUDITOR_PATH, "sha256": hashes[A_AUDITOR_PATH], "pending": synthetic, "required_for_formal": True}
        or audit.get("audit_script_sha256") != hashes[A_AUDITOR_PATH]
        or not _equal(audit.get("audit_dependency_sha256"), {n: hashes[n] for n in A_AUDITOR_SUPPORT_PATHS})):
        _fail("A protocol or independent executing auditor source identity mismatch")
    ranges = _public_ranges(members[ASSET_PATH])
    seed_results, ep_list = _json(raw["seed_results.json"]), _json(raw["episodes.json"])
    if type(seed_results) is not list or type(ep_list) is not list or type(archive.get("seeds")) is not list:
        _fail("A seed/episode/audit records must be arrays")
    def seed_map(items, label):
        result = {}
        for item in items:
            seed = item.get("seed") if type(item) is dict else None
            if type(seed) is not int or seed not in RESET_SEEDS or seed in result:
                _fail(label + " duplicate/unknown seed")
            result[seed] = item
        if set(result) != set(RESET_SEEDS):
            _fail(label + " must retain all three planned seeds")
        return result
    saved, derived = seed_map(seed_results, "A seed_results"), seed_map(archive["seeds"], "A audit")
    episodes = {}
    for ep in ep_list:
        seed, kind = ep.get("seed"), ep.get("kind")
        tid = ep.get("trial_id")
        if type(seed) is not int or seed not in RESET_SEEDS or kind not in KINDS or tid != f"seed{seed}_{kind}" or tid in episodes:
            _fail("A episode duplicate or unknown identity")
        episodes[tid] = ep
    rows, ids = {}, set()
    try:
        text = gzip.decompress(raw["trace.jsonl.gz"]).decode("utf-8")
    except (OSError, EOFError, UnicodeDecodeError) as exc:
        raise ASourceBindingError("A native trace unreadable") from exc
    for line in text.splitlines():
        row = _json(line.encode("utf-8"))
        if type(row) is not dict:
            _fail("A trace row must be object")
        seed, kind, index = row.get("seed"), row.get("kind"), row.get("step_index")
        if type(seed) is not int or seed not in RESET_SEEDS or kind not in KINDS or row.get("trial_id") != f"seed{seed}_{kind}":
            _fail("A transition trial identity mismatch")
        if "collector_exception" in row:
            continue  # preserved in original bytes and seed/episode failure records; never a new returned sample
        if "diagnostics" not in row or type(index) is not int or index < 0:
            _fail("returned transition must retain interval identity")
        transition = row.get("shared_transition_id")
        if transition != f"seed{seed}_{kind}:{index}" or transition in ids:
            _fail("duplicate or incorrect shared transition ID")
        ids.add(transition)
        rows.setdefault(row["trial_id"], []).append(row)
    seeds = {}
    for seed in RESET_SEEDS:
        if saved[seed].get("reset_seed") != RESET_SEEDS[seed]:
            _fail("A reset seed identity mismatch")
        seeds[seed] = _seed_record(seed, saved[seed], episodes, rows, derived[seed], ranges)
    # Namespace archive files and original source members differ; collision is forbidden.
    if set(sources) & set(members):
        _fail("A archive/source namespace collision")
    sources.update(members)
    record = {"schema": "c4-a-source-binding-v1", "synthetic": synthetic, "synthetic_fixture": synthetic,
        "archive_root": A_ROOT, "manifest": {"path": A_MANIFEST_PATH, "sha256": _digest(sources[A_MANIFEST_PATH])},
        "audit": {"path": A_AUDIT_PATH, "sha256": _digest(sources[A_AUDIT_PATH])},
        "raw_hashes": raw_records, "source_commit": metadata["source_commit"],
        "source_sha256": deepcopy(hashes), "runtime": deepcopy(expected_runtime),
        "A_paid_budget": deepcopy(archive.get("budget")),
        "calibration_ready": {str(s): seeds[s]["calibration_ready"] for s in RESET_SEEDS},
        "new_physical_calls": 0, "new_model_updates": 0,
        "scientific_A_contribution_required": False, "source_git_verified_by_binding": False}
    return ASourceBinding(seeds, record, sources)


def load_a_source_binding(root, *, synthetic=False, tracked_paths=None, current_source_bytes, expected_runtime):
    """See the strict internal loader; malformed schemas share one error type."""
    try:
        return _load_a_source_binding(root, synthetic=synthetic, tracked_paths=tracked_paths,
            current_source_bytes=current_source_bytes, expected_runtime=expected_runtime)
    except ASourceBindingError:
        raise
    except (OSError, TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError) as exc:
        raise ASourceBindingError("A malformed source schema: " + type(exc).__name__) from exc
