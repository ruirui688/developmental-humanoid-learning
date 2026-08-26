import pytest
import torch

from developmental_g1.evaluation import CompetenceWindow


def test_competence_window_uses_episode_counts_and_step_signals():
    window = CompetenceWindow(required_episodes=3)
    window.record_step(
        episode_done=torch.tensor([True, True, False]),
        episode_fell=torch.tensor([False, True, False]),
        upright=torch.tensor([1.0, 0.0, 1.0]),
        low_risk=torch.tensor([1.0, 0.0, 1.0]),
        low_saturation=torch.tensor([1.0, 0.5, 1.0]),
        schema_accuracy=torch.tensor([0.9, 0.3, 0.6]),
        schema_valid=torch.tensor([False, False, True]),
    )
    assert not window.complete
    window.record_step(
        episode_done=torch.tensor([False, True]),
        episode_fell=torch.tensor([False, False]),
        upright=torch.tensor([0.5, 1.0]),
        low_risk=torch.tensor([1.0, 1.0]),
        low_saturation=torch.tensor([0.5, 1.0]),
        schema_accuracy=torch.tensor([0.4, 0.8]),
        schema_valid=torch.tensor([True, False]),
    )
    result = window.result()
    assert result.episodes == 3
    assert result.successful_episodes == 2
    assert result.fallen_episodes == 1
    assert result.evaluation_steps == 5
    assert result.mean_episode_steps == pytest.approx(5 / 3)
    assert result.sample.survival == pytest.approx(2 / 3)
    assert result.sample.fall_rate == pytest.approx(1 / 3)
    assert result.sample.upright == pytest.approx(0.7)
    assert result.sample.low_risk == pytest.approx(0.8)
    assert result.sample.low_saturation == pytest.approx(0.8)
    assert result.sample.schema_accuracy == pytest.approx(0.5)


def test_competence_window_rejects_fall_without_episode_end():
    window = CompetenceWindow(required_episodes=1)
    with pytest.raises(ValueError):
        window.record_step(
            episode_done=torch.tensor([False]),
            episode_fell=torch.tensor([True]),
            upright=torch.ones(1),
            low_risk=torch.ones(1),
            low_saturation=torch.ones(1),
            schema_accuracy=torch.ones(1),
            schema_valid=torch.ones(1, dtype=torch.bool),
        )


def test_competence_window_requires_all_episodes():
    window = CompetenceWindow(required_episodes=2)
    window.record_step(
        episode_done=torch.tensor([True]),
        episode_fell=torch.tensor([False]),
        upright=torch.ones(1),
        low_risk=torch.ones(1),
        low_saturation=torch.ones(1),
        schema_accuracy=torch.ones(1),
        schema_valid=torch.ones(1, dtype=torch.bool),
    )
    with pytest.raises(RuntimeError):
        window.result()


def test_competence_window_separates_signal_rows_from_simulated_steps():
    window = CompetenceWindow(required_episodes=1)
    window.record_step(
        episode_done=torch.tensor([True]),
        episode_fell=torch.tensor([False]),
        upright=torch.ones(1),
        low_risk=torch.ones(1),
        low_saturation=torch.ones(1),
        schema_accuracy=torch.ones(1),
        schema_valid=torch.ones(1, dtype=torch.bool),
        simulated_environment_steps=8,
    )
    assert window.result().evaluation_steps == 8


def test_competence_window_rejects_too_few_simulated_steps():
    window = CompetenceWindow(required_episodes=1)
    with pytest.raises(ValueError):
        window.record_step(
            episode_done=torch.tensor([False, False]),
            episode_fell=torch.tensor([False, False]),
            upright=torch.ones(2),
            low_risk=torch.ones(2),
            low_saturation=torch.ones(2),
            schema_accuracy=torch.ones(2),
            schema_valid=torch.ones(2, dtype=torch.bool),
            simulated_environment_steps=1,
        )
