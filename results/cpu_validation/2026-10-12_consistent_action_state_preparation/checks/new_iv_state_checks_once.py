"""Five first synthetic IV2 checks; no saved raw or physical backend is used."""
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np


def safe(value):
    if isinstance(value, dict):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return safe(value.tolist())
    if isinstance(value, np.generic):
        return safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return {"nonfinite_float": str(value)}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--runner-sha256", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    if output.exists() or output == repo or repo.is_relative_to(output):
        parser.error("existing_or_repository_containing_output_refused")
    output.mkdir(parents=True, exist_ok=False)
    cost, checks, identities, failure = Counter(), [], {}, None
    wall, cpu = time.perf_counter(), time.process_time()
    with (output / "first_stdout.log").open("x", encoding="utf-8") as stdout, (output / "first_stderr.log").open("x", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                runner = repo / "scripts/refit_instrumental_state.py"
                model_path = repo / "src/developmental_physics/consistent_action_state_model.py"
                action_path = repo / "src/developmental_physics/instrumental_action_model.py"
                package_path = repo / "src/developmental_physics/__init__.py"
                helper_path = repo / "scripts/develop_instrumental_action_response.py"
                for path in (runner, model_path, action_path, package_path, helper_path, Path(__file__).resolve()):
                    path = path.resolve()
                    cost["source_file_reads"] += 1
                    blob = path.read_bytes()
                    cost["source_bytes_read"] += len(blob)
                    identities[str(path)] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                if identities[str(runner)]["sha256"] != args.runner_sha256 or identities[str(model_path)]["sha256"] != args.model_sha256:
                    raise ValueError("reviewed_IV2_source_identity_differs")
                sys.path.insert(0, str(repo / "src"))
                body = importlib.import_module("developmental_physics.consistent_action_state_model")
                action = importlib.import_module("developmental_physics.instrumental_action_model")
                package = importlib.import_module("developmental_physics")
                if (Path(body.__file__).resolve() != model_path or Path(action.__file__).resolve() != action_path
                    or Path(package.__file__).resolve() != package_path):
                    raise ValueError("canonical_import_source_path_differs")
                spec = importlib.util.spec_from_file_location("iv2_first_synthetic_runner", runner)
                if spec is None or spec.loader is None:
                    raise ValueError("runner_file_spec_unavailable")
                source = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = source
                spec.loader.exec_module(source)
                if Path(source.__file__).resolve() != runner or Path(source.iv1.__file__).resolve() != helper_path:
                    raise ValueError("runner_import_source_path_differs")

                def check(name, condition, detail):
                    checks.append({"name": name, "passed": bool(condition), "detail": safe(detail)})
                    print(json.dumps({"check": name, "passed": bool(condition)}))
                    if not condition:
                        raise AssertionError(name)

                def rejects(call):
                    try:
                        call()
                    except ValueError as exc:
                        return {"rejected": True, "type": type(exc).__name__, "message": str(exc)}
                    return {"rejected": False}

                qref = np.asarray((.13, -.07))
                ranges = np.asarray(((-1., 1.), (-1., 1.)))
                theta = np.zeros((2, 9))
                theta[:, body.NONACTION] = np.asarray(((.7, -.02, .04, .01, -.03), (.03, .8, -.01, .05, .02)))
                fixed_action = np.asarray(((.03, -.05, .004, .007), (-.06, .11, -.008, .009)))
                theta[:, 4:8] = fixed_action
                model = body.InstrumentalActionBodyModel(qref, ranges, theta)
                initial_theta_bytes = model.theta.tobytes()
                initial_action_bytes = model.theta[:, 4:8].tobytes()
                true_state = np.asarray(((.91, -.06, -.04, .03, .021), (.05, .87, .02, -.09, -.014)))
                design = (
                    (0., 0., 0., 0.), (.2, 0., 0., 0.), (-.2, 0., 0., 0.),
                    (0., .2, 0., 0.), (0., -.2, 0., 0.), (0., 0., .08, 0.),
                    (0., 0., -.08, 0.), (0., 0., 0., .08), (0., 0., 0., -.08),
                )
                requests = ((-.375, .125), (.5, -.5), (.25, .375), (-.5, -.125),
                    (.125, .5), (.375, -.25), (0., -.375), (-.25, .25), (.5, .375))
                fit = body.StateConsistencyFit(model, cost)
                labels, action_terms = [], []
                for state, request in zip(design, requests):
                    v, q = np.asarray(state[:2]), qref + np.asarray(state[2:])
                    psi = np.asarray((*v, *(q-qref), 1.))
                    feature, _ = body.action_features(q, request, ranges, cost)
                    action_term = fixed_action @ feature
                    next_v = true_state @ psi + action_term
                    cost["synthetic_transition_pairs_created"] += 1
                    cost["synthetic_scalar_label_values_created"] += 2
                    cost["synthetic_fixture_action_matvecs"] += 1
                    cost["synthetic_fixture_state_matvecs"] += 1
                    labels.append(next_v.tolist())
                    action_terms.append(action_term.tolist())
                    fit.add(q, v, request, next_v)
                matched = fit.fit_once()
                check("full_rank5_native_state_fit_removes_fixed_action_nuisance",
                    fit.samples == len(design) and fit.fit_record["rank"] == 5
                    and np.allclose(matched.theta[:, body.NONACTION], true_state, rtol=0., atol=1e-12)
                    and np.any(np.asarray(action_terms) != 0.),
                    {"known_state_2x5": true_state, "native_labels2": labels,
                     "fixed_action_terms2": action_terms, "fit": fit.record()})
                check("eight_action_coefficients_byte_frozen_ten_state_coefficients_recovered",
                    matched.theta[:, 4:8].tobytes() == initial_action_bytes
                    and model.theta.tobytes() == initial_theta_bytes
                    and np.array_equal(matched.qref, qref) and np.array_equal(matched.ranges, ranges)
                    and not matched.theta.flags.writeable
                    and not matched.qref.flags.writeable and not matched.ranges.flags.writeable
                    and np.allclose(matched.theta[:, body.NONACTION], true_state, rtol=0., atol=1e-12)
                    and tuple(body.NONACTION) == (0, 1, 2, 3, 8),
                    {"initial": model.record(), "matched": matched.record(),
                     "action_coefficients": 8, "state_coefficients": 10})

                deficient = body.StateConsistencyFit(model, cost)
                for request in requests[:3]:
                    feature, _ = body.action_features(qref, request, ranges, cost)
                    next_v = true_state[:, 4] + fixed_action @ feature
                    cost["synthetic_transition_pairs_created"] += 1
                    cost["synthetic_scalar_label_values_created"] += 2
                    cost["synthetic_fixture_action_matvecs"] += 1
                    deficient.add(qref, (0., 0.), request, next_v)
                rank_rejection = rejects(deficient.fit_once)
                attempts_before_retry = cost["state_fit_attempts"]
                retry_rejection = rejects(deficient.fit_once)
                late_label_rejection = rejects(lambda: deficient.add(qref, (0., 0.), (0., 0.), (0., 0.)))
                check("rank_deficiency_is_terminal_without_completion_or_retry",
                    rank_rejection["rejected"] and deficient.fit_record is not None
                    and deficient.fit_record["rank"] != 5 and retry_rejection["rejected"]
                    and late_label_rejection["rejected"] and deficient.samples == 3
                    and cost["state_fit_attempts"] == attempts_before_retry,
                    {"rank_rejection": rank_rejection, "retry_rejection": retry_rejection,
                     "late_label_rejection": late_label_rejection, "fit": deficient.record()})

                def observation(q, v):
                    return {"joint_position": [*q, *([0.] * 6)], "joint_velocity": [*v, *([0.] * 6)]}

                def transition(index, q, v, next_q, next_v):
                    cost["synthetic_top_level_selection_fixtures_created"] += 1
                    return {"seed": 8101, "kind": "identification", "phase": "active",
                        "active_index": index, "control_index": 1000+index,
                        "trial_id": "s8101_identification", "stage": "A", "returned": True,
                        "confirmed_physics_substeps": 1, "diagnostics": {"executed_substeps": 1},
                        "observation_before": observation(q, v), "observation_after": observation(next_q, next_v),
                        "requested_torque8": [.25, -.375, *([0.] * 6)]}

                first = transition(0, (.1, -.2), (.01, -.03), (.1005, -.1997), (.02, .04))
                second = transition(1, (.1005, -.1997), (.02, .04), (.101, -.199), (.03, .05))
                ignored = [
                    {"paid_native_endpoint": deepcopy(first)},
                    {"IV_native_annotation": {"seed": 8101, "active_index": 0, "native_next_v2": [99., 99.]}},
                    {"annotation": deepcopy(first)},
                    {**deepcopy(first), "kind": "prediction", "observation_after": "excluded_eval_poison"},
                    {**deepcopy(first), "phase": "prefix", "active_index": -1,
                     "control_index": 999, "observation_before": "excluded_prefix_poison"},
                ]
                stream = body.NativeIdentificationStream(seeds=(8101,), active_count=2, cost=cost)
                exclusions = [stream.accept(row) is None for row in ignored]
                selected_first, selected_second = stream.accept(first), stream.accept(second)
                complete_counts = stream.finish()
                duplicate = body.NativeIdentificationStream(seeds=(8101,), active_count=2, cost=cost)
                duplicate.accept(first)
                duplicate_rejection = rejects(lambda: duplicate.accept(first))
                breaks = []
                for field in ("joint_position", "joint_velocity"):
                    broken = body.NativeIdentificationStream(seeds=(8101,), active_count=2, cost=cost)
                    broken.accept(first)
                    bad_row = deepcopy(second)
                    bad_row["observation_before"][field][0] += .001
                    breaks.append(rejects(lambda: broken.accept(bad_row)))
                missing = body.NativeIdentificationStream(seeds=(8101,), active_count=2, cost=cost)
                missing.accept(first)
                missing_rejection = rejects(missing.finish)
                incomplete_rejection = rejects(lambda: body.identification_transition({**deepcopy(first), "returned": False}))
                check("complete_top_level_identification_only_exact_continuity_no_duplicates",
                    all(exclusions) and complete_counts == {8101: 2}
                    and selected_first["seed"] == 8101 and selected_first["index"] == 0
                    and selected_second["index"] == 1
                    and selected_first["next_q"].tobytes() == selected_second["q"].tobytes()
                    and selected_first["next_v"].tobytes() == selected_second["v"].tobytes()
                    and np.array_equal(selected_first["request"], (.25, -.375))
                    and duplicate_rejection["rejected"] and all(item["rejected"] for item in breaks)
                    and missing_rejection["rejected"] and incomplete_rejection["rejected"],
                    {"excluded_nested_annotation_eval_prefix": exclusions, "complete_counts": complete_counts,
                     "first": selected_first, "second": selected_second,
                     "duplicate": duplicate_rejection, "state_breaks": breaks,
                     "missing": missing_rejection, "incomplete_top_level": incomplete_rejection})

                pulse_rows = []
                axes = ((1., 0.), (0., 1.), (1., 1.), (1., -1.), (1., 1.))
                amplitudes = (.125, .25, .375, .5, .375)
                for block, (axis, amplitude) in enumerate(zip(axes, amplitudes)):
                    for local_index, sign in ((10, 0.), (19, 0.), (29, 0.), (30, 1.), (39, 1.),
                        (40, 0.), (90, 0.), (99, 0.), (129, 0.), (130, -1.), (139, -1.), (140, 0.)):
                        index = 200*block+local_index
                        expected = sign*amplitude*np.asarray(axis)
                        actual = np.asarray(source.prediction_pulse(index))
                        cost["synthetic_prediction_pulse_calls"] += 1
                        pulse_rows.append({"index": index, "expected2": expected,
                            "actual2": actual, "matched": actual.shape == (2,) and np.array_equal(actual, expected)})
                check("new_prediction_pulse_slots3_and13_all_block_boundaries",
                    len(pulse_rows) == 60 and all(row["matched"] for row in pulse_rows), pulse_rows)
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    report = {"status": "failed" if failure else "passed", "first_failure": failure, "checks": checks,
        "source_identities": identities, "synthetic_only_cost": dict(cost), "cost": dict(cost),
        "cost_scope": "all_fit_and_saved_selection_counters_above_use_only_new_synthetic_fixtures",
        "saved_raw_reads": 0, "old_trace_or_prediction_reads": 0,
        "real_data_fit_attempts": 0, "real_data_scalar_label_uses": 0,
        "environment_constructions": 0, "physics_calls": 0, "physics_substeps": 0,
        "physical_native_labels": 0, "RLS_updates": 0,
        "timing_excludes": "final_JSON_encoding_and_checks_payload_write",
        "unmeasured_import_IO": "unknown_not_zero"}
    (output / "checks.json").write_text(json.dumps(safe(report), ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "output": str(output)}))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
