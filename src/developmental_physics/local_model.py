"""Small native-signal ARX/RLS model and fixed local predictive controller.

No environment or simulator object enters this module. RLS predicts a local
joint's next velocity from its encoders and requested actuator torque. The
generic initial coefficients are disclosed assumptions, not an identified
robot or a task policy. Mathematical MPC rollouts consume no physical steps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from numbers import Real

import numpy as np


INITIAL_COEFFICIENTS = (1.0, 0.0, 0.02, 0.0)
INITIAL_COVARIANCE = 100.0
FORGETTING_FACTOR = 1.0


def _scalar(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real scalar")
    return float(value)


def _digest(record: object) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


class LocalBodyModel:
    """Velocity ARX model with float64, no-forgetting recursive least squares.

    Features are [v, q-qref, requested_torque, 1]. Requested torque is known
    before the transition; realized endpoint torque is diagnostic only. The
    next position is an Euler prediction q + dt * predicted_next_v; it is a
    model approximation, not the simulator's actual substep integration rule.
    """

    def __init__(self, qref: float, *, dt: float = 0.02, trainable: bool = True):
        self._qref = _scalar("qref", qref)
        self._dt = _scalar("dt", dt)
        if self.dt <= 0:
            raise ValueError("dt must be positive")
        if type(trainable) is not bool:
            raise ValueError("trainable must be a boolean")
        self._trainable = trainable
        self._theta = np.asarray(INITIAL_COEFFICIENTS, dtype=np.float64)
        self._covariance = np.eye(4, dtype=np.float64) * INITIAL_COVARIANCE
        self._update_count = 0

    @property
    def qref(self) -> float:
        return self._qref

    @property
    def dt(self) -> float:
        return self._dt

    @property
    def trainable(self) -> bool:
        return self._trainable

    @property
    def update_count(self) -> int:
        return self._update_count

    @property
    def coefficients(self) -> np.ndarray:
        return self._theta.copy()

    @property
    def covariance(self) -> np.ndarray:
        return self._covariance.copy()

    def _features(self, q: float, v: float, torque: float) -> tuple[float, np.ndarray]:
        position = _scalar("q", q)
        velocity = _scalar("v", v)
        requested = _scalar("torque", torque)
        features = np.asarray([velocity, position - self.qref, requested, 1.], dtype=np.float64)
        if not np.isfinite(features).all():
            raise ValueError("features must remain finite")
        return position, features

    def predict(self, q: float, v: float, torque: float) -> tuple[float, float]:
        position, features = self._features(q, v, torque)
        with np.errstate(over="ignore", invalid="ignore"):
            next_v = float(self._theta @ features)
            next_q = position + self.dt * next_v
        if not np.isfinite([next_q, next_v]).all():
            raise ValueError("prediction overflowed")
        return next_q, next_v

    def _parameter_record(self) -> dict[str, object]:
        return {
            "qref_rad": self.qref,
            "dt_seconds": self.dt,
            "features": ["v", "q-qref", "requested_torque", "1"],
            "initial_coefficients": list(INITIAL_COEFFICIENTS),
            "initial_covariance_scale": INITIAL_COVARIANCE,
            "forgetting_factor": FORGETTING_FACTOR,
            "coefficients": self._theta.tolist(),
            "covariance": self._covariance.tolist(),
            "dtype": "float64",
        }

    def parameter_fingerprint(self) -> str:
        # Frozen clones carry identical learned parameters. Update permission
        # and the cumulative call count are recorded separately in snapshots.
        return _digest(self._parameter_record())

    def snapshot(self) -> dict[str, object]:
        return {
            **self._parameter_record(),
            "parameter_fingerprint": self.parameter_fingerprint(),
            "update_count": self.update_count,
            "trainable": self.trainable,
            "initial_prior": "generic velocity continuity and torque response, not identified body dynamics",
            "torque_input": "requested torque at control-step start; realized endpoint torque is diagnostic only",
        }

    def clone_frozen(self) -> LocalBodyModel:
        clone = LocalBodyModel(self.qref, dt=self.dt, trainable=False)
        clone._theta = self._theta.copy()
        clone._covariance = self._covariance.copy()
        clone._update_count = self.update_count
        return clone

    def update(self, q: float, v: float, torque: float, next_v: float, *,
               phase: str = "identification") -> dict[str, object]:
        """Record a pre-update prediction, then update unless this is prefix.

        Prefix interaction remains paid by the caller, while prefix samples
        cannot alter these parameters. Frozen evaluation models reject every
        update call; use predict() during evaluation.
        """
        if not self.trainable:
            raise RuntimeError("frozen evaluation model cannot update")
        if phase not in ("prefix", "identification", "probe", "recovery"):
            raise ValueError("phase must be prefix, identification, probe or recovery")
        _, features = self._features(q, v, torque)
        observed_next_v = _scalar("next_v", next_v)
        predicted_q, predicted_v = self.predict(q, v, torque)
        residual = observed_next_v - predicted_v
        if not np.isfinite(residual):
            raise ValueError("prediction residual overflowed")
        before = self.parameter_fingerprint()
        updated = phase != "prefix"
        if updated:
            try:
                with np.errstate(over="raise", invalid="raise", divide="raise"):
                    projected = self._covariance @ features
                    denominator = FORGETTING_FACTOR + float(features @ projected)
                    if not np.isfinite(denominator) or denominator <= 0:
                        raise ValueError("RLS denominator must be finite and positive")
                    gain = projected / denominator
                    theta = self._theta + gain * residual
                    covariance = (self._covariance - np.outer(gain, projected)) / FORGETTING_FACTOR
                    covariance = .5 * (covariance + covariance.T)
            except FloatingPointError as error:
                raise ValueError("RLS arithmetic overflowed") from error
            if not np.isfinite(theta).all() or not np.isfinite(covariance).all():
                raise ValueError("RLS parameters must remain finite")
            # Compute first, then commit atomically so a rejected sample costs
            # no parameter mutation or claimed successful update.
            self._theta = theta
            self._covariance = covariance
            self._update_count += 1
        return {
            "phase": phase,
            "updated": updated,
            "features": features.tolist(),
            "preupdate_prediction": {"next_q_rad": predicted_q, "next_v_rad_s": predicted_v},
            "observed_next_v_rad_s": observed_next_v,
            "preupdate_error_rad_s": residual,
            "update_count": self.update_count,
            "parameter_fingerprint_before": before,
            "parameter_fingerprint_after": self.parameter_fingerprint(),
        }


@dataclass(frozen=True)
class MPCConfig:
    horizon: int = 15
    candidate_count: int = 9
    torque_limit_nm: float = 0.5
    position_weight: float = 1.0
    velocity_weight: float = 0.002
    effort_weight: float = 0.00002
    change_weight: float = 0.00002
    local_position_radius_rad: float = 0.15
    prediction_limit_tolerance_rad: float = 0.03
    target_limit_margin_rad: float = 0.03
    velocity_limit_rad_s: float = 1.5

    def __post_init__(self) -> None:
        if type(self.horizon) is not int or self.horizon < 1:
            raise ValueError("horizon must be a positive integer")
        if (type(self.candidate_count) is not int or self.candidate_count < 3
                or self.candidate_count % 2 != 1):
            raise ValueError("candidate_count must be odd and >= 3 to include zero")
        for name, value in asdict(self).items():
            if name in ("horizon", "candidate_count"):
                continue
            scalar = _scalar(name, value)
            nonnegative = name.endswith("weight") or name.endswith("tolerance_rad")
            if scalar < 0 or (scalar == 0 and not nonnegative):
                raise ValueError(f"{name} must be {'nonnegative' if nonnegative else 'positive'}")
        if self.torque_limit_nm > .5:
            raise ValueError("torque limit cannot exceed the shared 0.5 N m permission")
        if self.prediction_limit_tolerance_rad >= .08:
            raise ValueError("forecast tolerance must stay inside the environment exit margin")


@dataclass(frozen=True)
class MPCDecision:
    torque: float
    feasible_candidates: int
    fallback: bool
    cost: float | None
    predicted_q: tuple[float, ...]
    predicted_v: tuple[float, ...]
    mathematical_prediction_calls: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FixedLocalMPC:
    """Constant-action finite-grid MPC using only the passed local model.

    Forecast limits permit 0.03 rad of soft-limit excursion; task targets
    remain 0.03 rad inside public limits. This mathematical tolerance does
    not modify the independent environment's torque/limit guards.
    """

    def __init__(self, model: LocalBodyModel, joint_range: object,
                 config: MPCConfig | None = None):
        if not isinstance(model, LocalBodyModel):
            raise TypeError("model must be a LocalBodyModel")
        self.model = model
        self.config = MPCConfig() if config is None else config
        if not isinstance(self.config, MPCConfig):
            raise TypeError("config must be an MPCConfig")
        try:
            limits = np.asarray(joint_range, dtype=float)
        except (ValueError, TypeError) as error:
            raise ValueError("joint_range must be two finite ordered public limits") from error
        if (limits.shape != (2,) or not np.isfinite(limits).all()
                or limits[0] >= limits[1]):
            raise ValueError("joint_range must be two finite ordered public limits")
        self.joint_range = tuple(float(v) for v in limits)
        radius = self.config.local_position_radius_rad
        tolerance = self.config.prediction_limit_tolerance_rad
        margin = self.config.target_limit_margin_rad
        self.forecast_bounds = (max(model.qref - radius, self.joint_range[0] - tolerance),
                                min(model.qref + radius, self.joint_range[1] + tolerance))
        self.target_bounds = (max(model.qref - radius, self.joint_range[0] + margin),
                              min(model.qref + radius, self.joint_range[1] - margin))
        self._candidates = tuple(float(v) for v in np.linspace(
            -self.config.torque_limit_nm, self.config.torque_limit_nm, self.config.candidate_count))

    def spec(self) -> dict[str, object]:
        return {
            "config": asdict(self.config),
            "qref_rad": self.model.qref,
            "joint_range_rad": list(self.joint_range),
            "forecast_bounds_rad": list(self.forecast_bounds),
            "target_bounds_rad": list(self.target_bounds),
            "candidates_nm": list(self._candidates),
            "action_rollout": "constant torque over the full horizon",
            "cost": "summed position, velocity and effort; change cost at first step",
            "tie_break": "cost, absolute torque, signed torque",
            "fallback_nm": 0.,
            "physical_queries": 0,
        }

    def parameter_fingerprint(self) -> str:
        return _digest(self.spec())

    def select(self, q: float, v: float, target_q: float, *,
               previous_torque: float = 0.) -> MPCDecision:
        position = _scalar("q", q)
        velocity = _scalar("v", v)
        target = _scalar("target_q", target_q)
        previous = _scalar("previous_torque", previous_torque)
        if abs(previous) > self.config.torque_limit_nm:
            raise ValueError("previous torque exceeds the fixed command permission")
        if not self.target_bounds[0] <= target <= self.target_bounds[1]:
            raise ValueError("target must be local and inside the public limit margin")
        cfg = self.config
        lower, upper = self.forecast_bounds
        feasible = []
        calls = 0
        for torque in self._candidates:
            predicted_q, predicted_v = position, velocity
            trajectory_q, trajectory_v = [], []
            cost = cfg.change_weight * (torque - previous) ** 2
            for _ in range(cfg.horizon):
                calls += 1
                try:
                    predicted_q, predicted_v = self.model.predict(predicted_q, predicted_v, torque)
                except ValueError:
                    break
                if (not lower <= predicted_q <= upper
                        or abs(predicted_v) > cfg.velocity_limit_rad_s):
                    break
                trajectory_q.append(predicted_q)
                trajectory_v.append(predicted_v)
                cost += (cfg.position_weight * (predicted_q - target) ** 2
                         + cfg.velocity_weight * predicted_v ** 2
                         + cfg.effort_weight * torque ** 2)
                if not np.isfinite(cost):
                    break
            else:
                feasible.append((cost, abs(torque), torque, tuple(trajectory_q), tuple(trajectory_v)))
        if not feasible:
            return MPCDecision(0., 0, True, None, (), (), calls)
        cost, _, torque, trajectory_q, trajectory_v = min(feasible)
        return MPCDecision(torque, len(feasible), False, cost, trajectory_q, trajectory_v, calls)
