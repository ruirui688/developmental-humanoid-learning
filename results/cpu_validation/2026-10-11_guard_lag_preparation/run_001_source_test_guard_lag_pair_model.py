"""Small fixed artificial checks only. No raw data, fit bank or physics.

Run directly, rather than the old test/collector matrices. Each run keeps a
numbered source copy, text result and exact mathematical-call ledger.
"""
from __future__ import annotations

from collections import Counter
import dis
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import time
import unittest

import numpy as np

from developmental_physics.guard_coupled_pair_model import GuardCoupledPairBodyModel
from developmental_physics.local_pair_model import PairPredictionError, PairUpdateError, _parameter_state
from guard_lag_pair_model import FEATURE_NAMES, GuardLagPairBodyModel


QREF = (.1, -.0005)
RANGES = ((-1., 1.), (0., 2.3))
INPUT = (QREF, (.1, .2), (.375, -.5), (.3, -.1), (.04, .23))
LEDGER = []


def manual_features(q, v, u, previous_v):
    """Independent scalar guard, hinge and history arithmetic."""
    guarded = []
    for i, (lower, upper) in enumerate(RANGES):
        command = min(.5, max(-.5, u[i]))
        if (q[i] <= lower+.03 and command < 0.) or (q[i] >= upper-.03 and command > 0.):
            command = 0.
        guarded.append(command)
    hinge = [math.copysign(max(abs(command)-.25, 0.), command) for command in guarded]
    return [*v, q[0]-QREF[0], q[1]-QREF[1], *guarded, *hinge, 1.,
            v[0]-previous_v[0], v[1]-previous_v[1]]


