from __future__ import annotations

import hashlib
from datetime import date, timedelta

import torch

from research.financial_jepa.contracts import DevelopmentData, ExperimentConfig, Variant, YieldRow
from research.financial_jepa.dataset import prepare_splits
from research.financial_jepa.model import build_model, compute_loss, shuffled_targets, update_ema
from research.financial_jepa.training import train_variant, train_variant_recorded
from tests.research.support import curve


def _development(config: ExperimentConfig) -> DevelopmentData:
    rows: list[YieldRow] = []
    for year, base in ((2017, 1.0), (2018, 2.0), (2022, 3.0)):
        start = date(year, 1, 1)
        rows.extend(
            YieldRow(
                observed_on=start + timedelta(days=index),
                yields=curve(base + 0.02 * index, 0.1),
                boundary_before=False,
            )
            for index in range(14)
        )
    prepared = prepare_splits(tuple(rows), config)
    return DevelopmentData(train=prepared.train, validation=prepared.validation)


def _state_digest(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        digest.update(name.encode())
        digest.update(tensor.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def test_model_uses_last_context_token_and_has_causal_shapes() -> None:
    config = ExperimentConfig.synthetic(context_length=4, future_length=2, batch_size=2, epochs=1)
    model = build_model(config, seed=17)
    context = torch.randn(2, 4, 8)

    prediction = model.predict(context)

    assert prediction.shape == (2, 2, 16)
    changed_future = context.clone()
    changed_future[:, -1, :] += 1.0
    assert not torch.equal(prediction, model.predict(changed_future))


def test_predictor_is_causal_and_reads_last_context_hidden_state() -> None:
    config = ExperimentConfig.synthetic(context_length=4, future_length=2, batch_size=2, epochs=1)
    model = build_model(config, seed=17)
    model.eval()
    context = torch.randn(2, 4, 8)
    latents = model.encoder(context)
    sequence = latents + model.predictor.position.unsqueeze(0)
    mask = torch.triu(torch.ones(4, 4, dtype=torch.bool), diagonal=1)

    with torch.no_grad():
        hidden = model.predictor.transformer(sequence, mask=mask, is_causal=True)
        expected = model.predictor.future_head(hidden[:, -1, :]).reshape(2, 2, 16)
        changed = sequence.clone()
        changed[:, -1, :] += 100.0
        changed_hidden = model.predictor.transformer(changed, mask=mask, is_causal=True)

    assert torch.allclose(model.predictor(latents), expected)
    assert torch.allclose(hidden[:, :-1, :], changed_hidden[:, :-1, :])


def test_target_has_no_grad_and_ema_moves_toward_online() -> None:
    config = ExperimentConfig.synthetic(context_length=3, future_length=2, batch_size=2, epochs=1)
    model = build_model(config, seed=17)
    before = tuple(parameter.clone() for parameter in model.target_encoder.parameters())
    with torch.no_grad():
        for parameter in model.encoder.parameters():
            parameter.add_(1.0)

    update_ema(model, decay=0.99)
    targets = model.encode_target(torch.randn(2, 2, 8))

    assert targets.requires_grad is False
    assert all(parameter.requires_grad is False for parameter in model.target_encoder.parameters())
    assert any(
        not torch.equal(old, new)
        for old, new in zip(before, model.target_encoder.parameters(), strict=True)
    )


def test_vicreg_loss_and_seeded_shuffle_are_finite_derangements() -> None:
    prediction = torch.zeros(4, 2, 16)
    target = torch.arange(128, dtype=torch.float32).reshape(4, 2, 16)
    context = torch.randn(4, 3, 16)

    shuffled = shuffled_targets(target, seed=17, epoch=2, batch_index=3)
    terms = compute_loss(prediction, target, context, regularize=True)

    assert all(not torch.equal(shuffled[index], target[index]) for index in range(4))
    assert terms.total.isfinite()
    assert terms.total > terms.prediction


def test_training_is_deterministic_and_different_seeds_differ() -> None:
    config = ExperimentConfig.synthetic(context_length=3, future_length=2, batch_size=2, epochs=2)
    development = _development(config)

    first = train_variant(development, config, Variant.REGULARIZED, seed=17)
    repeated = train_variant(development, config, Variant.REGULARIZED, seed=17)
    alternate = train_variant(development, config, Variant.REGULARIZED, seed=29)

    assert first.selected_epoch == repeated.selected_epoch
    assert _state_digest(first.model_state) == _state_digest(repeated.model_state)
    assert _state_digest(first.model_state) != _state_digest(alternate.model_state)


def test_recorded_training_preserves_pre_refactor_golden() -> None:
    config = ExperimentConfig.synthetic(context_length=3, future_length=2, batch_size=2, epochs=2)
    rows: list[YieldRow] = []
    for year, base in ((2017, 1.0), (2018, 2.0), (2022, 3.0)):
        rows.extend(
            YieldRow(
                date(year, 1, 1) + timedelta(days=index),
                curve(base + 0.03 * index, 0.05),
                False,
            )
            for index in range(22)
        )
    prepared = prepare_splits(tuple(rows), config)
    development = DevelopmentData(prepared.train, prepared.validation)

    recorded = train_variant_recorded(development, config, Variant.REGULARIZED, seed=17)
    legacy = train_variant(development, config, Variant.REGULARIZED, seed=17)

    assert recorded.result.selected_epoch == legacy.selected_epoch == 2
    assert recorded.result.validation_mse == legacy.validation_mse == 0.7429499626159668
    assert recorded.result.state_sha256 == legacy.state_sha256
    assert recorded.result.state_sha256 == (
        "55d1c9fe9639a354d59fa84db0b69e50d50a6a2c31c39843f323272a2710fcdd"
    )
    assert len(recorded.epochs) == 2
    assert recorded.epochs[0].batch_count == 9
    assert recorded.epochs[0].window_count == 18
    assert recorded.epochs[1].checkpoint_updated is True
    assert _state_digest(recorded.initial_model_state) != recorded.result.state_sha256
