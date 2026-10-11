import numpy as np
import pytest

from developmental_physics.local_integration import FrozenIntegrationModel
from developmental_physics.local_model import HingeBodyModel, FixedLocalMPC


def test_views_preserve_velocity_parameters_and_expose_distinct_position_rule():
    model = HingeBodyModel(.1)
    model.update(.1, .02, .25, .03)
    end = FrozenIntegrationModel(model, "endpoint_euler")
    trap = FrozenIntegrationModel(model, "trapezoid")
    assert end.parameter_fingerprint() == trap.parameter_fingerprint() == model.parameter_fingerprint()
    assert end.integration_fingerprint() != trap.integration_fingerprint()
    assert np.array_equal(end.coefficients, trap.coefficients)
    assert np.array_equal(end.covariance, trap.covariance)
    assert end.update_count == trap.update_count == 1
    for q, v, u in ((.1, .2, .5), (.02, -.04, -.375), (.05, .0, .0)):
        qe, ve = end.predict(q, v, u)
        qt, vt = trap.predict(q, v, u)
        assert ve == vt
        assert (qe, ve) == model.predict(q, v, u)
        assert qt == q + .02*(.5*v + .5*vt)
    with pytest.raises(RuntimeError, match="cannot update"):
        trap.update(.1, 0., .1, .01)
    clone = trap.clone_frozen()
    assert clone.snapshot() == trap.snapshot()
    # Later fitting the source cannot silently change a frozen evaluation view.
    before = trap.snapshot()
    model.update(.1, .01, -.5, -.04)
    assert trap.snapshot() == before and trap.parameter_fingerprint() != model.parameter_fingerprint()


def test_view_works_with_unchanged_mpc_and_does_not_query_physics():
    model = FrozenIntegrationModel(HingeBodyModel(0.), "trapezoid")
    planner = FixedLocalMPC(model, [-1., 1.])
    decision = planner.select(0., 0., .04)
    assert abs(decision.torque) <= .5 and not decision.fallback
    assert decision.mathematical_prediction_calls == 9*15
    assert planner.spec()["physical_queries"] == 0
    assert len(decision.predicted_q) == len(decision.predicted_v) == 15


@pytest.mark.parametrize("q,v,u", [(True, 0., 0.), (0., float("nan"), 0.), (0., 0., float("inf"))])
def test_native_input_validation_is_preserved(q, v, u):
    model = FrozenIntegrationModel(HingeBodyModel(0.), "trapezoid")
    with pytest.raises(ValueError):
        model.predict(q, v, u)


def test_invalid_mode_is_not_silently_treated_as_euler():
    with pytest.raises(ValueError):
        FrozenIntegrationModel(HingeBodyModel(0.), "unknown")


def test_euler_adapter_preserves_original_planner_choices_and_paths_exactly():
    model=HingeBodyModel(.1)
    for q,v,u,next_v in ((.1,0.,.25,.01),(.101,.01,.5,.03),(.102,.03,-.375,-.01)):
        model.update(q,v,u,next_v)
    original=FixedLocalMPC(model.clone_frozen(),[-1.,1.])
    adapted=FixedLocalMPC(FrozenIntegrationModel(model,"endpoint_euler"),[-1.,1.])
    for q,v,target,previous in ((.1,0.,.06,0.),(.08,-.02,.02,-.5),(.12,.04,.06,.125)):
        assert original.select(q,v,target,previous_torque=previous) == adapted.select(q,v,target,previous_torque=previous)


def test_rewrapping_cannot_silently_retain_the_previous_integration_rule():
    base=HingeBodyModel(0.)
    trap=FrozenIntegrationModel(base,"trapezoid")
    endpoint=FrozenIntegrationModel(trap,"endpoint_euler")
    assert endpoint.predict(.1,.2,.5) == base.predict(.1,.2,.5)
    assert endpoint.integration == "endpoint_euler" and not endpoint.trainable
