"""Synthetic binding tests: no actual A archive, model fit, physics or Git."""
from copy import deepcopy
import builtins
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

try:
    from developmental_physics import guard_pair_source_binding as binding
except ImportError:
    import guard_pair_source_binding as binding
from synthetic_a_source_fixture import ArtificialAArchive, encode, sha


@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("synthetic binding tests must not invoke external commands")
    for name in ("Popen", "run", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, name, forbidden)


@pytest.fixture
def fixture(tmp_path):
    return ArtificialAArchive(tmp_path / "artificial_repository").write()


def load(fixture):
    return binding.load_a_source_binding(fixture.root, **fixture.kwargs())


def rewrite_outer_record(fixture, relative, blob):
    root = fixture.root / binding.A_ROOT
    (root / relative).write_bytes(blob)
    manifest = json.loads((root / "manifest.json").read_bytes())
    manifest["files"][relative].update(bytes=len(blob), sha256=sha(blob))
    (root / "manifest.json").write_bytes(encode(manifest))


def test_three_complete_calibrations_and_failed_A_control_remain_usable(fixture):
    result = load(fixture)
    assert not isinstance(result, dict)
    assert result.record()["synthetic"] is True
    assert result.record()["scientific_A_contribution_required"] is False
    for seed in (0, 1, 2):
        record = result.seed(seed)
        assert record["calibration_ready"] is True
        assert len(record["calibration_transitions"]) == 400
        assert len(record["prediction_transitions"]) == 100
        assert record["calibration_transitions"][0]["shared_transition_id"] == f"seed{seed}_calibration:100"
        assert record["calibration_transitions"][-1]["shared_transition_id"] == f"seed{seed}_calibration:499"
        assert record["reused_baselines"]["learned_guard"]["status"] == "terminated"
        assert record["reused_audit_metrics"]["learned_guard"]["status"] == "terminated"
    assert result.record()["new_physical_calls"] == result.record()["new_model_updates"] == 0


def test_getters_are_deep_copies_and_cache_no_reread(fixture, monkeypatch):
    result = load(fixture)
    expected = result.seed(0)
    got = result.seed(0)
    got["calibration_transitions"][0]["observation_before"]["joint_position"][0] = 123
    got["reused_baselines"]["zero"]["status"] = "invented"
    record = result.record()
    record["source_sha256"].clear()
    sources = result.source_bytes()
    sources.clear()
    monkeypatch.setattr(Path, "read_bytes", lambda _: (_ for _ in ()).throw(AssertionError("getters must not read")))
    assert result.seed(0) == expected
    assert result.record()["source_sha256"]
    assert result.source_bytes()


@pytest.mark.parametrize("seed", [True, -1, 3, "0"])
def test_unknown_seed_rejected(fixture, seed):
    with pytest.raises(binding.ASourceBindingError):
        load(fixture).seed(seed)


def test_incomplete_calibration_only_blocks_that_seed(fixture):
    fixture.rows = [r for r in fixture.rows if not (r["seed"] == 1 and r["kind"] == "calibration" and r["step_index"] > 260)]
    fixture.seeds[1].update(calibration_completed=False, learned_models={}, calibration_vector_updates=322, calibration_scalar_updates=644)
    next(e for e in fixture.episodes if e["trial_id"] == "seed1_calibration").update(status="terminated", completed=False)
    last = next(r for r in fixture.rows if r["shared_transition_id"] == "seed1_calibration:260")
    last["study_abort"] = "complete terminal must be retained"
    fixture.write()
    result = load(fixture)
    assert result.seed(0)["calibration_ready"] and result.seed(2)["calibration_ready"]
    assert not result.seed(1)["calibration_ready"]
    assert result.seed(1)["calibration_block_reason"]["type"] == "ACalibrationBlocked"
    assert result.seed(1)["calibration_transitions"][-1]["study_abort"]


