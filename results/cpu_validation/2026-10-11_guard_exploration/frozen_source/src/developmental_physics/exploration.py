"""Fixed, independent-joint smooth exploration. RNG state is not learning."""

from __future__ import annotations

import hashlib
import json
import numpy as np


class SmoothRandomExplorer:
    def __init__(self, action_limits: np.ndarray, seed: int = 0, smoothing: float = .9):
        self.limits = np.asarray(action_limits, dtype=float).copy()
        if self.limits.shape != (8,) or not np.isfinite(self.limits).all() or np.any(self.limits <= 0):
            raise ValueError("action_limits must be 8 finite positive values")
        if not np.isfinite(smoothing) or not 0 <= smoothing < 1:
            raise ValueError("smoothing must be in [0, 1)")
        self.smoothing = float(smoothing)
        self.rng = np.random.default_rng(seed)
        self.command = np.zeros(8)

    def parameter_fingerprint(self) -> str:
        return hashlib.sha256(json.dumps({"limits": self.limits.tolist(), "smoothing": self.smoothing}, sort_keys=True).encode()).hexdigest()

    def act(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        # Open-loop audit prefix: observations are collected, not optimized yet.
        noise = self.rng.uniform(-self.limits, self.limits)
        self.command = self.smoothing * self.command + (1 - self.smoothing) * noise
        return self.command.copy()
