"""First-only necessary synthetic CF1 history checks; no old data or physics."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import json
from pathlib import Path
import sys
import traceback

import numpy as np


def identity(blob):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


def expect_value_error(callback):
    try:
        callback()
    except ValueError as exc:
        return {"type": type(exc).__name__, "message": str(exc)}
    raise AssertionError("missing_history_or_continuity_error_was_not_rejected")


def check_history_formula(body):
    ranges = np.asarray([[-1., 1.], [-1., 1.]])
    model = body.CausalIncrementalPairModel(ranges, np.asarray([[.2, 0., 0., 0.], [0., .2, 0., 0.]]))
    qprev, vprev, uprev = np.asarray([-.98, 0.]), np.zeros(2), np.asarray([-.5, 0.])
    q, v, request = np.asarray([-.95, 0.]), np.asarray([.02, 0.]), np.asarray([-.5, 0.])
    memory = body.NativeIntervalMemory("synthetic", 9, qprev, vprev, uprev, q, v)
    next_q, next_v, own_memory, drift = model.predict(q, v, request, memory, "synthetic", 10)
    # The previous negative request was blocked at previous q, while the
    # current one is allowed. B already has velocity-increment units.
    np.testing.assert_allclose(drift, np.asarray([.02, 0.]), rtol=0., atol=1e-15)
    np.testing.assert_allclose(next_v, np.asarray([-.06, 0.]), rtol=0., atol=1e-15)
    np.testing.assert_allclose(next_q, np.asarray([-.95012, 0.]), rtol=0., atol=1e-15)
    assert own_memory.qprev.tobytes() == q.tobytes()
    assert own_memory.vprev.tobytes() == v.tobytes()
    assert own_memory.requestprev.tobytes() == request.tobytes()
    recursive_q, recursive_v, recursive_memory, recursive_drift = model.predict(
        next_q, next_v, np.zeros(2), own_memory, "synthetic", 11)
    np.testing.assert_allclose(recursive_drift, np.asarray([.02, 0.]), rtol=0., atol=1e-15)
    np.testing.assert_allclose(recursive_v, np.asarray([-.04, 0.]), rtol=0., atol=1e-15)
    np.testing.assert_allclose(recursive_q, np.asarray([-.9502, 0.]), rtol=0., atol=1e-15)
    assert recursive_memory.qprev.tobytes() == next_q.tobytes()
    assert recursive_memory.vprev.tobytes() == next_v.tobytes()
    missing = expect_value_error(lambda: model.predict(q, v, request, None, "synthetic", 10))
    cross_trial = expect_value_error(lambda: model.predict(q, v, request, memory, "other_trial", 10))
    discontinuous = expect_value_error(lambda: model.predict(q+np.asarray([.001, 0.]), v, request, memory, "synthetic", 10))
    return {"case": "past_guard_increment_units_own_recursive_memory_and_required_history", "passed": True,
            "first_next_q": next_q.tolist(), "first_next_v": next_v.tolist(), "drift": drift.tolist(),
            "recursive_q": recursive_q.tolist(), "recursive_v": recursive_v.tolist(),
            "expected_rejections": [missing, cross_trial, discontinuous], "new_pair_returns": 2}


class UnreadableArray:
    def __array__(self, *args, **kwargs):
        raise AssertionError("privileged_field_was_consumed")


def source_row(index, before_q, after_q):
    active = index-1
    before = {"joint_position": before_q.copy(), "joint_velocity": np.zeros(8),
              "actuator_torque": UnreadableArray(), "root_orientation": UnreadableArray()}
    after = {"joint_position": after_q.copy(), "joint_velocity": np.zeros(8),
             "actuator_torque": UnreadableArray(), "root_orientation": UnreadableArray()}
    return {"seed": 1, "trial_id": "synthetic_trial", "kind": "identification", "control_index": index,
            "active_index": active, "stage": "prefix" if active < 0 else "A", "phase": "prefix" if active < 0 else "active",
            "returned": True, "confirmed_physics_substeps": 1, "diagnostics": {"executed_substeps": 1,
                "terminated": False, "reason": None, "applied_torque": UnreadableArray()},
            "observation_before": before, "observation_after": after, "requested_torque8": np.zeros(8),
            "current_target_q2": np.zeros(2), "audit_contacts": UnreadableArray()}


def check_native_continuity(body):
    def selector():
        return body.NativeCausalTraceStream((1,), {1: "synthetic_trial"}, {1: np.zeros(2)}, total_count=3, prefix_count=1)
    stream = selector()
    rows = [source_row(index, np.zeros(8), np.zeros(8)) for index in range(3)]
    first = stream.accept(rows[0])
    active0 = stream.accept(rows[1])
    memory = body.interval_memory(first)
    memory.require_current(active0["q"], active0["v"], active0["trial_id"], active0["control_index"])
    assert memory.control_index == 0 and active0["active_index"] == 0
    stream.accept(rows[2])
    assert stream.finish() == {1: 3}
    broken = selector()
    broken.accept(rows[0])
    bad = copy.copy(rows[1])
    bad["observation_before"] = dict(rows[1]["observation_before"])
    bad["observation_before"]["joint_position"] = np.asarray([.001, 0., 0., 0., 0., 0., 0., 0.])
    continuity = expect_value_error(lambda: broken.accept(bad))
    duplicate = expect_value_error(lambda: broken.accept(rows[0]))
    missing = expect_value_error(lambda: broken.finish())
    stopped = selector()
    stopped_row = dict(rows[0], stop={"study_abort": "synthetic_stop"})
    stopped_error = expect_value_error(lambda: stopped.accept(stopped_row))
    return {"case": "complete_prefix_active0_native_history_and_no_privileged_inputs", "passed": True,
            "complete_counts": {"1": 3}, "prefix_memory_control_index": memory.control_index,
            "expected_rejections": [continuity, duplicate, missing, stopped_error], "privileged_fields_consumed": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output.exists() or output == repo or repo.is_relative_to(output):
        parser.error("first_new_output_directory_required")
    output.mkdir(parents=True, exist_ok=False)
    script_blob = Path(__file__).read_bytes()
    (output / "check_script.py").write_bytes(script_blob)
    result = {"status": "running", "checks": [], "first_failure": None, "script": identity(script_blob),
              "new_physics": 0, "old_model_calls": 0, "old_fit_gate_RMSE_recomputations": 0,
              "old_data_reads": 0, "fixture_inputs": "explicit_numpy_arrays"}
    def seal():
        (output / "checks.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    seal()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                sys.path.insert(0, str(repo / "src"))
                import developmental_physics.causal_incremental_pair_model as body
                result["source"] = {str(path.relative_to(repo)).replace("\\", "/"): identity(path.read_bytes()) for path in (
                    repo / "src/developmental_physics/causal_incremental_pair_model.py",
                    repo / "src/developmental_physics/instrumental_action_model.py",
                    repo / "src/developmental_physics/__init__.py")}
                seal()
                for check in (check_history_formula, check_native_continuity):
                    case = check(body)
                    result["checks"].append(case)
                    with (output / "case_results.jsonl").open("a", encoding="utf-8") as history:
                        history.write(json.dumps(case, ensure_ascii=False, allow_nan=False)+"\n")
                        history.flush()
                    seal()
                result["status"] = "passed"
            except BaseException as exc:
                result["status"] = "failed"
                result["first_failure"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
            finally:
                seal()
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