def test_missing_calibration_only_blocks_seed(fixture):
    fixture.rows = [r for r in fixture.rows if r["trial_id"] != "seed2_calibration"]
    fixture.episodes = [e for e in fixture.episodes if e["trial_id"] != "seed2_calibration"]
    fixture.seeds[2].update(calibration_completed=False, learned_models={})
    fixture.write()
    result = load(fixture)
    assert not result.seed(2)["calibration_ready"]
    assert result.seed(2)["calibration_transitions"] == []


def test_last_complete_terminal_not_ready_even_400_transitions(fixture):
    next(r for r in fixture.rows if r["shared_transition_id"] == "seed0_calibration:499")["study_abort"] = "velocity"
    fixture.seeds[0].update(calibration_completed=False, learned_models={})
    next(e for e in fixture.episodes if e["trial_id"] == "seed0_calibration").update(status="terminated", completed=False)
    fixture.write()
    record = load(fixture).seed(0)
    assert len(record["calibration_transitions"]) == 400
    assert not record["calibration_ready"]


def test_prediction_partial_is_preserved_without_learning(fixture):
    fixture.rows = [r for r in fixture.rows if not (r["trial_id"] == "seed0_prediction" and r["step_index"] > 119)]
    row = next(r for r in fixture.rows if r["shared_transition_id"] == "seed0_prediction:119")
    row["diagnostics"].update(executed_substeps=4, terminated=True)
    next(e for e in fixture.episodes if e["trial_id"] == "seed0_prediction").update(status="terminated", completed=False)
    fixture.write()
    result = load(fixture).seed(0)
    assert result["calibration_ready"]
    assert len(result["prediction_transitions"]) == 20
    assert result["prediction_transitions"][-1]["diagnostics"]["executed_substeps"] == 4
    assert result["prediction_transitions"][-1]["model_update"] is None


@pytest.mark.parametrize("case", ["duplicate", "id", "schedule", "unpaid_qref", "native_size", "native_bool", "gap", "evaluation_fit", "terminal_followed"])
def test_corrupted_transition_contract_rejected(fixture, case):
    row = next(r for r in fixture.rows if r["shared_transition_id"] == "seed0_calibration:100")
    if case == "duplicate":
        fixture.rows.append(deepcopy(row))
    elif case == "id":
        row["shared_transition_id"] = "new-ID"
    elif case == "schedule":
        row["requested_torque"][0] = .5
    elif case == "unpaid_qref":
        fixture.seeds[0]["reference_q"] = [.01, 0.]
    elif case == "native_size":
        row["observation_before"]["joint_position"] = [0.] * 2
    elif case == "native_bool":
        row["observation_before"]["joint_velocity"][2] = True
    elif case == "gap":
        fixture.rows.remove(row)
    elif case == "evaluation_fit":
        next(r for r in fixture.rows if r["shared_transition_id"] == "seed0_prediction:100")["model_update"] = {"updated": True}
    else:
        row["study_abort"] = "terminal"
    fixture.write()
    with pytest.raises(binding.ASourceBindingError):
        load(fixture)


@pytest.mark.parametrize("case", ["failed", "failed_alias", "scope", "git_flag", "consistency", "input_hashes", "auditor_source"])
def test_existing_audit_identity_rejected(fixture, case):
    if case == "failed":
        fixture.audit["failed"] = 1
    elif case == "failed_alias":
        fixture.audit["failed"] = False
        fixture.audit["failed_checks"] = 0
    elif case == "scope":
        fixture.audit["immutable_scope"]["calibration_steps"] = 399
    elif case == "git_flag":
        fixture.audit["execution"]["source_git_verification_enabled"] = True
    elif case == "consistency":
        fixture.audit["final_gates"]["data_consistency_verified"] = False
    fixture.write()
    if case in ("input_hashes", "auditor_source"):
        path = fixture.root / binding.A_AUDIT_PATH
        audit = json.loads(path.read_bytes())
        if case == "input_hashes":
            audit["archive"]["input_hashes"]["metadata.json"] = "0" * 64
        else:
            audit["audit_script_sha256"] = "0" * 64
        rewrite_outer_record(fixture, "first_audit.json", encode(audit))
    with pytest.raises(binding.ASourceBindingError):
        load(fixture)


