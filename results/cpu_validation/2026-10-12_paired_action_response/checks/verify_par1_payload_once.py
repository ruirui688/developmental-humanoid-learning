"""One lightweight saved PAR1 payload check; never replay physics or response math."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile


SEEDS = (8101, 8102, 8103)
ORIGINS = (0, 500, 1000, 1500)
SIDE_IDS = {(seed, origin, axis, sign) for seed in SEEDS for origin in ORIGINS
            for axis in (0, 1) for sign in (-1, 1)}
ORIGIN_IDS = {(seed, origin) for seed in SEEDS for origin in ORIGINS}
MODEL_IDS = {f"{seed}_{name}" for seed in SEEDS for name in ("cold", "learned")}
SOURCE_PATHS = {
    "scripts/diagnose_paired_action_response.py",
    "docs/PAIRED_ACTION_RESPONSE_DIAGNOSTIC_PROTOCOL.md",
    "src/developmental_physics/__init__.py",
    "src/developmental_physics/free_root_fast_feedback_environment.py",
    "src/developmental_physics/environment.py",
    "src/developmental_physics/assets/ground_body.xml",
    "src/developmental_physics/guard_pair_model.py",
}
PROTOCOL_PIN = {"bytes": 10425, "sha256": "8ce717c5a80b9c70185c8bbc3c0839417e3ee9209423d3fb27de80687c79526d"}
MODEL_PIN = {"bytes": 60924, "sha256": "3cfbd871c275a8f5d8a07615a239ee9e8192b5e93dcf35104cf61a01f6a6a992"}
FLAGS = ("scientific_adoption", "old_free_root_C4_validation", "c4_scientific_validation",
         "c5_scientific_dependency_released", "c4_contact_scientific_validation")
REQUIRED_FILES = {"run.json", "source.zip", "first_stdout.log", "first_stderr.log",
                  "source_trace.jsonl.gz", "fork_trace.jsonl.gz", "opaque_integration_states.npz"}


def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Fresh check directory")
    args = parser.parse_args()
    repo, raw, output = args.repo.resolve(), args.raw.resolve(), args.output.resolve()
    if output.exists() or output == raw or output.is_relative_to(raw) or raw.is_relative_to(output):
        parser.error("new_output_outside_original_payload_required")
    output.mkdir(parents=True, exist_ok=False)
    cost = Counter({"output_directory_create_attempts": 1, "output_directory_create_returns": 1})
    checks, unavailable, file_ids, cached = [], [], {}, {}
    checker_identity = None
    failure, run, complete = None, None, False

    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    def skip(name, reason):
        unavailable.append({"name": name, "reason": reason})

    def read_and_hash(path, keep=False):
        cost["file_open_attempts"] += 1
        try:
            with path.open("rb") as handle:
                cost["file_open_returns"] += 1
                digest, size, pieces = hashlib.sha256(), 0, []
                while True:
                    cost["file_read_attempts"] += 1
                    part = handle.read(1024 * 1024)
                    cost["file_read_returns"] += 1
                    cost["file_bytes_read"] += len(part)
                    if not part:
                        break
                    digest.update(part)
                    size += len(part)
                    if keep:
                        pieces.append(part)
            value = {"bytes": size, "sha256": digest.hexdigest()}
            return value, b"".join(pieces) if keep else None
        except BaseException:
            cost["file_IO_exceptions"] += 1
            raise

    def counter(name):
        value = run["cost"].get(name, 0)
        if type(value) is not int or value < 0:
            raise ValueError("invalid_nonnegative_integer_counter:" + name)
        return value

    try:
        checker_identity, _ = read_and_hash(Path(__file__).resolve())
        cost["directory_inventory_attempts"] += 1
        entries = sorted(raw.iterdir(), key=lambda path: path.name)
        cost["directory_inventory_returns"] += 1
        check("raw_entries_are_regular_files", all(path.is_file() and not path.is_symlink() for path in entries))
        for path in entries:
            if not path.is_file() or path.is_symlink():
                continue
            file_ids[path.name], blob = read_and_hash(path, keep=path.name in {"run.json", "source.zip"})
            if blob is not None:
                cached[path.name] = blob
        cost["run_JSON_decode_attempts"] += 1
        run = json.loads(cached["run.json"])
        cost["run_JSON_decode_returns"] += 1
        complete = run.get("status") == "completed"
        check("PAR1_status_and_first_failure", run.get("experiment_id") == "PAR1"
              and run.get("status") in {"completed", "stopped", "failed"}
              and (run.get("first_failure") is None if complete else isinstance(run.get("first_failure"), dict)))
        check("completed_payload_has_all_original_files", REQUIRED_FILES <= set(file_ids) if complete else True,
              {"missing": sorted(REQUIRED_FILES - set(file_ids)), "partial_execution": not complete})
        check("all_science_flags_false", all(run.get(name) is False for name in FLAGS))
        check("no_control_opening_or_partial_ranking", run.get("control_candidate_opened") is False
              and run.get("partial_subset_ranking") is False)
        zero_fields = ("fit_calls", "RLS_updates", "model_predict_calls", "SVD_calls", "inverse_solves", "old_math_recomputations")
        check("zero_learning_and_replay_fields", all(run.get(name) == 0 and type(run.get(name)) is int for name in zero_fields))
        cfg = run["config"]
        check("fixed_population_config", cfg["seeds"] == list(SEEDS) and cfg["origins_before_active_step"] == list(ORIGINS)
              and cfg["side_order"] == [[0, -1], [0, 1], [1, -1], [1, 1]]
              and cfg["prefix"] == 1000 and cfg["active"] == 2000 and cfg["dose_nm"] == .125
              and cfg["dt_seconds"] == .002 and cfg["study_q_rad"] == .12 and cfg["study_v_rad_s"] == 1.)
        sides = run["complete_planned_side_population"]
        ids = [(item["seed"], item["origin_active_index"], item["axis"], item["sign"]) for item in sides]
        check("all_48_planned_sides_preserved", len(ids) == 48 and len(set(ids)) == 48 and set(ids) == SIDE_IDS)
        statuses = {"not_attempted", "attempted", "unavailable", "finite_response_available"}
        check("side_status_population", all(item.get("status") in statuses for item in sides)
              and (all(item["status"] in {"unavailable", "finite_response_available"} for item in sides) if complete else True))
        reasons = {"outside_permission_no_clip", "guard_zero_effective_input", "weak_signal"}
        check("NA_reasons_preserved", all(item.get("unavailable_reason") in reasons
              for item in sides if item.get("status") == "unavailable"))
        permission_na = [item for item in sides if item.get("unavailable_reason") == "outside_permission_no_clip"]
        check("permission_NA_has_original_request", all(isinstance(item.get("requested2"), list)
              and len(item["requested2"]) == 2 for item in permission_na))
        finished = [item for item in sides if item.get("status") == "finite_response_available"
                    or item.get("unavailable_reason") in {"guard_zero_effective_input", "weak_signal"}]
        response_keys = {"actual_response_v2", "model_response_v2", "model_error_v2", "base_request2",
                         "projected_base2", "projected_side2", "base_guard_blocked", "side_guard_blocked"}
        check("stepped_NA_and_responses_retained", all(response_keys <= set(item) for item in finished))
        origins = run["origins"]
        origin_ids = [(item["seed"], item["origin_active_index"]) for item in origins]
        check("origin_population", len(set(origin_ids)) == len(origin_ids) and set(origin_ids) <= ORIGIN_IDS
              and (set(origin_ids) == ORIGIN_IDS if complete else True))
        check("completed_12_qualifications", len(origins) == 12 and all(item.get("qualification") ==
              "passed_exact_pre_and_endpoint" for item in origins) if complete else True,
              "Saved labels only; no state-match recomputation")
        trials = run["source_trials"]
        trial_seeds = [item["seed"] for item in trials]
        check("source_trial_population", len(set(trial_seeds)) == len(trial_seeds) and set(trial_seeds) <= set(SEEDS)
              and (set(trial_seeds) == set(SEEDS) and all(item.get("status") == "completed"
                   and item.get("planned_source_controls") == 3000 for item in trials) if complete else True))
        limits = {"source_control_attempts": 9000, "source_control_returns": 9000,
                  "qualification_control_attempts": 12, "qualification_control_returns": 12,
                  "side_control_attempts": 48, "side_control_returns": 48,
                  "total_control_attempts": 9060, "confirmed_physics_substeps": 9060,
                  "mj_step_attempts": 9060, "mj_step_returns": 9060,
                  "pre_data_copy_attempts": 12, "fork_data_copy_attempts": 60,
                  "theta_scalars_read": 108, "finite_effect_pair_returns": 48,
                  "model_response_pair_returns": 96, "new_response_scalar_labels": 96,
                  "model_response_scalar_outputs": 192}
        counts = {name: counter(name) for name in limits}
        check("actual_counters_within_fixed_caps", all(counts[name] <= cap for name, cap in limits.items()), counts)
        check("total_controls_are_source_and_forks", counter("total_control_attempts") == sum(
              counter(group + "_control_attempts") for group in ("source", "qualification", "side")))
        check("physics_cost_not_rewound_by_clone", counter("confirmed_physics_substeps") == sum(
              counter(group + "_confirmed_physics_substeps") for group in ("source", "qualification", "side")))
        check("completed_source_and_fork_counts", (counter("source_control_attempts") == 9000
              and counter("source_control_returns") == 9000 and counter("source_confirmed_physics_substeps") == 9000
              and counter("qualification_control_returns") == 12 and counter("side_control_returns") == len(finished)
              and len(finished) + len(permission_na) == 48 and counter("finite_effect_pair_returns") == len(finished)
              and counter("model_response_pair_returns") == 2 * len(finished)
              and counter("confirmed_physics_substeps") == 9000 + 12 + len(finished)) if complete else True)
        fingerprints = run["model_fingerprints"]
        check("saved_model_fingerprint_population", set(fingerprints) <= MODEL_IDS
              and (set(fingerprints) == MODEL_IDS if complete else True))
        fingerprint_fields = {"before", "after", "theta_bytes_before", "theta_bytes_after"}
        check("saved_model_fingerprints_unchanged", all(fingerprint_fields <= set(item)
              and item["before"] == item["after"] and item["theta_bytes_before"] == item["theta_bytes_after"]
              for item in fingerprints.values()))
        check("completed_model_source_pin", run["model_source"].get("identity") == MODEL_PIN if complete else True)
        source = run.get("source")
        if source is not None and "source.zip" in cached:
            commit = source.get("commit", "")
            check("exact_source_commit_and_manifest", bool(re.fullmatch(r"[0-9a-f]{40}", commit))
                  and source.get("clean_committed_bytes_verified") is True and set(source["files"]) == SOURCE_PATHS)
            cost["source_ZIP_open_attempts"] += 1
            with zipfile.ZipFile(io.BytesIO(cached["source.zip"])) as archive:
                cost["source_ZIP_open_returns"] += 1
                names = archive.namelist()
                check("source_ZIP_population", len(names) == len(SOURCE_PATHS) and set(names) == SOURCE_PATHS)
                for name in names:
                    cost["source_ZIP_member_read_attempts"] += 1
                    blob = archive.read(name)
                    cost["source_ZIP_member_read_returns"] += 1
                    cost["source_ZIP_decoded_bytes_read"] += len(blob)
                    check("ZIP_manifest_identity:" + name, identity(blob) == source["files"].get(name))
                    if not re.fullmatch(r"[0-9a-f]{40}", commit):
                        skip("ZIP_git_identity:" + name, "Invalid saved source commit; no git request")
                        continue
                    cost["git_blob_query_attempts"] += 1
                    result = subprocess.run(["git", "show", commit + ":" + name], cwd=repo, capture_output=True, check=False)
                    cost["git_blob_query_returns"] += 1
                    cost["git_stdout_bytes_read"] += len(result.stdout)
                    cost["git_stderr_bytes_read"] += len(result.stderr)
                    check("ZIP_git_identity:" + name, result.returncode == 0 and result.stdout == blob)
                    if name == "docs/PAIRED_ACTION_RESPONSE_DIAGNOSTIC_PROTOCOL.md":
                        check("frozen_protocol_pin", identity(blob) == PROTOCOL_PIN)
        else:
            check("completed_source_archive_available", not complete)
            skip("source_ZIP_bindings", "First partial failure has no saved source/archive; not repaired")
        stream_meta = run["streams"]
        for name, item in stream_meta.items():
            path = item.get("path")
            check("stream_saved_identity_scope:" + name, path == name + ".jsonl.gz" and path in file_ids
                  and item.get("format") == "gzip_jsonl" and item.get("identity_scope") == "decoded_jsonl"
                  and type(item.get("records")) is int and item["records"] >= 0
                  and type(item.get("bytes")) is int and item["bytes"] >= 0
                  and isinstance(item.get("sha256"), str) and bool(re.fullmatch(r"[0-9a-f]{64}", item["sha256"])),
                  "Compressed file identity recorded separately; decoded identity not recalculated")
        check("completed_two_stream_manifests", set(stream_meta) == {"source_trace", "fork_trace"} if complete else True)
    except BaseException as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
        check("verification_first_error", False, failure)

    failed = sum(not item["passed"] for item in checks)
    report = {"experiment_id": "PAR1_saved_payload_contract", "status": "passed" if failed == 0 else "failed",
              "execution_completed": complete, "execution_status": None if run is None else run.get("status"),
              "partial_execution_contract": not complete, "scientific_gate_evaluated": False,
              "scientific_validation": False, "checks": checks, "checked": len(checks), "failed": failed,
              "unavailable": unavailable, "first_verification_failure": failure, "raw_directory": str(raw),
              "checker_source": {"path": str(Path(__file__).resolve()), "identity": checker_identity},
              "original_file_identities": file_ids, "IO_through_before_checks_JSON_write": dict(cost),
              "saved_IO_excludes": "Final checks JSON encode/write and final stdout; actual write reported on stdout",
              "unmeasured_filesystem_metadata_IO": "unknown_not_zero",
              "gzip_trace_decode_calls": 0, "opaque_state_decode_calls": 0, "response_math_calls": 0,
              "clone_match_recomputations": 0, "model_calls": 0, "physics_calls": 0,
              "protocol_pin": PROTOCOL_PIN, "all_science_flags_false_required": list(FLAGS)}
    payload = (json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    cost["checks_JSON_encoded_bytes"] = len(payload)
    cost["checks_file_open_attempts"] += 1
    with (output / "checks.json").open("xb") as handle:
        cost["checks_file_open_returns"] += 1
        cost["checks_file_write_attempts"] += 1
        written = handle.write(payload)
        cost["checks_file_write_returns"] += 1
        cost["checks_bytes_written"] += written
    print(json.dumps({"status": report["status"], "execution_status": report["execution_status"],
                      "checks": len(checks), "failed": failed, "output": str(output / "checks.json"),
                      "actual_IO_including_checks_write": dict(cost), "scientific_validation": False}))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
