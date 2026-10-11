"""Independent hinge-feature arithmetic and corruption checks."""
from fractions import Fraction
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


AUDIT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_local_learning_v2.py"
spec = importlib.util.spec_from_file_location("independent_local_learning_audit", AUDIT_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_rls_replay_matches_exact_fraction_update():
    theta = [1., 0., .02, 0., 0.]
    covariance = [[100. if i == j else 0. for j in range(5)] for i in range(5)]
    features = [.5, .125, .5, .25, 1.]
    label = .625
    actual_theta, actual_covariance = module.rls_replay(theta, covariance, features, label)
    x = [Fraction(1, 2), Fraction(1, 8), Fraction(1, 2), Fraction(1, 4), Fraction(1)]
    denominator = 1 + 100 * sum(value * value for value in x)
    gains = [100 * value / denominator for value in x]
    residual = Fraction(5, 8) - Fraction(1, 2) - Fraction(1, 50) * Fraction(1, 2)
    exact_theta = [Fraction(1), Fraction(0), Fraction(1, 50), Fraction(0), Fraction(0)]
    for i in range(5):
        assert actual_theta[i] == pytest.approx(float(exact_theta[i] + gains[i] * residual), abs=1e-14)
        for j in range(5):
            expected = (100 if i == j else 0) - gains[i] * 100 * x[j]
            assert actual_covariance[i][j] == pytest.approx(float(expected), abs=1e-12)


def test_prediction_uses_current_requested_torque_and_reference():
    assert module.predict([1., 2., 3., 4., 5.], .2, .3, .4, .5) == pytest.approx([.3 + .02 * 8.1, 8.1])


def test_fingerprint_detects_coefficients_or_covariance_corruption():
    covariance = [[100. if i == j else 0. for j in range(5)] for i in range(5)]
    initial = module.model_record(.1, module.INITIAL.copy(), covariance)
    first = module.digest(initial)
    initial["coefficients"][2] += .001
    assert module.digest(initial) != first
    initial["coefficients"][2] -= .001
    initial["covariance"][0][0] += .001
    assert module.digest(initial) != first


def test_scalar_audit_rejects_wrong_features_and_nonfinite():
    checks = module.Checks()
    checks.compare([.1, .2, .3, .05, 1.], [.1, .2, .5, .05, 1.], "causal_features")
    checks.near(float("nan"), 0., "nonfinite")
    assert checks.failed == 2


def test_mpc_replay_has_zero_tie_and_no_hidden_simulation():
    result = module.replay_mpc([1., 0., 0., 0., 0.], 0., 0., 0., 0., 0., [-1., 1.])
    assert result["torque"] == 0.
    assert result["feasible_candidates"] == 9
    assert result["mathematical_prediction_calls"] == 135
    assert result["fallback"] is False


def test_mpc_replay_reports_all_infeasible_zero_fallback():
    result = module.replay_mpc([1., 0., 0., 0., 0.], 0., .5, 0., .04, 0., [-1., 1.])
    assert result["fallback"] is True
    assert result["torque"] == 0.
    assert result["feasible_candidates"] == 0
    assert result["mathematical_prediction_calls"] == 9


def heldout_fixture(learned_prediction=.7, learned_tracking=.7):
    rows = []
    for seed in (10, 11, 12):
        rows.append({"seed": seed, "complete": True, "evaluations": {
            "prediction": {"velocity_prediction_rmse": {"frozen": 1., "learned": learned_prediction}},
            "frozen_mpc": {"tracking_rmse_rad": 1.},
            "learned_mpc": {"tracking_rmse_rad": learned_tracking},
            "fixed_pd": {"tracking_rmse_rad": .2},
        }})
    return [{"split": "holdout", "seeds": rows}]


def test_scientific_gate_passes_relative_contribution_with_stronger_pd():
    result = module.scientific_gate(heldout_fixture())
    assert result["passed"] is True
    assert result["per_seed"][0]["tracking_pd"] < result["per_seed"][0]["tracking_learned"]


def test_scientific_negative_result_does_not_create_audit_violations():
    checks = module.Checks()
    gate = module.scientific_gate(heldout_fixture(learned_prediction=.9))
    assert gate["evaluated"] is True and gate["passed"] is False
    assert checks.failed == 0


def test_scientific_gate_rejects_one_unimproved_seed_despite_good_mean():
    fixtures = heldout_fixture(learned_tracking=.2)
    fixtures[0]["seeds"][2]["evaluations"]["learned_mpc"]["tracking_rmse_rad"] = 1.1
    gate = module.scientific_gate(fixtures)
    assert gate["tracking_mean_improvement"] > .2
    assert gate["passed"] is False


def test_scientific_gate_requires_all_predeclared_seeds_and_complete_runs():
    fixtures = heldout_fixture()
    fixtures[0]["seeds"][1]["complete"] = False
    assert module.scientific_gate(fixtures)["passed"] is False
    fixtures[0]["seeds"].pop()
    assert module.scientific_gate(fixtures)["passed"] is False


def test_output_guard_rejects_inside_archive_and_existing_output(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    with pytest.raises(ValueError, match="outside"):
        module.validate_output_path(archive / "audit.json", [archive])
    output = tmp_path / "audit.json"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(ValueError, match="overwrite"):
        module.validate_output_path(output, [archive])
    assert output.read_text(encoding="utf-8") == "existing"


def test_cli_rejects_input_mutation_before_reading_archive(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    output = archive / "audit.json"
    result = subprocess.run([sys.executable, str(AUDIT_PATH), str(archive), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 2
    assert not output.exists()


def test_cli_rejects_existing_output_before_reading_archive(tmp_path):
    output = tmp_path / "audit.json"
    output.write_text("preserved", encoding="utf-8")
    result = subprocess.run([sys.executable, str(AUDIT_PATH), str(tmp_path / "missing_archive"), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 2
    assert output.read_text(encoding="utf-8") == "preserved"


@pytest.mark.parametrize("torque,expected", [(0., 0.), (.125, 0.), (.25, 0.), (-.25, 0.), (.375, .125), (-.375, -.125), (.5, .25), (-.5, -.25)])
def test_signed_hinge_has_frozen_threshold(torque, expected):
    assert module.hinge(torque) == expected


def test_prior_still_has_original_nominal_response():
    for torque in (-.5, -.375, -.25, -.125, 0., .125, .25, .375, .5):
        qnext, vnext = module.predict(module.INITIAL, .1, .15, .2, torque)
        assert vnext == pytest.approx(.2 + .02 * torque, abs=1e-14)
        assert qnext == pytest.approx(.15 + .02 * vnext, abs=1e-14)


def test_bad_threshold_is_rejected_even_with_recomputed_hash():
    covariance = [[100. if i == j else 0. for j in range(5)] for i in range(5)]
    expected = module.model_record(.1, module.INITIAL.copy(), covariance)
    corrupted = {**expected, "hinge_threshold_nm": .3}
    corrupted["parameter_fingerprint"] = module.digest(corrupted)
    checks = module.Checks()
    checks.compare(corrupted, expected, "fixed_hinge_structure")
    assert checks.failed == 1


def test_bad_calibration_dose_order_is_rejected():
    actual = module.CALIBRATION_AMPLITUDES.copy()
    actual[0], actual[1] = actual[1], actual[0]
    checks = module.Checks()
    checks.compare(actual, module.CALIBRATION_AMPLITUDES, "predeclared_dose_order")
    assert checks.failed == 2