class ArtificialChecks(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.models = 0
        LEDGER.append({"test": self.id(), "events": self.events})

    def watch(self, body, label="candidate11"):
        """Caller instrumentation, with no counters/history added to helper."""
        self.models += 1
        label = f"{label}:{self.models}"
        for method, kind in (("_features", "features"), ("_predict_state", "pair_prediction"),
                             ("_predict_output", "scalar_prediction"), ("_propose_update", "rls_proposal"),
                             ("update", "update_call")):
            original = getattr(body, method)
            def wrapped(*args, _original=original, _kind=kind, **kwargs):
                event = {"model": label, "kind": _kind, "outcome": "attempted"}
                if _kind in ("scalar_prediction", "rls_proposal"):
                    event["output_index"] = args[0]
                before = body.update_count if _kind == "update_call" else None
                self.events.append(event)
                try:
                    answer = _original(*args, **kwargs)
                    event["outcome"] = "success"
                    return answer
                except BaseException as exc:
                    event["outcome"] = "failed"
                    event["exception_type"] = type(exc).__name__
                    raise
                finally:
                    if _kind == "update_call":
                        event["committed_vector_updates"] = body.update_count-before
                        event["committed_scalar_updates"] = 2*(body.update_count-before)
            setattr(body, method, wrapped)
        return body

    def body(self, **kwargs):
        return self.watch(GuardLagPairBodyModel(QREF, public_joint_ranges=RANGES, **kwargs))

    def test_cold_prior_and_explicit_history_feature_order(self):
        body = self.body()
        expected = np.zeros((2, 11))
        expected[0, 0] = expected[1, 1] = 1.
        expected[0, 4] = expected[1, 5] = .02
        np.testing.assert_array_equal(body.coefficients, expected)
        np.testing.assert_array_equal(body.covariance, np.repeat((100.*np.eye(11))[None], 2, axis=0))
        positions, features = body._features(INPUT[0], INPUT[1], INPUT[2], INPUT[4])
        self.assertEqual(positions, QREF)
        np.testing.assert_array_equal(features, [manual_features(INPUT[0], INPUT[1], INPUT[2], INPUT[4])]*2)
        self.assertEqual(FEATURE_NAMES[-2:], ("v0-previous_v0", "v1-previous_v1"))
        self.assertEqual(body.snapshot()["forgetting_factor"], 1.)
        self.assertEqual(body.snapshot()["dt_seconds"], .02)
        self.assertEqual(body.snapshot()["integration"], "endpoint_euler")

    def test_zero_lag_matches_same_coefficients_in_old9_to_machine_precision(self):
        body = self.body(trainable=False)
        base = self.watch(GuardCoupledPairBodyModel(QREF, public_joint_ranges=RANGES,
                                                  trainable=False), "old9")
        # Explicit fixed coefficients, not learned from a dataset.
        coefficients = np.asarray([[.82, .18, -.07, .09, .22, -.13, .06, -.04, .01],
                                   [-.16, .87, .11, -.08, -.19, .24, .03, .07, -.015]])
        base._state = _parameter_state(coefficients.copy(), base.covariance, 0)
        body._state = _parameter_state(np.column_stack((coefficients, np.zeros((2, 2)))), body.covariance, 0)
        rows = [
            (QREF, (.1, .2), (.375, -.5), (.04, .23)),
            ((-.97, .03), (.01, -.02), (-.5, -.5), (-.02, .01)),
            ((.97, 2.27), (-.01, .02), (.5, .5), (.02, -.01)),
            ((0., 1.), (.1, -.1), (2., -2.), (-.1, .2)),
            ((-1.01, -.0005), (-.1, .2), (.125, -.125), (.1, .1)),
            ((0., .2), (0., 0.), (0., -0.), (.1, -.1)),
        ]
        maximum_difference = 0.
        for q, v, u, previous_v in rows:
            actual = np.asarray(body.predict(q, v, u, previous_v))
            reference = np.asarray(base.predict(q, v, u))
            maximum_difference = max(maximum_difference, float(np.max(np.abs(actual-reference))))
            np.testing.assert_allclose(actual, reference, rtol=1e-12, atol=1e-14)
        LEDGER[-1]["zero_lag_maximum_absolute_difference"] = maximum_difference

    def test_one_rls_transition_matches_independent_scalar_hand_calculation(self):
        body = self.body()
        q, v, u, labels, previous_v = INPUT
        feature = manual_features(q, v, u, previous_v)
        initial = body.coefficients.tolist()
        denominator = 1.+100.*sum(x*x for x in feature)
        expected_theta, expected_covariance = [], []
        for head in range(2):
            prediction = sum(a*b for a, b in zip(initial[head], feature))
            residual = labels[head]-prediction
            expected_theta.append([initial[head][j]+100.*feature[j]*residual/denominator for j in range(11)])
            expected_covariance.append([
                [100.*(i == j)-10000.*feature[i]*feature[j]/denominator for j in range(11)]
                for i in range(11)])
        record = body.update(*INPUT, transition_id="artificial:one-hand-transition")
        np.testing.assert_allclose(body.coefficients, expected_theta, rtol=0., atol=1e-14)
        np.testing.assert_allclose(body.covariance, expected_covariance, rtol=0., atol=3e-14)
        self.assertEqual(record["features_per_output"], [feature]*2)
        self.assertEqual(record["committed_scalar_updates"], 2)
        self.assertEqual((body.update_count, body.scalar_update_count), (1, 2))
        self.assertTrue(all(row["committed"] for row in record["output_records"]))

    def test_history_is_required_validated_and_not_internal_state(self):
        body = self.body()
        before = body.snapshot()
        with self.assertRaises(TypeError):
            body.predict(*INPUT[:3])
        with self.assertRaises(TypeError):
            body.update(*INPUT[:4], transition_id="artificial:missing-history")
        for bad in (None, (0.,), (True, 0.), (np.nan, 0.), ("0", 0.)):
            with self.assertRaises(PairPredictionError) as caught:
                body.predict(*INPUT[:3], bad)
            self.assertEqual(caught.exception.scalar_prediction_attempts, 0)
            with self.assertRaises(ValueError):
                body.update(*INPUT[:4], bad, transition_id="artificial:invalid-history")
        self.assertEqual(body.snapshot(), before)
        self.assertNotIn("_previous_v", vars(body))
        self.assertEqual(list(inspect.signature(GuardLagPairBodyModel.predict).parameters),
                         ["self", "q", "v", "u", "previous_v"])
        for forbidden in ("actual_torque", "next_q", "environment", "hidden_gain"):
            with self.assertRaises(TypeError):
                body.predict(*INPUT[:3], INPUT[4], **{forbidden: object()})

    def test_second_head_rejection_or_io_failure_publishes_nothing(self):
        for fatal in (False, True):
            body = GuardLagPairBodyModel(QREF, public_joint_ranges=RANGES)
            original = body._propose_update
            def rejected(index, *args, _original=original):
                if index == 1:
                    raise OSError("artificial head1 IO") if fatal else ValueError("artificial head1 rejection")
                return _original(index, *args)
            body._propose_update = rejected
            self.watch(body)
            before = body.snapshot()
            with self.assertRaises(OSError if fatal else PairUpdateError) as caught:
                body.update(*INPUT, transition_id="artificial:head1-failure")
            exc = caught.exception
            ledger = exc.pair_update_accounting if fatal else exc.to_dict()
            self.assertEqual(body.snapshot(), before)
            self.assertEqual(ledger["committed_scalar_updates"], 0)
            self.assertEqual(len(ledger["proposed_outputs"]), 1)
            self.assertFalse(ledger["proposed_outputs"][0]["committed"])
            self.assertEqual(ledger["snapshot_after_attempt"], before)

    def test_single_publication_interrupt_is_wholly_old_or_new(self):
        instructions = list(dis.get_instructions(GuardLagPairBodyModel.update))
        stores = [i for i, item in enumerate(instructions)
                  if item.opname == "STORE_ATTR" and item.argval == "_state"]
        self.assertEqual(len(stores), 1)
        for boundary in ("before", "after"):
            body, expected = self.body(), self.body()
            if boundary == "after":
                expected.update(*INPUT, transition_id="artificial:expected-committed")
            offset = instructions[stores[0]+(boundary == "after")].offset
            def trace(frame, event, arg):
                if frame.f_code is GuardLagPairBodyModel.update.__code__ and frame.f_locals.get("self") is body:
                    frame.f_trace_opcodes = True
                    if event == "opcode" and frame.f_lasti == offset:
                        raise KeyboardInterrupt(f"artificial {boundary} commit")
                return trace
            prior_trace = sys.gettrace()
            try:
                sys.settrace(trace)
                with self.assertRaises(KeyboardInterrupt) as caught:
                    body.update(*INPUT, transition_id="artificial:commit-interrupt")
            finally:
                sys.settrace(prior_trace)
            self.assertEqual(body.snapshot(), expected.snapshot())
            ledger = caught.exception.pair_update_accounting
            self.assertEqual(ledger["committed_scalar_updates"], 2 if boundary == "after" else 0)
            self.assertEqual(ledger["snapshot_after_attempt"], body.snapshot())

    def test_frozen_clone_copies_complete_parameter_state_without_sharing(self):
        body = self.body()
        body.update(*INPUT, transition_id="artificial:clone-source")
        clone = self.watch(body.clone_frozen())
        clone_before = clone.snapshot()
        self.assertFalse(clone.trainable)
        self.assertEqual(clone.parameter_fingerprint(), body.parameter_fingerprint())
        self.assertEqual((clone.update_count, clone.scalar_update_count), (1, 2))
        for name in ("theta", "covariance"):
            original_array, cloned_array = getattr(body._state, name), getattr(clone._state, name)
            self.assertFalse(np.shares_memory(original_array, cloned_array))
            self.assertFalse(cloned_array.flags.writeable)
        self.assertFalse(np.shares_memory(body._initial_theta, clone._initial_theta))
        self.assertIsNot(body.public_guard, clone.public_guard)
        with self.assertRaises(RuntimeError):
            clone.update(*INPUT, transition_id="artificial:frozen-rejection")
        body.update(QREF, (.2, .1), (.5, .5), (.1, .3), (.1, .2), transition_id="artificial:later-source")
        clone.coefficients[:] = 999.
        clone.covariance[:] = 999.
        self.assertEqual(clone.snapshot(), clone_before)

    def test_predictions_are_pure_and_rollout_history_advances_old_current_v(self):
        body = self.body(trainable=False)
        theta = body.coefficients
        theta[0, 9], theta[0, 10] = .2, -.1
        theta[1, 9], theta[1, 10] = .05, .3
        body._state = _parameter_state(theta, body.covariance, 0)
        before = body.snapshot()
        q, v, u, _, previous_v = INPUT
        first = body.predict(q, v, u, previous_v)
        # An unrelated history call cannot alter an identical query later.
        other = body.predict(q, v, u, (-.2, .7))
        self.assertNotEqual(first, other)
        self.assertEqual(first, body.predict(q, v, u, previous_v))
        for _ in range(3):
            old_v = v
            new_q, new_v = body.predict(q, v, u, previous_v)
            x = manual_features(q, v, u, previous_v)
            manual_v = tuple(sum(a*b for a, b in zip(head, x)) for head in theta.tolist())
            np.testing.assert_allclose(new_v, manual_v, rtol=1e-14, atol=1e-15)
            np.testing.assert_allclose(new_q, [q[i]+.02*manual_v[i] for i in range(2)], rtol=1e-14, atol=1e-15)
            q, v, previous_v = new_q, new_v, old_v
        self.assertEqual(body.snapshot(), before)


def totals(events):
    counts = Counter()
    for event in events:
        counts[event["kind"]+"_attempts"] += 1
        counts[event["kind"]+"_"+event["outcome"]] += 1
        if event["kind"] == "update_call":
            counts["committed_vector_updates"] += event["committed_vector_updates"]
            counts["committed_scalar_updates"] += event["committed_scalar_updates"]
    return dict(sorted(counts.items()))


def main():
    directory = Path(__file__).resolve().parent
    number = 1
    while (directory/f"run_{number:03d}_math.json").exists():
        number += 1
    prefix = f"run_{number:03d}"
    hashes = {}
    for filename in ("guard_lag_pair_model.py", Path(__file__).name):
        source = directory/filename
        copied = directory/f"{prefix}_source_{filename}"
        shutil.copyfile(source, copied)
        hashes[filename] = hashlib.sha256(source.read_bytes()).hexdigest()
    start_wall, start_cpu, start_times = time.perf_counter(), time.process_time(), os.times()
    with (directory/f"{prefix}_math.log").open("x", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ArtificialChecks))
    elapsed = {"wall_seconds": time.perf_counter()-start_wall, "process_cpu_seconds": time.process_time()-start_cpu,
               "user_cpu_seconds": os.times().user-start_times.user,
               "system_cpu_seconds": os.times().system-start_times.system}
    per_test = [{**item, "math_totals": totals(item["events"])} for item in LEDGER]
    report = {
        "schema": "c4_lag_model_artificial_math_v1", "run": prefix,
        "source_sha256": hashes, "environment": {"python": sys.version, "executable": sys.executable,
                                                    "platform": platform.platform(), "numpy": np.__version__},
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "success": result.wasSuccessful(), "elapsed": elapsed,
        "math_totals": totals([event for item in LEDGER for event in item["events"]]), "per_test": per_test,
        "research_cost": {"physics_control_calls": 0, "physics_substeps": 0, "real_raw_data_reads": 0,
                          "real_online_scalar_updates": 0, "real_offline_scalar_updates": 0,
                          "synthetic_updates_excluded_from_formal_research_ledger": True},
        "scope": "handcrafted mathematical checks only; no dataset fit, collector, MPC search or scientific adoption gate",
        "mujoco_loaded": "mujoco" in sys.modules,
    }
    with (directory/f"{prefix}_math.json").open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps({key: report[key] for key in ("run", "tests_run", "failures", "errors", "success", "elapsed", "math_totals", "mujoco_loaded")}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
