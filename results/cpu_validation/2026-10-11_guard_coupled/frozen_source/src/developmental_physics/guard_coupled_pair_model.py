"""Synthetic-stage public-guard coupled next-velocity model.

Only current native q/v, an already known requested two-axis command and
public joint ranges enter features. This is a control-start projection,
not the realized interval-average torque. No simulator, actual future
input, privileged state or scientific acceptance protocol is queried here.
The original atomic pair RLS and FixedPairMPC are reused unchanged.
"""
from __future__ import annotations

from developmental_physics.guard_pair_model import KnownAngleGuard
from developmental_physics.local_pair_model import PairBodyModel, _parameter_state


class GuardCoupledPairBodyModel(PairBodyModel):
    """Two nine-parameter heads with matching own-axis, zero-cross priors.

    Preserve the existing coupled_hinge9 GLOBAL column order, shared by
    both heads: [v0,v1,q0-qref0,q1-qref1,G0,G1,h(G0),h(G1),1].
    For head i, own columns are [i,2+i,4+i,6+i], and the complementary
    columns belong to the other axis. There is no prefilled coupling.
    """

    def __init__(self, qref, *, public_joint_ranges, dt=.02, trainable=True):
        self._guard = KnownAngleGuard(public_joint_ranges)
        super().__init__(qref, structure="coupled_hinge9", dt=dt, trainable=trainable)

    @property
    def input_basis(self):
        return "known_angle_guard"

    @property
    def public_guard(self):
        return self._guard

    def describe_input(self, q, u):
        projection = self.public_guard.project(q, u)
        return {
            **projection.to_dict(), "input_basis": self.input_basis,
            "model_feature_command_nm": projection.projected_start_nm,
        }

    def _features(self, q, v, u):
        projection = self.public_guard.project(q, u)
        return super()._features(projection.native_q_rad, v, projection.projected_start_nm)

    def _parameter_record(self, state=None):
        record = super()._parameter_record(state)
        row = ["v0", "v1", "q0-qref0", "q1-qref1",
               "start_G0(q0,u0)", "start_G1(q1,u1)",
               "h(start_G0(q0,u0))", "h(start_G1(q1,u1))", "1"]
        record["features_per_output"] = [row.copy(), row.copy()]
        record["feature_roles_per_output"] = [
            {"output_index": i, "own_columns": [i, 2+i, 4+i, 6+i],
             "cross_columns": [1-i, 3-i, 5-i, 7-i], "constant_column": 8}
            for i in range(2)
        ]
        record["input_mapping"] = {
            "basis": self.input_basis,
            "feature_command": "G(current q, original requested u) at control start",
            "public_guard": self.public_guard.spec(),
            "guard_used_by_model": True,
            "recompute": "same causal mapping on every RLS and mathematical prediction call",
        }
        record["model_definition"] = {
            "feature_order_source": "unchanged PairBodyModel coupled_hinge9 global column order",
            "rls_source": "unchanged PairBodyModel atomic two-head update",
            "guard_source": "KnownAngleGuard public control-start rule",
            "own_prior": "same [1,0,.02,0] as matching guard diagonal; constant zero",
            "cross_prior": "all four cross coefficients zero for each output",
            "parameter_count_per_output": 9,
            "matching_diagonal_parameter_count_per_output": 5,
            "physical_queries": 0,
        }
        return record

    def clone_frozen(self):
        state = self._state
        clone = GuardCoupledPairBodyModel(
            self.qref, public_joint_ranges=self.public_guard.public_joint_ranges,
            dt=self.dt, trainable=False,
        )
        clone._state = _parameter_state(
            state.theta.copy(), state.covariance.copy(), state.vector_update_count,
        )
        return clone
