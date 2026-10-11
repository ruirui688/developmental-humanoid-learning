"""One necessary revision check: fake inputs only, no descriptive statistics."""
import ast
import hashlib
import json
from pathlib import Path
import time
import traceback

base = Path(__file__).resolve().parent.parent
revision = base/"revision_01"
output = revision/"BRANCH_CHECK_01.json"
if output.exists():
    raise FileExistsError("one-attempt branch check must not overwrite its record")
started_wall, started_cpu = time.perf_counter(), time.process_time()
paths = [base/"diagnose_guard_native_context.py",
         revision/"diagnose_guard_native_context.ast02_verified.py",
         revision/"diagnose_guard_native_context.original.py",
         base.parent/"c4_native_context_protocol_staging/F_PROTOCOL_DRAFT.md"]
blobs = [path.read_bytes() for path in paths]
record = {"source_reads": {"opens": 4, "binary_bytes": sum(map(len, blobs)),
                          "hash_operations": 4, "AST_parses": 3},
          "source_sha256": hashlib.sha256(blobs[0]).hexdigest(),
          "ast02_source_sha256": hashlib.sha256(blobs[1]).hexdigest(),
          "original_source_sha256": hashlib.sha256(blobs[2]).hexdigest(),
          "protocol_sha256": hashlib.sha256(blobs[3]).hexdigest(),
          "scope": "explicit source/fake-fixture/output reads only; excludes Python interpreter/import reads and this final report serialization/write",
          "descriptive_statistical_math": 0, "model_imports": 0, "model_calls": 0,
          "RLS_updates": 0, "physical_queries": 0, "actual_E_C_D_reads": 0,
          "git_calls": 0, "old_statistical_fixture_reexecutions": 0}
