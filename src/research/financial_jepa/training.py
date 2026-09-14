from __future__ import annotations

import hashlib

import numpy as np
import torch

from research.financial_jepa.contracts import (
    Deadline,
    DevelopmentData,
    ExperimentConfig,
    ProtocolError,
    TrainResult,
    Variant,
    WindowSet,
)
from research.financial_jepa.diagnostic_contracts import EpochRecord, RecordedTrainResult
from research.financial_jepa.model import (
    YieldJepa,
    build_model,
    compute_loss,
    shuffled_targets,
    update_ema,
)


def _arrays(window_set: WindowSet) -> tuple[torch.Tensor, torch.Tensor]:
    contexts = np.stack([window.context for window in window_set.windows])
    futures = np.stack([window.future for window in window_set.windows])
    return (
        torch.from_numpy(contexts).to(dtype=torch.float32),
        torch.from_numpy(futures).to(dtype=torch.float32),
    )


def _validation_mse(model: YieldJepa, data: WindowSet, batch_size: int) -> float:
    contexts, futures = _arrays(data)
    total_error = 0.0
    element_count = 0
    model.eval()
    with torch.no_grad():
        for start in range(0, len(contexts), batch_size):
            context = contexts[start : start + batch_size]
            future = futures[start : start + batch_size]
            prediction = model.predict(context)
            target = model.encode_target(future)
            total_error += float(torch.sum((prediction - target) ** 2).item())
            element_count += prediction.numel()
    return total_error / element_count


def _state_copy(model: YieldJepa) -> dict[str, torch.Tensor]:
    return {name: tensor.detach().cpu().clone() for name, tensor in model.state_dict().items()}


def state_digest(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        digest.update(name.encode())
        digest.update(tensor.contiguous().numpy().tobytes())
    return digest.hexdigest()


def train_variant(
    development_data: DevelopmentData,
    config: ExperimentConfig,
    variant: Variant,
    seed: int,
    deadline: Deadline | None = None,
) -> TrainResult:
    return _train_variant(development_data, config, variant, seed, deadline, False).result


def train_variant_recorded(
    development_data: DevelopmentData,
    config: ExperimentConfig,
    variant: Variant,
    seed: int,
    deadline: Deadline | None = None,
) -> RecordedTrainResult:
    return _train_variant(development_data, config, variant, seed, deadline, True)


def _train_variant(
    development_data: DevelopmentData,
    config: ExperimentConfig,
    variant: Variant,
    seed: int,
    deadline: Deadline | None,
    record_epochs: bool,
) -> RecordedTrainResult:
    model = build_model(config, seed)
    initial_state = _state_copy(model)
    optimizer = torch.optim.AdamW(
        (*model.encoder.parameters(), *model.predictor.parameters()),
        lr=1e-3,
        betas=(0.9, 0.999),
        eps=1e-8,
        weight_decay=1e-4,
    )
    contexts, futures = _arrays(development_data.train)
    if len(contexts) < config.batch_size:
        raise ProtocolError("training split has no complete drop-last batch")
    selected_epoch = 0
    selected_mse = float("inf")
    selected_state = _state_copy(model)
    records: list[EpochRecord] = []
    for epoch in range(1, config.epochs + 1):
        generator = torch.Generator(device="cpu")
        generator.manual_seed(seed + epoch)
        order = torch.randperm(len(contexts), generator=generator)
        model.train()
        batch_index = 0
        prediction_total = 0.0
        variance_total = 0.0
        covariance_total = 0.0
        loss_total = 0.0
        for start in range(0, len(order) - config.batch_size + 1, config.batch_size):
            indices = order[start : start + config.batch_size]
            context = contexts[indices]
            future = futures[indices]
            context_latents = model.encoder(context)
            prediction = model.predictor(context_latents)
            target = model.encode_target(future)
            if variant is Variant.SHUFFLED_TARGET:
                target = shuffled_targets(
                    target,
                    seed=seed,
                    epoch=epoch,
                    batch_index=batch_index,
                )
            regularize = variant is not Variant.NO_REGULARIZER
            loss = compute_loss(
                prediction,
                target,
                context_latents,
                regularize=regularize,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.total.backward()
            optimizer.step()
            update_ema(model, decay=0.99)
            if record_epochs:
                prediction_total += float(loss.prediction.detach().item())
                variance_total += float(loss.variance.detach().item())
                covariance_total += float(loss.covariance.detach().item())
                loss_total += float(loss.total.detach().item())
            batch_index += 1
        validation_mse = _validation_mse(model, development_data.validation, config.batch_size)
        checkpoint_updated = validation_mse < selected_mse
        if checkpoint_updated:
            selected_epoch = epoch
            selected_mse = validation_mse
            selected_state = _state_copy(model)
        if record_epochs:
            records.append(
                EpochRecord(
                    epoch=epoch,
                    batch_count=batch_index,
                    window_count=batch_index * config.batch_size,
                    mean_prediction_loss=prediction_total / batch_index,
                    mean_variance_loss=variance_total / batch_index,
                    mean_covariance_loss=covariance_total / batch_index,
                    mean_total_loss=loss_total / batch_index,
                    aligned_validation_mse=validation_mse,
                    checkpoint_updated=checkpoint_updated,
                )
            )
        if deadline is not None:
            deadline.check()
    model.load_state_dict(selected_state)
    return RecordedTrainResult(
        result=TrainResult(
            variant=variant,
            seed=seed,
            selected_epoch=selected_epoch,
            validation_mse=selected_mse,
            model_state=selected_state,
            state_sha256=state_digest(selected_state),
        ),
        initial_model_state=initial_state,
        epochs=tuple(records),
    )
