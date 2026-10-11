"""Frozen position-integration views of the unchanged local velocity model.

The dynamics parameter fingerprint deliberately stays identical between
views. A separate integration fingerprint identifies the prediction rule.
Only native q/v and a currently known requested command enter predict().
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from .local_model import LocalBodyModel


INTEGRATIONS = ("endpoint_euler", "trapezoid")


class FrozenIntegrationModel(LocalBodyModel):
    """An isolated frozen copy; only position integration can differ.

    Subclassing preserves the existing FixedLocalMPC model interface. The
    owned velocity model supplies validation, parameters and all velocity
    predictions; no RLS equations or model coefficients are changed here.
    """

    def __init__(self, model: LocalBodyModel, integration: str = "endpoint_euler"):
        if not isinstance(model, LocalBodyModel):
            raise TypeError("model must be a LocalBodyModel")
        if integration not in INTEGRATIONS:
            raise ValueError("integration must be endpoint_euler or trapezoid")
        if isinstance(model, FrozenIntegrationModel):
            model = model._velocity_model
        self._velocity_model = model.clone_frozen()
        self._integration = integration

    @property
    def qref(self):
        return self._velocity_model.qref

    @property
    def dt(self):
        return self._velocity_model.dt

    @property
    def trainable(self):
        return False

    @property
    def update_count(self):
        return self._velocity_model.update_count

    @property
    def coefficients(self):
        return self._velocity_model.coefficients

    @property
    def covariance(self):
        return self._velocity_model.covariance

    @property
    def integration(self):
        return self._integration

    def predict(self, q, v, torque):
        next_q, next_v = self._velocity_model.predict(q, v, torque)
        if self.integration == "trapezoid":
            next_q = float(q) + self.dt * (.5*float(v) + .5*next_v)
        if not np.isfinite([next_q, next_v]).all():
            raise ValueError("position integration overflowed")
        return next_q, next_v

    def update(self, *args, **kwargs):
        raise RuntimeError("frozen integration view cannot update")

    def parameter_fingerprint(self):
        return self._velocity_model.parameter_fingerprint()

    def integration_spec(self):
        return {
            "mode": self.integration, "dt_seconds": self.dt,
            "rule": "q + dt * predicted_next_v" if self.integration == "endpoint_euler" else "q + dt * (current_v + predicted_next_v) / 2",
            "endpoint_velocity_rule_unchanged": True,
            "dynamics_parameter_fingerprint": self.parameter_fingerprint(),
        }

    def integration_fingerprint(self):
        return hashlib.sha256(json.dumps(self.integration_spec(), sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()

    def snapshot(self):
        return {**self._velocity_model.snapshot(), "integration": self.integration_spec(),
                "integration_fingerprint": self.integration_fingerprint(),
                "frozen_view": True}

    def clone_frozen(self):
        return FrozenIntegrationModel(self._velocity_model, self.integration)