checks = {}
try:
    trees = [ast.parse(blob) for blob in blobs[:3]]
    functions = [{node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)} for tree in trees]
    dump = lambda node: ast.dump(node, include_attributes=False)
    protected = ("finite", "vector", "sub", "mul", "div", "total", "square", "root", "norm",
                 "native_equal", "native_scores", "saved_errors", "describe", "safe_mean", "pearson",
                 "score_statistics", "summarize_records")
    for name in protected:
        checks["AST_original_protected_"+name] = dump(functions[0][name]) == dump(functions[2][name])
    for name in functions[0]:
        if name != "derive_rows":
            checks["AST_since02_"+name] = dump(functions[0][name]) == dump(functions[1][name])
    new_derive = ast.unparse(functions[0]["derive_rows"])
    old_derive = ast.unparse(functions[1]["derive_rows"])
    expected_derive = old_derive.replace(
        "if identity != f'{tid}:{index}' or identity in history['seen']:",
        "if not isinstance(identity, str) or identity != f'{tid}:{index}' or identity in history['seen']:")
    expected_derive = expected_derive.replace(
        "if identity in history['seen'] else 'regular_wrong_transition_identity_failures'",
        "if isinstance(identity, str) and identity in history['seen'] else 'regular_wrong_transition_identity_failures'")
    checks["AST_since02_only_regular_identity_type_guard"] = new_derive == expected_derive
    namespace = {"__file__": str(paths[0].resolve()), "__name__": "f_revision_fake_check"}
    exec(compile(blobs[0], str(paths[0]), "exec"), namespace)
    checks["formal_flag_false_on_disk"] = namespace["FORMAL_DIAGNOSTIC_ENABLED"] is False

    forbidden_called = []
    def forbidden(name):
        def fail(*args, **kwargs):
            forbidden_called.append(name)
            raise AssertionError("forbidden descriptive/model branch: "+name)
        return fail
    for name in ("native_scores", "saved_errors", "describe", "safe_mean", "pearson",
                 "score_statistics", "summarize_records", "diagnose_rows", "cached_trace_rows"):
        namespace[name] = forbidden(name)

    fee = namespace["new_fee"]()
    reasons = {name: {} for name in namespace["PREDICTORS"]}
    flags = namespace["input_quality_flags"]({}, None, None, False, False, reasons, fee)
    expected = {
        "current_native_joint_position:missing", "current_native_joint_velocity:missing",
        "current_native_imu_gyro:missing", "current_native_imu_acceleration:missing",
        "previous_native_endpoint:unavailable_or_discontinuous", "prefix99_native_qref:unavailable",
        "current_target:missing", "prediction_native_history:missing", "interval:not_complete_20ms",
        "observed_next_q_label:missing", "observed_next_v_label:missing",
        "saved_cold11_q_prediction:missing", "saved_cold11_v_prediction:missing",
        "saved_learned_sparse11_q_prediction:missing", "saved_learned_sparse11_v_prediction:missing"}
    checks["all_15_simultaneous_missing_flags_retained"] = set(flags) == expected and len(flags) == 15
    checks["all_independent_missing_fee_counts_one"] = all(fee["input_quality_flag:"+flag] == 1 for flag in expected)

    row = {"observation_before": {"joint_position": [0]*8, "joint_velocity": [0]*8,
             "imu_gyro": [float("inf"), 0, 0], "imu_acceleration": [0, 0]},
           "observation_after": {"joint_position": None, "joint_velocity": ["bad"]*8},
           "target_q": ["bad", 0], "history": {},
           "predicted_next_qv": {"cold11": [[float("nan"), 0], None], "learned_sparse11": [[]]}}
    reasons["cold11"]["q"] = "nonfinite_saved_difference"
    mixed = namespace["input_quality_flags"](row, (0,)*8,
        {"imu_acceleration": [None, 0, 0]}, False, False, reasons, fee)
    mixed_expected = {"current_native_imu_gyro:nonfinite", "current_native_imu_acceleration:wrong_shape",
        "previous_native_acceleration:invalid_scalar_type", "current_target:invalid_scalar_type",
        "prediction_native_history:invalid_or_discontinuous", "interval:not_complete_20ms",
        "observed_next_q_label:missing", "observed_next_v_label:invalid_scalar_type",
        "saved_cold11_q_prediction:nonfinite", "saved_cold11_q_difference:nonfinite",
        "saved_cold11_v_prediction:missing", "saved_learned_sparse11_q_prediction:wrong_container_shape",
        "saved_learned_sparse11_v_prediction:wrong_container_shape"}
    checks["mixed_quality_causes_do_not_overwrite_each_other"] = set(mixed) == mixed_expected and len(mixed) == 13
    episode = {"trial_id": "fake", "seed": 0, "kind": "cold11"}
    groups = namespace["quality_counts"]({"fake": [{"target_segment": "A", "input_quality_flags": flags},
        {"target_segment": "A", "input_quality_flags": mixed}]}, [episode])
    checks["independent_counts_keep_rows_and_flags_distinct"] = (
        groups[0]["saved_active_records"] == 2 and groups[0]["rows_with_any_quality_flag"] == 2
        and groups[0]["independent_flag_counts"]["interval:not_complete_20ms"] == 2
        and sum(groups[0]["independent_flag_counts"].values()) == 28)
    record["quality_fake_fee"] = dict(fee)

    identity_records = []
    base_row = {"trial_id": "fake", "seed": 0, "kind": "cold11", "step_index": 0,
                "shared_transition_id": "fake:0", "phase": "prefix"}
    cases = [("missing", None, "regular_missing_transition_identity_failures"),
             ("wrong", "other:0", "regular_wrong_transition_identity_failures"),
             ("unhashable", [], "regular_wrong_transition_identity_failures"),
             ("duplicate", "fake:0", "regular_duplicate_transition_identity_failures")]
    for label, identity, counter in cases:
        identity_fee = namespace["new_fee"]()
        fake_row = dict(base_row, shared_transition_id=identity)
        supplied = [base_row, fake_row] if label == "duplicate" else [fake_row]
        caught = None
        try:
            namespace["derive_rows"](supplied, [episode], identity_fee)
        except ValueError as exc:
            caught = str(exc)
        checks["regular_identity_"+label+"_counts_before_exit"] = caught is not None and identity_fee[counter] == 1
        identity_records.append({"case": label, "error": caught, "fee": dict(identity_fee)})
    record["fake_identity_failures"] = identity_records

    fake_blob = b"F provenance fixture only\n"
    fake_file = revision/"read_fee_fake_01.bin"
    with fake_file.open("xb") as writer:
        writer.write(fake_blob)
    local_fee = namespace["new_fee"]()
    for label in ("source", "binding", "protocol"):
        assert namespace["read_f_local"](fake_file, label, local_fee) == fake_blob
    checks["f_local_reads_record_each_of_three_labels"] = (
        local_fee["f_local_file_opens"] == 3 and local_fee["f_local_binary_bytes_read"] == 3*len(fake_blob)
        and all(local_fee["f_local_"+label+"_opens"] == 1 and
                local_fee["f_local_"+label+"_binary_bytes_read"] == len(fake_blob)
                for label in ("source", "binding", "protocol")))
    record["fake_local_read_fee"] = dict(local_fee)

    fake_root = revision.resolve()
    fake_archive = fake_root/"fake_archive_not_read"
    fake_output = revision/"fake_preflight_01"
    provenance = {"source_commit": "a"*40, "source_sha256": record["source_sha256"],
                  "binding_path": "fake_binding.json", "binding_sha256": "b"*64,
                  "protocol": {"path": "fake_protocol.md", "sha256": record["protocol_sha256"]},
                  "source_dirty": False, "synthetic_test_provenance": True}
    call_count = {"clean_f_stub_calls": 0, "e_preflight_stub_calls": 0}
    def fake_clean(binding_path, fee):
        call_count["clean_f_stub_calls"] += 1
        return fake_root, {"archive_relative_path": "fake_archive_not_read"}, provenance
    def fake_preflight(*args, **kwargs):
        call_count["e_preflight_stub_calls"] += 1
        raise ValueError("synthetic first E preflight failure; no E files opened")
    namespace["clean_f_provenance"] = fake_clean
    namespace["sealed_e_inputs"] = fake_preflight
    namespace["FORMAL_DIAGNOSTIC_ENABLED"] = True  # in-memory fake exercise only
    caught = None
    try:
        namespace["run_diagnostic"](fake_archive, revision/"fake_binding_not_read.json", "c"*64, fake_output)
    except ValueError as exc:
        caught = str(exc)
    finally:
        namespace["FORMAL_DIAGNOSTIC_ENABLED"] = False
    output_blobs = [(fake_output/name).read_bytes() for name in ("run.json", "manifest.json")]
    fake_run, fake_manifest = [json.loads(blob) for blob in output_blobs]
    checks["first_e_preflight_failure_preserves_verified_f_identity"] = (
        fake_run["status"] == "exception" and fake_run["f_provenance"] == provenance
        and caught == "synthetic first E preflight failure; no E files opened")
    checks["preflight_timing_and_output_integrity_scopes_present"] = (
        "excludes run/manifest" in fake_run["timing_scope"]
        and "excludes final manifest" in fake_manifest["final_record_timing"]["scope"]
        and fake_manifest["output_integrity_reads"]["opens"] == 1)
    checks["no_statistical_or_e_file_branch_executed"] = not forbidden_called and call_count == {
        "clean_f_stub_calls": 1, "e_preflight_stub_calls": 1}
    record["fake_preflight"] = {"stub_call_counts": call_count, "run_descriptive_fee": fake_run["descriptive_fee"],
        "run_wall_seconds": fake_run["wall_seconds"], "run_cpu_seconds": fake_run["cpu_seconds"],
        "runtime_output_integrity_reads": fake_manifest["output_integrity_reads"],
        "runtime_final_record_timing": fake_manifest["final_record_timing"],
        "harness_output_reads": {"opens": 2, "binary_bytes": sum(map(len, output_blobs)), "hash_operations": 0}}
    checks["formal_flag_restored_false_in_memory"] = namespace["FORMAL_DIAGNOSTIC_ENABLED"] is False
    record.update(checks=checks, passed=sum(checks.values()), failed=sum(not value for value in checks.values()))
except BaseException as exc:
    record.update(checks=checks, passed=sum(checks.values()), failed=1+sum(not value for value in checks.values()),
        harness_exception={"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
finally:
    record.update(wall_seconds=time.perf_counter()-started_wall, cpu_seconds=time.process_time()-started_cpu)
    with output.open("x", encoding="utf-8", newline="\n") as writer:
        json.dump(record, writer, indent=2, allow_nan=False)
        writer.write("\n")
    print(json.dumps(record, indent=2, allow_nan=False))
raise SystemExit(int(record["failed"] != 0))
