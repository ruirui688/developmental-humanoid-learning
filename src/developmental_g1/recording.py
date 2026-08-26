"""Finite Isaac Gym recording callback for deterministic policy evaluation."""

from __future__ import annotations

from humanoidverse.agents.callbacks.base_callback import RL_EvalCallback


class FiniteStandingRecorder(RL_EvalCallback):
    """Toggle PBHC's viewer recorder and exit after an exact frame budget."""

    def __init__(self, config, training_loop):
        super().__init__(config, training_loop)
        self.recording_steps = int(config.recording_steps)
        if self.recording_steps < 1:
            raise ValueError("recording_steps must be positive")
        self.steps = 0
        self._finalized = False

    @property
    def simulator(self):
        return self.training_loop.env.simulator

    def on_pre_evaluate_policy(self):
        if not getattr(self.simulator, "visualize_viewer", False):
            raise RuntimeError("finite recording requires an Isaac Gym viewer")
        self.simulator.user_is_recording = True
        self.simulator.user_recording_state_change = True

    def on_post_eval_env_step(self, actor_state):
        self.steps += 1
        if self.steps == self.recording_steps:
            self.simulator.user_is_recording = False
            self.simulator.user_recording_state_change = True
        elif self.steps > self.recording_steps and not self._finalized:
            # The extra render step consumes the state change and writes MP4.
            self._finalized = True
            raise SystemExit(0)
        return actor_state
