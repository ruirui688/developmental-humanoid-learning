"""Pure temporary-file fixtures: no Git, physics, or real experiment archives."""

import hashlib
import importlib.util
import copy
import io
import json
from pathlib import Path
import subprocess
import zipfile

import pytest


_spec = importlib.util.spec_from_file_location("pd_binding_under_test", next(p for p in Path(__file__).resolve().parents if (p/"pyproject.toml").is_file())/"src/developmental_physics/pd_selection_binding.py")
assert _spec and _spec.loader
helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helper)


@pytest.fixture(autouse=True)
def forbid_subprocess(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("PD binding must not use Git or any subprocess")
    for name in ("run", "Popen", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, name, forbidden)


@pytest.fixture
def fixture_repo(tmp_path):
    members = {helper.PD_PROTOCOL_PATH: b"fixture frozen protocol\n",
               helper.PD_AUDITOR_PATH: b"fixture independent auditor\n",
               helper.PD_COMMON_AUDITOR_PATH: b"fixture common audit\n"}
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    protocol = {"path": helper.PD_PROTOCOL_PATH, "sha256": hashlib.sha256(members[helper.PD_PROTOCOL_PATH]).hexdigest()}
    metadata = copy.deepcopy(helper.PD_METADATA_FIELDS)
    metadata.update(environment_config=copy.deepcopy(helper.PD_ENVIRONMENT_FIELDS), protocol=protocol,
                    source_snapshot_sha256=hashlib.sha256(zip_buffer.getvalue()).hexdigest(),
                    source_sha256={name: hashlib.sha256(value).hexdigest() for name, value in members.items()})
    raw_local = {"metadata.json": json.dumps(metadata).encode("utf-8") + b"\r\n",
                 "source_snapshot.zip": zip_buffer.getvalue(), "manifest.json": b'{"fixture":"original manifest"}\n',
                 "episodes.json": b"fixture forbidden episodes", "selection.json": b"fixture original selected record",
                 "trace.jsonl.gz": b"fixture forbidden trace"}
    selected = {"candidate_id": 4, "joint_indices": [0, 1], "kp": [64.0, 64.0], "kd": [1.0, 2.0]}
    audit = {"validated_selection": True, "failed_checks": 0, "source_git_verification_enabled": True,
             "immutable_scope": copy.deepcopy(helper.PD_AUDIT_SCOPE),
             "selection": {"status": "selected", "picked": {"candidate": 4, "kp": [64.0, 64.0], "kd": [1.0, 2.0],
                 "eligible": True, "sort_key": [0.02, 0.03, 0.01, 4], "paid_control_steps": 900, "paid_physics_steps": 9000}},
             "input_hashes": {name: hashlib.sha256(value).hexdigest() for name, value in raw_local.items()},
             "audit_sources_sha256": {"auditor": metadata["source_sha256"][helper.PD_AUDITOR_PATH],
                                      "common": metadata["source_sha256"][helper.PD_COMMON_AUDITOR_PATH]}}
    manifest = {"protocol": protocol, "files": {f"raw/{name}": {"kind": "raw", "source": f"fixture/{name}",
        "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()} for name, value in raw_local.items()}}
    raw = {"results/pd/manifest.json": json.dumps(manifest).encode("utf-8") + b"\r\n",
           "results/pd/audit.json": json.dumps(audit).encode("utf-8") + b"\n",
           **{f"results/pd/raw/{name}": raw_local[name] for name in ("metadata.json", "source_snapshot.zip")}}
    for name, content in raw.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    # No trace/episodes fixtures are created: opening them would fail this suite.
    selection = {
        "schema": "c4-pd-selection-v1", "status": "selected", "selected": selected,
        "protocol": protocol,
        "sources": {label: {"path": name, "sha256": hashlib.sha256(raw[name]).hexdigest()}
                    for label, name in (("manifest", "results/pd/manifest.json"),
                                        ("audit", "results/pd/audit.json"))},
    }
    path = "results/pd/selected.json"
    def write_selection():
        data = json.dumps(selection, ensure_ascii=False).encode("utf-8") + b"\n"
        (tmp_path / path).write_bytes(data)
        return data
    write_selection()
    return tmp_path, path, selection, raw, write_selection


def load_fixture(fixture_repo, **kwargs):
    root, path, selection, *_ = fixture_repo
    kwargs.setdefault("tracked_paths", [path])
    kwargs.setdefault("expected_protocol", selection["protocol"].copy())
    return helper.load_pd_binding(root, expected_selection_path=path, **kwargs)


def test_binding_is_json_compatible_and_retains_exact_original_bytes(fixture_repo):
    root, path, _, raw, _ = fixture_repo
    binding = load_fixture(fixture_repo)
    assert binding["kp"] == (64.0, 64.0)
    assert binding["kd"] == (1.0, 2.0)
    assert binding["selected_id"] == 4
    expected = {**raw, path: (root / path).read_bytes()}
    assert binding.archive_source_bytes() == expected
    assert binding["source_records"] == {name: hashlib.sha256(value).hexdigest() for name, value in expected.items()}
    assert json.loads(json.dumps(binding))["kd"] == [1.0, 2.0]
    assert binding["audit_selection_confirmed"] is True
    assert binding["raw_trace_or_episodes_read"] is False
    (root / "results/pd/audit.json").write_bytes(b"changed after binding")
    copy = binding.archive_source_bytes()
    assert copy["results/pd/audit.json"] == raw["results/pd/audit.json"]
    copy.clear()
    assert binding.archive_source_bytes() == expected


@pytest.mark.parametrize("tracked", [None, [], "results/pd/selected.json"])
def test_independent_selection_requires_caller_verified_tracked_evidence(fixture_repo, tracked):
    with pytest.raises(helper.PDSelectionBindingError, match="tracked"):
        load_fixture(fixture_repo, tracked_paths=tracked)


def test_optional_frozen_expected_hash_and_source_paths(fixture_repo):
    root, path, _, _, _ = fixture_repo
    digest = hashlib.sha256((root / path).read_bytes()).hexdigest()
    binding = load_fixture(fixture_repo, expected_selection_sha256=digest,
                           expected_manifest_path="results/pd/manifest.json",
                           expected_audit_path="results/pd/audit.json")
    assert binding["selection_sha256"] == digest
    for arguments in ({"expected_selection_sha256": "0" * 64},
                      {"expected_audit_path": "results/pd/different.json"},
                      {"expected_manifest_path": "results/pd/different.json"}):
        with pytest.raises(helper.PDSelectionBindingError, match="match"):
            load_fixture(fixture_repo, **arguments)


@pytest.mark.parametrize("candidate", [None, "unknown", "draft", "pending_1", "candidate_TBD", "", "contains space"])
def test_no_unknown_candidate_fallback(fixture_repo, candidate):
    _, _, selection, _, write_selection = fixture_repo
    selection["selected"]["candidate_id"] = candidate
    write_selection()
    with pytest.raises(helper.PDSelectionBindingError, match="candidate_id"):
        load_fixture(fixture_repo)


@pytest.mark.parametrize("gain", [True, "64", -1, float("inf"), float("nan"), 10 ** 1000])
def test_invalid_gains_rejected(fixture_repo, gain):
    _, _, selection, _, write_selection = fixture_repo
    selection["selected"]["kp"] = [gain, 64]
    write_selection()
    with pytest.raises(helper.PDSelectionBindingError):
        load_fixture(fixture_repo)


@pytest.mark.parametrize("bad_path", ["../outside.json", "/absolute.json", "C:/absolute.json", "a\\b.json",
                                     "./results/pd/audit.json", "results//pd/audit.json", "results/pd/../audit.json"])
def test_unsafe_declared_paths_rejected_before_source_access(fixture_repo, bad_path):
    _, _, selection, _, write_selection = fixture_repo
    selection["sources"]["audit"]["path"] = bad_path
    write_selection()
    with pytest.raises(helper.PDSelectionBindingError):
        load_fixture(fixture_repo)


@pytest.mark.parametrize("label", ["manifest", "audit"])
def test_changed_source_raw_bytes_do_not_bind(fixture_repo, label):
    root, _, selection, _, _ = fixture_repo
    (root / selection["sources"][label]["path"]).write_bytes(b"{}\n")
    with pytest.raises(helper.PDSelectionBindingError, match="bytes do not match"):
        load_fixture(fixture_repo)


def test_duplicate_selection_keys_rejected(fixture_repo):
    root, path, *_ = fixture_repo
    (root / path).write_bytes(b'{"schema":"c4-pd-selection-v1","schema":"other"}')
    with pytest.raises(helper.PDSelectionBindingError, match="duplicate key"):
        load_fixture(fixture_repo)


@pytest.mark.parametrize("mutation", ["missing_gains", "extra_top", "draft_status", "wrong_schema", "bool_indices",
                                      "reversed_indices", "uppercase_hash", "same_source", "missing_source"])
def test_strict_schema_and_independent_files(fixture_repo, mutation):
    root, _, selection, _, write_selection = fixture_repo
    if mutation == "missing_gains":
        del selection["selected"]["kd"]
    elif mutation == "extra_top":
        selection["default_pd"] = True
    elif mutation == "draft_status":
        selection["status"] = "draft"
    elif mutation == "wrong_schema":
        selection["schema"] = "other"
    elif mutation == "bool_indices":
        selection["selected"]["joint_indices"] = [False, True]
    elif mutation == "reversed_indices":
        selection["selected"]["joint_indices"] = [1, 0]
    elif mutation == "uppercase_hash":
        selection["sources"]["audit"]["sha256"] = "A" * 64
    elif mutation == "same_source":
        selection["sources"]["audit"] = selection["sources"]["manifest"].copy()
    elif mutation == "missing_source":
        (root / selection["sources"]["audit"]["path"]).unlink()
    write_selection()
    with pytest.raises(helper.PDSelectionBindingError):
        load_fixture(fixture_repo)


def test_source_symlink_escaping_root_rejected(fixture_repo, tmp_path):
    root, _, selection, _, write_selection = fixture_repo
    outside = root.parent / f"{root.name}_outside_audit.json"
    outside.write_bytes(b"outside fixture")
    link = root / "results/pd/audit_link.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("platform does not permit temporary test symlinks")
    selection["sources"]["audit"] = {"path": "results/pd/audit_link.json", "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()}
    write_selection()
    with pytest.raises(helper.PDSelectionBindingError, match="outside"):
        load_fixture(fixture_repo)


def rewrite_bound_document(fixture_repo, relative, document):
    root, _, selection, _, write_selection = fixture_repo
    target = root / "results/pd" / relative
    data = json.dumps(document).encode("utf-8") + b"\n"
    target.write_bytes(data)
    if relative in ("audit.json", "manifest.json"):
        source_key = relative.removesuffix(".json")
        selection["sources"][source_key]["sha256"] = hashlib.sha256(data).hexdigest()
        write_selection()
    else:
        audit_path = root / "results/pd/audit.json"
        audit = json.loads(audit_path.read_bytes())
        audit["input_hashes"][relative.removeprefix("raw/")] = hashlib.sha256(data).hexdigest()
        rewrite_bound_document(fixture_repo, "audit.json", audit)
        manifest_path = root / "results/pd/manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["files"][relative]["sha256"] = hashlib.sha256(data).hexdigest()
        manifest["files"][relative]["bytes"] = len(data)
        rewrite_bound_document(fixture_repo, "manifest.json", manifest)


@pytest.mark.parametrize("mutation", ["not_validated", "failed_checks", "no_git", "ineligible", "different_candidate",
                                      "different_gain_type", "different_seeds", "wrong_input_hash", "different_auditor_source"])
def test_existing_independent_audit_conditions_are_required(fixture_repo, mutation):
    root, *_ = fixture_repo
    audit = json.loads((root / "results/pd/audit.json").read_bytes())
    if mutation == "not_validated":
        audit["validated_selection"] = False
    elif mutation == "failed_checks":
        audit["failed_checks"] = 1
    elif mutation == "no_git":
        audit["source_git_verification_enabled"] = False
    elif mutation == "ineligible":
        audit["selection"]["picked"]["eligible"] = False
    elif mutation == "different_candidate":
        audit["selection"]["picked"]["candidate"] = 2
    elif mutation == "different_gain_type":
        audit["selection"]["picked"]["kp"] = [64, 64]
    elif mutation == "different_seeds":
        audit["immutable_scope"]["seeds"] = [20, 21, 22]
    elif mutation == "wrong_input_hash":
        audit["input_hashes"]["trace.jsonl.gz"] = "0" * 64
    elif mutation == "different_auditor_source":
        audit["audit_sources_sha256"]["auditor"] = "0" * 64
    rewrite_bound_document(fixture_repo, "audit.json", audit)
    with pytest.raises(helper.PDSelectionBindingError):
        load_fixture(fixture_repo)


@pytest.mark.parametrize("field,value", [("native_joint_count", 2), ("target_offsets_rad", [0.1, 0.2]),
                                        ("seeds", [20, 21, 22]), ("model_updates", 1)])
def test_native_dimension_targets_seeds_and_learning_conditions_are_bound(fixture_repo, field, value):
    root, *_ = fixture_repo
    metadata = json.loads((root / "results/pd/raw/metadata.json").read_bytes())
    metadata[field] = value
    rewrite_bound_document(fixture_repo, "raw/metadata.json", metadata)
    with pytest.raises(helper.PDSelectionBindingError, match="scope"):
        load_fixture(fixture_repo)


def test_control_permissions_are_bound(fixture_repo):
    root, *_ = fixture_repo
    metadata = json.loads((root / "results/pd/raw/metadata.json").read_bytes())
    metadata["environment_config"]["torque_limit"] = 1.0
    rewrite_bound_document(fixture_repo, "raw/metadata.json", metadata)
    with pytest.raises(helper.PDSelectionBindingError, match="permissions"):
        load_fixture(fixture_repo)


def test_original_protocol_member_hash_is_required(fixture_repo):
    root, _, selection, _, write_selection = fixture_repo
    selection["protocol"]["sha256"] = "0" * 64
    manifest = json.loads((root / "results/pd/manifest.json").read_bytes())
    manifest["protocol"] = selection["protocol"]
    rewrite_bound_document(fixture_repo, "manifest.json", manifest)
    metadata = json.loads((root / "results/pd/raw/metadata.json").read_bytes())
    metadata["protocol"] = selection["protocol"]
    rewrite_bound_document(fixture_repo, "raw/metadata.json", metadata)
    write_selection()
    with pytest.raises(helper.PDSelectionBindingError, match="protocol member"):
        load_fixture(fixture_repo)


def test_no_extra_source_reads_for_archive_or_reporting(fixture_repo, monkeypatch):
    original = Path.read_bytes
    reads = []
    def counted(path):
        reads.append(path)
        if path.name in ("trace.jsonl.gz", "episodes.json"):
            pytest.fail("source binding must not reread/re-audit traces or episodes")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", counted)
    binding = load_fixture(fixture_repo)
    assert len(reads) == 5 and len(set(reads)) == 5
    assert binding["status"] == "selected"
    binding.archive_source_bytes()
    json.dumps(binding)
    assert len(reads) == 5