@pytest.mark.parametrize("case", ["rawhash", "size", "escape", "rawmanifest", "duplicatezip", "current_source", "runtime", "plant", "snapshot_ranges"])
def test_source_and_public_identity_rejected(fixture, case):
    root = fixture.root / binding.A_ROOT
    if case == "rawhash":
        (root / "raw/seed_results.json").write_bytes(b"{}")
    elif case in ("size", "escape"):
        manifest = json.loads((root / "manifest.json").read_bytes())
        if case == "size":
            manifest["files"]["raw/metadata.json"]["bytes"] += 1
        else:
            manifest["files"]["../escape"] = manifest["files"]["first_audit.json"]
        (root / "manifest.json").write_bytes(encode(manifest))
    elif case == "rawmanifest":
        rewrite_outer_record(fixture, "raw/manifest.json", b"{}")
    elif case == "duplicatezip":
        fixture.duplicate_zip_member = binding.A_PROTOCOL_PATH
        with pytest.warns(UserWarning):
            fixture.write()
    elif case == "current_source":
        fixture.current_sources[binding.A_COLLECTOR_PATH] = b"unrelated revised source"
    elif case == "runtime":
        fixture.runtime["mujoco_version"] = "different"
    elif case == "plant":
        fixture.episodes[1]["environment_fingerprint_before"] = "0" * 64
        fixture.write()
    else:
        fixture.seeds[0]["learned_models"]["learned_guard"]["input_mapping"]["public_guard"]["public_joint_ranges_rad"][0][0] = -2.
        fixture.write()
    with pytest.raises(binding.ASourceBindingError):
        load(fixture)


def test_production_without_tracked_evidence_rejects_before_any_read(fixture, monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda _: (_ for _ in ()).throw(AssertionError("must reject before read")))
    kwargs = fixture.kwargs()
    kwargs["synthetic"] = False
    with pytest.raises(binding.ASourceBindingError, match="tracked_paths"):
        binding.load_a_source_binding(fixture.root, **kwargs)


def test_only_literal_first_audit_is_accepted(fixture):
    root = fixture.root / binding.A_ROOT
    (root / "first_audit.json").rename(root / "audit.json")
    with pytest.raises(binding.ASourceBindingError):
        load(fixture)


def test_binding_imports_no_simulation_or_model():
    source = Path(binding.__file__).read_text()
    assert "import numpy" not in source
    assert "import mujoco" not in source
    assert "import developmental_physics" not in source
    assert "import subprocess" not in source


def test_all_fixture_reads_stay_in_artificial_root(fixture, monkeypatch):
    original = Path.read_bytes
    read_paths = []
    def guarded_read(path):
        path.resolve().relative_to(fixture.root.resolve())
        read_paths.append(path)
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    load(fixture)
    assert len(read_paths) == 8  # one read of outer manifest/audit and six raw originals


def test_new_B_sources_are_allowed_without_guessing_A_paths(fixture):
    fixture.current_sources["src/developmental_physics/guard_coupled_development.py"] = b"B is a new source, absent from A"
    assert load(fixture).seed(0)["calibration_ready"]


@pytest.mark.parametrize("case", ["diagnostics", "models", "audit_execution", "episode"])
def test_malformed_nested_shapes_have_binding_error_type(fixture, case):
    if case == "diagnostics":
        fixture.rows[0]["diagnostics"] = None
    elif case == "models":
        fixture.seeds[0]["initial_models"] = None
    elif case == "audit_execution":
        fixture.audit["execution"] = None
    else:
        fixture.episodes[0] = None
    fixture.write()
    with pytest.raises(binding.ASourceBindingError):
        load(fixture)
