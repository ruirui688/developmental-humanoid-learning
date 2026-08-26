import torch

from developmental_g1.body_schema import BodySchemaActor


def test_body_schema_actor_shapes_and_shared_encoder_gradient():
    actor = BodySchemaActor(
        observation_dim=12,
        num_actions=4,
        schema_target_dim=7,
        hidden_dims=(16, 8),
        schema_hidden_dim=10,
        activation="ELU",
        init_noise_std=0.8,
    )
    observations = torch.randn(5, 12)
    executed_actions = torch.randn(5, 4)
    prediction = actor.predict_body_schema(observations, executed_actions)
    assert prediction.shape == (5, 7)
    prediction.square().mean().backward()
    assert actor.encoder[0].weight.grad is not None


def test_maturation_exploration_scale_changes_distribution_not_mean():
    actor = BodySchemaActor(
        observation_dim=3,
        num_actions=2,
        schema_target_dim=4,
        hidden_dims=(8,),
        schema_hidden_dim=8,
        activation="ELU",
        init_noise_std=0.8,
    )
    observations = torch.randn(6, 3)
    actor.noise_scale = 0.25
    actor.update_distribution(observations)
    protected_mean = actor.action_mean.clone()
    assert torch.allclose(actor.action_std, torch.full((6, 2), 0.2))
    actor.noise_scale = 1.0
    actor.update_distribution(observations)
    assert torch.allclose(actor.action_mean, protected_mean)
    assert torch.allclose(actor.action_std, torch.full((6, 2), 0.5))


def test_body_schema_actor_clamps_effective_exploration_std():
    actor = BodySchemaActor(
        observation_dim=4,
        num_actions=2,
        schema_target_dim=3,
        hidden_dims=(8,),
        schema_hidden_dim=4,
        activation="ELU",
        init_noise_std=0.8,
        min_noise_std=0.05,
        max_noise_std=0.5,
    )
    actor.noise_scale = 2.0
    assert torch.allclose(actor.std, torch.full((2,), 0.5))
    actor.raw_std.data.fill_(0.01)
    actor.noise_scale = 0.25
    assert torch.allclose(actor.std, torch.full((2,), 0.05))
