"""Read the first archived FR0 report payloads once; never execute science.

Run only after the first physical execution has finished and been archived.
No raw trajectory, contact, model, test or experiment entry point is imported.
Saved metrics are copied, never recomputed or reclassified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time


PAYLOADS = ("raw/run.json", "raw/metrics.json", "execution.json", "manifest.json")


def selected(mapping: dict, keys: tuple[str, ...]) -> dict:
    """Copy saved values without substituting zero for absent observations."""
    return {key: mapping.get(key) for key in keys}


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive", type=Path,
        default=repo / "results/cpu_validation/2026-10-12_free_root_fast_feedback_engineering",
    )
    parser.add_argument(
        "--output", type=Path, default=repo / "external/c4_fr0_report_input.json",
    )
    args = parser.parse_args()
    archive, output = args.archive.resolve(), args.output.resolve()

    # Fail before paying any payload reads if the output or archive is not ready.
    if output.exists():
        raise FileExistsError("new_FR0_reporting_summary_required")
    if not archive.is_dir():
        raise FileNotFoundError("first_FR0_archive_required")
    missing = [name for name in PAYLOADS if not (archive / name).is_file()]
    if missing:
        raise FileNotFoundError("archived_payloads_missing:" + ",".join(missing))
    if output in {archive / name for name in PAYLOADS} or output.is_relative_to(archive):
        raise ValueError("reporting_output_must_not_modify_original_archive")
    if not output.parent.is_dir():
        raise FileNotFoundError("reporting_output_parent_required")

    wall, cpu = time.perf_counter(), time.process_time()
    saved, sources = {}, {}
    reads, read_bytes = 0, 0
    for name in PAYLOADS:
        data = (archive / name).read_bytes()  # Exactly one read per listed payload.
        reads += 1
        read_bytes += len(data)
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("dictionary_payload_required:" + name)
        saved[name] = value
        sources[name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    run, metrics = saved["raw/run.json"], saved["raw/metrics.json"]
    execution, manifest = saved["execution.json"], saved["manifest.json"]
    if run.get("experiment_id") != "FR0":
        raise ValueError("FR0_run_identity_required")
    if type(execution.get("returncode")) is not int:
        raise ValueError("finished_first_execution_record_required")
    if manifest.get("status") != "archived":
        raise ValueError("finished_root_archive_manifest_required")

    receipt = {
        "archive": str(archive), "saved": saved, "source_files": sources,
        "reads": reads, "read_bytes": read_bytes,
        "wall_seconds": time.perf_counter() - wall,
        "cpu_seconds": time.process_time() - cpu,
        "timing_excludes": "summary_serialization_write_and_stdout",
        "metric_recalculations": 0, "raw_trajectory_reads": 0,
        "model_fit_physics_calls": 0, "automatic_retry": False,
    }
    encoded = (json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with output.open("xb") as stream:
        stream.write(encoded)

    trial = run.get("trial", {})
    windows = [selected(window, (
        "target", "observed_count", "planned_count", "available",
        "mae_axis_rad", "threshold_rad", "passed_axis",
    )) for window in metrics.get("windows", [])]
    contacts = {}
    for phase, values in metrics.get("phase_effort_and_contacts", {}).items():
        contacts[phase] = selected(values, (
            "confirmed_substeps", "observed_contact_endpoints",
            "missing_contact_endpoint_substeps", "actual_effort_complete",
        ))
        contacts[phase]["classes"] = {
            category: selected(value, (
                "positive_contact_endpoint_count", "positive_pair_event_count",
                "maximum_endpoint_normal_force_n",
                "full_positive_contact_count_unknown",
            )) for category, value in values.get("classes", {}).items()
        }
    compact = {
        "summary": str(output), "summary_write_bytes": len(encoded),
        "reads": reads, "read_bytes": read_bytes,
        "status": run.get("status"), "execution_returncode": execution.get("returncode"),
        "complete": trial.get("complete"), "stop": trial.get("stop"),
        "failure": trial.get("failure"),
        "engineering_qualification_passed": metrics.get("engineering_qualification_passed"),
        "metadata_stable": metrics.get("metadata_stable"),
        "windows": windows, "contacts": contacts,
        "left_arm_contact_checks": metrics.get("left_arm_contact_checks"),
        "cost": selected(run.get("cost", {}), (
            "control_call_attempts", "control_call_returns", "control_call_exceptions",
            "confirmed_physics_substeps", "captured_native_endpoints",
            "captured_complete_endpoints", "pd_request_returns",
            "audit_contact_snapshot_returns", "audit_contact_pair_inspections",
            "audit_contact_force_query_returns", "model_calls", "fit_calls",
            "RLS_updates", "MPC_decisions", "wall_seconds", "cpu_seconds",
        )),
        "metric_recalculations": 0, "raw_trajectory_reads": 0,
        "model_fit_physics_calls": 0,
    }
    print(json.dumps(compact, ensure_ascii=False, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
