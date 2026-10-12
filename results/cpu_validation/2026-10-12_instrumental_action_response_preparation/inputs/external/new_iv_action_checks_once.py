"""Five first synthetic IV1 checks; no saved raw or physical backend is used."""
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback

import numpy as np


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
                runner = repo / "scripts/develop_instrumental_action_response.py"
                model_path = repo / "src/developmental_physics/instrumental_action_model.py"
                for path in (runner, model_path, Path(__file__).resolve()):
                    cost["source_file_reads"] += 1
                    blob = path.read_bytes()
                    cost["source_bytes_read"] += len(blob)
                    identities[str(path)] = {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
                if identities[str(runner)]["sha256"] != args.runner_sha256 or identities[str(model_path)]["sha256"] != args.model_sha256:
                    raise ValueError("reviewed_IV1_source_identity_differs")
                def load(name, path):
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    return module
                body = load("iv1_synthetic_body", model_path)
                source = load("iv1_synthetic_source", runner)
                def check(name, condition, detail):
                    checks.append({"name": name, "passed": bool(condition), "detail": source.safe(detail)})
                    if not condition:
                        raise AssertionError(name)
                theta = np.zeros((2, 9))
                theta[0, 0], theta[1, 1], theta[:, 8] = .8, .9, (.03, -.04)
                model = body.InstrumentalActionBodyModel((0., 0.), ((-1., 1.), (-1., 1.)), theta)
                true_action = np.asarray([[.03, -.05, .004, .007], [-.06, .11, -.008, .009]])
                moment = body.ActionIVMoments(model, cost)
                for group, base in enumerate(((-.3, -.3), (-.1, -.1), (.1, .1), (.3, .3))):
                    q, v = np.asarray((.02*group, -.01*group)), np.asarray((.1, -.2))
                    latent = np.asarray((.17*(group+1), -.23*(group+1)))
                    for sign in body.SIGNS:
                        dither = .125*np.asarray(sign)
                        x, _ = body.action_features(q, np.asarray(base)+dither, model.ranges, cost)
                        label = model.state_term(q, v, cost)+latent+true_action@x
                        moment.add(q, v, base, dither, label)
                corrected = moment.fit_once()
                directed = body.ActionIVMoments(model, cost)
                directed.M = np.asarray([[2., 1., 0., 0.], [0., 3., 1., 0.], [.1, 0., 4., .5], [0., 0., 0., 5.]])
                directed.Y, directed.samples = directed.M@true_action.T, 4
                directed_M_before = directed.M.tobytes()
                directed_corrected = directed.fit_once()
                check("conditional_centered_IV_recovers_action_with_hidden_state_drift",
                    np.allclose(corrected.theta[:, 4:8], true_action, rtol=0., atol=1e-12)
                    and np.allclose(directed_corrected.theta[:, 4:8], true_action, rtol=0., atol=1e-12)
                    and directed.M.tobytes() == directed_M_before and moment.fit_record["rank"] == 4 and moment.samples == 16,
                    {"moment": moment.record(), "non_symmetric_equation": directed.record(), "recovered": corrected.theta[:, 4:8]})
                check("exactly_eight_action_coefficients_replace_frozen_state",
                    corrected.theta[:, body.NONACTION].tobytes() == model.theta[:, body.NONACTION].tobytes()
                    and model.theta.tobytes() == theta.tobytes() and not corrected.theta.flags.writeable,
                    {"original": model.record(), "corrected": corrected.record()})
                rows = [body.centered_instrument((-.97, 0.), (-.1, .1), .125*np.asarray(sign), model.ranges, cost) for sign in body.SIGNS]
                check("guard_equality_conditions_all_four_known_legal_requests",
                    np.allclose(np.sum([row["instrument4"] for row in rows], axis=0), np.zeros(4), rtol=0., atol=1e-16)
                    and rows[0]["blocked2"][0] and not rows[2]["blocked2"][0]
                    and np.isclose(rows[0]["action4"][0], 0.) and np.isclose(rows[2]["action4"][0], .025), rows)
                deficient = body.ActionIVMoments(model, cost)
                for sign in body.SIGNS:
                    deficient.add((-1., -1.), (0., 0.), (-.375, -.375), .125*np.asarray(sign), (0., 0.))
                rank_rejected, retry_rejected = False, False
                try:
                    deficient.fit_once()
                except ValueError:
                    rank_rejected = deficient.fit_record["rank"] != 4
                try:
                    deficient.fit_once()
                except ValueError:
                    retry_rejected = True
                check("rank_deficiency_is_terminal_without_rank_completion_or_retry", rank_rejected and retry_rejected, deficient.record())
                rejected = []
                for call in (
                    lambda: body.action_features((0., 0.), (.50001, 0.), model.ranges),
                    lambda: body.centered_instrument((0., 0.), (.376, 0.), (.125, -.125), model.ranges),
                    lambda: body.centered_instrument((0., 0.), (0., 0.), (.1, -.125), model.ranges),
                    lambda: model.predict((float("nan"), 0.), (0., 0.), (0., 0.)),
                    lambda: model.predict((0., 0.), (0., 0.), (0., 0.), future_actual_torque=(0., 0.))):
                    try:
                        call()
                        rejected.append(False)
                    except (ValueError, TypeError):
                        rejected.append(True)
                base = source.pd(np.zeros(2), np.zeros(2), np.asarray((.1, -.1)), .375)
                legal = all(np.all(np.abs(base+.125*np.asarray(sign)) <= .5) for sign in body.SIGNS)
                check("only_native_current_inputs_and_fixed_legal_source_dose", all(rejected) and legal
                    and np.array_equal(source.prediction_pulse(10), (.125, 0.))
                    and np.array_equal(source.prediction_pulse(90), (-.125, 0.)), {"rejected": rejected, "base": base})
            except BaseException as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                traceback.print_exc()
    cost["wall_seconds"], cost["cpu_seconds"] = time.perf_counter()-wall, time.process_time()-cpu
    report = {"status": "failed" if failure else "passed", "first_failure": failure, "checks": checks,
        "source_identities": identities, "synthetic_only_cost": dict(cost), "cost": dict(cost),
        "saved_raw_reads": 0, "environment_constructions": 0, "physics_calls": 0,
        "physical_native_labels": 0, "RLS_updates": 0, "unmeasured_import_IO": "unknown_not_zero"}
    (output / "checks.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "output": str(output)}))
    return 1 if failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
