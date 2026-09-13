from __future__ import annotations

import copy
from dataclasses import dataclass

import torch
from torch import nn

from research.financial_jepa.contracts import ExperimentConfig, ProtocolError


class YieldEncoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(8, 32),
            nn.GELU(),
            nn.Linear(32, 16),
            nn.LayerNorm(16),
        )

    def forward(self, yields: torch.Tensor) -> torch.Tensor:
        return self.layers(yields)


class YieldPredictor(nn.Module):
    def __init__(self, context_length: int, future_length: int) -> None:
        super().__init__()
        self.context_length = context_length
        self.future_length = future_length
        self.position = nn.Parameter(torch.empty(context_length, 16))
        layer = nn.TransformerEncoderLayer(
            d_model=16,
            nhead=4,
            dim_feedforward=64,
            dropout=0.0,
            activation="gelu",
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(layer, num_layers=2)
        self.future_head = nn.Linear(16, future_length * 16)
        nn.init.normal_(self.position, mean=0.0, std=0.02)

    def forward(self, context_latents: torch.Tensor) -> torch.Tensor:
        sequence = context_latents + self.position.unsqueeze(0)
        causal_mask = torch.triu(
            torch.ones(
                self.context_length,
                self.context_length,
                dtype=torch.bool,
                device=sequence.device,
            ),
            diagonal=1,
        )
        hidden = self.transformer(sequence, mask=causal_mask, is_causal=True)
        return self.future_head(hidden[:, self.context_length - 1, :]).reshape(
            -1, self.future_length, 16
        )


class YieldJepa(nn.Module):
    def __init__(self, context_length: int, future_length: int) -> None:
        super().__init__()
        self.encoder = YieldEncoder()
        self.predictor = YieldPredictor(context_length, future_length)
        self.target_encoder = copy.deepcopy(self.encoder)
        self.target_encoder.requires_grad_(False)

    def predict(self, context: torch.Tensor) -> torch.Tensor:
        return self.predictor(self.encoder(context))

    def encode_target(self, future: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return self.target_encoder(future)


@dataclass(frozen=True, slots=True)
class LossTerms:
    prediction: torch.Tensor
    variance: torch.Tensor
    covariance: torch.Tensor
    total: torch.Tensor


def configure_cpu(seed: int) -> None:
    torch.set_num_threads(4)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(seed)


def build_model(config: ExperimentConfig, seed: int) -> YieldJepa:
    configure_cpu(seed)
    return YieldJepa(config.context_length, config.future_length).cpu()


def compute_loss(
    prediction: torch.Tensor,
    target: torch.Tensor,
    context_latents: torch.Tensor,
    *,
    regularize: bool,
) -> LossTerms:
    prediction_loss = torch.mean((prediction - target) ** 2)
    if regularize:
        flattened = context_latents.reshape(-1, context_latents.shape[-1])
        population_variance = torch.var(flattened, dim=0, correction=0)
        variance_loss = torch.mean(torch.relu(1.0 - torch.sqrt(population_variance + 1e-4)) ** 2)
        centered = flattened - flattened.mean(dim=0)
        covariance = centered.T @ centered / (flattened.shape[0] - 1)
        off_diagonal = covariance - torch.diag(torch.diagonal(covariance))
        covariance_loss = torch.sum(off_diagonal**2) / (16 * 15)
        total = prediction_loss + 0.1 * (variance_loss + covariance_loss)
    else:
        zero = prediction_loss.new_zeros(())
        variance_loss = zero
        covariance_loss = zero
        total = prediction_loss
    return LossTerms(prediction_loss, variance_loss, covariance_loss, total)


def update_ema(model: YieldJepa, decay: float = 0.99) -> None:
    with torch.no_grad():
        for target, online in zip(
            model.target_encoder.parameters(), model.encoder.parameters(), strict=True
        ):
            target.mul_(decay).add_(online, alpha=1.0 - decay)


def shuffled_targets(
    target: torch.Tensor,
    *,
    seed: int,
    epoch: int,
    batch_index: int,
) -> torch.Tensor:
    batch_size = target.shape[0]
    if batch_size < 2:
        raise ProtocolError("shuffled-target batches require at least two rows")
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed + epoch * 1_000_003 + batch_index * 10_007)
    offset = int(torch.randint(1, batch_size, (), generator=generator).item())
    return torch.roll(target, shifts=offset, dims=0)
