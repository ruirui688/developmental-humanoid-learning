"""One tiny handwritten F statistics/interface fixture; never an E archive."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import traceback

import diagnose_guard_native_context as f


def observation(q0, other, gyro, acceleration):
    return {"joint_position": [q0, -q0, *([other]*6)], "joint_velocity": [0.]*8,
            "imu_gyro": [gyro, 0., 0.], "imu_acceleration": [acceleration, 0., 0.]}


def fixture():
    tid = "seed0_cold11"
    observations = [observation(0., 0., 0., 0.), observation(0., 0., 0., 0.),
                    observation(0., 0., 0., .5), observation(.01, .15, .5, 1.5),
                    observation(.02, .30, 1., 3.), observation(.03, .45, 1.5, 5.),
                    observation(.04, .60, 2., 7.5)]
    predictions = [((.01, -.01), (0., 0.)), ((.01, -.01), (.1, -.1)),
                   ((.01, -.01), (.2, -.2)), ((.01, -.01), (.3, -.3))]
    rows = []
    for offset, index in enumerate(range(98, 104)):
        row = {"trial_id": tid, "seed": 0, "kind": "cold11", "step_index": index,
               "shared_transition_id": f"{tid}:{index}", "phase": "prefix" if index < 100 else "control",
               "observation_before": observations[offset], "observation_after": observations[offset+1],
               "diagnostics": {"executed_substeps": 4 if index == 103 else 10,
                               "terminated": index == 103}, "study_abort": None,
               "target_q": None if index < 100 else [.04, -.04], "predicted_next_qv": {},
               "history": None if index < 100 else {"native_contiguous": True,
                   "history_transition_ids": [f"{tid}:{index-2}", f"{tid}:{index-1}"],
                   "current_v_rad_s": [0., 0.], "previous_v_rad_s": [0., 0.]}}
        if index >= 100:
            row["predicted_next_qv"] = {name: predictions[index-100] for name in f.PREDICTORS}
        rows.append(row)
    # Two source-notification shapes, not two new physical endpoints.
    duplicate = copy.deepcopy(rows[-1])
    duplicate.update(collector_exception={"type": "ArtificialNotice"}, returned_step_diagnostics=duplicate.pop("diagnostics"))
    invalid = {"trial_id": tid, "seed": 0, "kind": "cold11", "step_index": None,
               "shared_transition_id": None, "collector_exception": {"type": "ArtificialNotice"}}
    rows.extend((duplicate, invalid))
    episode = {"trial_id": tid, "seed": 0, "kind": "cold11", "status": "terminated",
               "study_abort": None, "environment_terminated": True,
               "environment_stop_reason": "artificial_partial_stop", "returned_steps": 6,
               "written_returned_steps": 6, "returned_unwritten_steps": 0,
               "unreturned_physics_steps": 0, "collector_exception": None,
               "phase_budgets": {"prefix": {"control_calls_attempted": 2, "control_steps": 2, "physics_steps": 20},
                                 "control": {"control_calls_attempted": 4, "control_steps": 4, "physics_steps": 34}}}
    return rows, episode


def run_checks(output):
    fee = f.new_fee()
    rows, episode = fixture()
    outcomes = []
    report = None
    try:
        report = f.diagnose_rows(rows, [episode], fee)
        derived = report["derived_by_trial"][episode["trial_id"]]
        assert len(derived) == 4 and [r["executed_substeps"] for r in derived] == [10, 10, 10, 4]
        assert [r["scores"]["acc_delta"] for r in derived] == [.5, 1., 1.5, 2.]
        assert all(r["native_prediction_history_valid"] for r in derived)
        assert derived[-1]["saved_errors"]["cold11"]["q"] is None
        event = report["events"][0]
        assert event["tail20_counts"]["returned_endpoint_n"] == 4
        assert event["tail20_counts"]["complete_interval_n"] == 3
        assert event["tail20_counts"]["partial_interval_n"] == 1
        assert event["earlier_counts"]["returned_endpoint_n"] == 0
        assert len(report["exception_notifications"][episode["trial_id"]]) == 2
        assert [n["identity_status"] for n in report["exception_notifications"][episode["trial_id"]]] == [
            "duplicate_notification", "missing_or_invalid_notification_identity"]
        group = next(g for g in report["groups"] if g["axis"] == 0 and g["predictor"] == "cold11"
                     and g["error_channel"] == "q" and g["target_segment"] == "A" and g["window"] == "all")
        gyro = next(x for x in group["statistics"] if x["score"] == "gyro")
        assert gyro["paired_n"] == 3 and abs(gyro["pearson_signed"]["r"]-1.) < 1e-12
        assert [x["n"] for x in gyro["fixed_bins"]] == [1, 1, 1]
        assert group["unobserved_planned_endpoint_n"] == 96
        empty = next(g for g in report["groups"] if g["window"] == "earlier")
        assert all(s["pearson_signed"]["reason"] == "empty_window" for s in empty["statistics"])
        assert report["scientific_adoption"]["passed"] is False
        outcomes.append({"check": "single_small_core_history_bins_partial_stop_notifications", "passed": True})
    except BaseException as exc:
        outcomes.append({"check": "single_small_core_history_bins_partial_stop_notifications", "passed": False,
                         "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    try:
        xd = f.describe([0., 1e-200, 2e-200], fee)
        yd = f.describe([0., 1., 2.], fee)
        assert f.pearson([0., 1e-200, 2e-200], [0., 1., 2.], xd, yd, fee)["reason"] == "numerical_unavailable"
        constant = f.describe([1., 1., 1.], fee)
        assert f.pearson([1., 1., 1.], [0., 1., 2.], constant, yd, fee)["reason"] == "zero_variance"
        assert f.norm([1e308, 1e308], fee) is None
        exception_episode = {**episode, "status": "exception"}
        empty_report = f.summarize_records({episode["trial_id"]: []}, [exception_episode], fee)
        assert empty_report["events"][0]["source_stop"] is False
        assert empty_report["events"][0]["stop_flags_in_exception"] is True
        outcomes.append({"check": "numerical_zero_variance_and_exception_classification", "passed": True})
    except BaseException as exc:
        outcomes.append({"check": "numerical_zero_variance_and_exception_classification", "passed": False,
                         "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    try:
        assert f.FORMAL_DIAGNOSTIC_ENABLED is False
        blocked_path = output/"must_not_exist"
        try:
            f.run_diagnostic(output/"no_archive", output/"no_binding", "0"*64, blocked_path)
        except RuntimeError:
            pass
        else:
            raise AssertionError("formal interface must refuse before filesystem access")
        assert not blocked_path.exists()
        assert all(fee[key] == 0 for key in f.ZERO_WORK)
        outcomes.append({"check": "disabled_formal_interface_zero_model_physics", "passed": True})
    except BaseException as exc:
        outcomes.append({"check": "disabled_formal_interface_zero_model_physics", "passed": False,
                         "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()})
    return {"outcomes": outcomes, "passed": sum(x["passed"] for x in outcomes),
            "failed": sum(not x["passed"] for x in outcomes), "descriptive_fee": dict(fee),
            "fixture_source_rows": len(rows), "fixture_unique_active_endpoints": 4,
            "fixture_construction": "literal encoder/IMU/prediction values; no model or simulation",
            "core_report": report}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name in ("diagnose_guard_native_context.py", "check_small_once.py"):
        source = Path(__file__).with_name(name)
        shutil.copyfile(source, args.output/name)
        hashes[name] = hashlib.sha256((args.output/name).read_bytes()).hexdigest()
    wall, cpu = time.perf_counter(), time.process_time()
    report = run_checks(args.output)
    report.update(source_sha256=hashes, wall_seconds=time.perf_counter()-wall,
                  cpu_seconds=time.process_time()-cpu, python=sys.version,
                  real_source_reads=0, real_raw_data_reads=0, formal_runs=0)
    f.write_json(args.output/"run.json", report)
    print(json.dumps({key: report[key] for key in ("passed", "failed", "descriptive_fee", "wall_seconds", "cpu_seconds")}, indent=2))
    return int(report["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
