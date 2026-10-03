from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from research.financial_jepa.contracts import ALPHAS, SEEDS, ProtocolError


class Fold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    fold_id: int
    training_dates: tuple[str, ...]
    selection_dates: tuple[str, ...]
    diagnostic_dates: tuple[str, ...]
    membership_sha256: str
    selection_plan_sha256: str


class WalkForwardProtocol(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    protocol_version: Literal["yield-jepa-walkforward-preregistration/1"] = (
        "yield-jepa-walkforward-preregistration/1"
    )
    status: Literal["preregistered_not_executed"] = "preregistered_not_executed"
    reserved_period: tuple[str, str] = ("2022-01-01", "2025-12-31")
    source_selection_artifact_sha256: str
    folds: tuple[Fold, ...]
    rules: tuple[str, ...] = (
        "All fold outcomes through 2021 are retrospective development diagnostics.",
        "Fit every scaler, PCA, model and ridge solely on that fold's training rows.",
        "Train new seeded models per fold; source selected states are provenance only "
        "and forbidden as fold initializers.",
        "Select epochs and shared ridge alpha only on that fold's selection rows; "
        "no diagnostic refit.",
        "Build contexts and targets wholly within each partition; "
        "retain original missing-row, gap and methodology boundaries.",
        "Use seeds 17/29/43, ten epochs, alpha grid and matched input/readout groups "
        "from capacity protocol/1.",
        "Record every fit failure; paired summaries use only common successful "
        "seed/fold pairs and show excluded counts.",
        "Report fold and seed variation descriptively; chronological folds are "
        "dependent, not significance samples.",
        "No evaluation loader or authorization for 2022-2025 is provided by this preregistration.",
        "A future evaluator requires a separately versioned, frozen selection handoff "
        "before opening reserved values.",
        "Future execution is bounded to four folds, three seeds, ten epochs each, "
        "CPU and 3600 seconds; abort incomplete output.",
    )


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def preregister_folds(dates: tuple[date, ...], source_identity: str) -> WalkForwardProtocol:
    if any(day.year < 2001 or day.year > 2021 for day in dates):
        raise ProtocolError(
            "reserved or unsupported dates cannot enter development preregistration"
        )
    if len(dates) != len(set(dates)) or tuple(sorted(dates)) != dates:
        raise ProtocolError("fold dates must be unique and chronological")
    if len(source_identity) != 64 or any(
        char not in "0123456789abcdef" for char in source_identity
    ):
        raise ProtocolError("selection artifact identity must be SHA-256")
    folds = []
    for index, end in enumerate((2011, 2013, 2015, 2017), start=1):
        membership = {
            "training_dates": tuple(day.isoformat() for day in dates if day.year <= end),
            "selection_dates": tuple(day.isoformat() for day in dates if end < day.year <= end + 2),
            "diagnostic_dates": tuple(
                day.isoformat() for day in dates if end + 2 < day.year <= end + 4
            ),
        }
        if not all(membership.values()):
            raise ProtocolError("walk-forward fold has an empty partition")
        identity = digest(membership)
        folds.append(
            Fold(
                fold_id=index,
                **membership,
                membership_sha256=identity,
                selection_plan_sha256=digest(
                    {
                        "membership": identity,
                        "seeds": SEEDS,
                        "alphas": ALPHAS,
                        "epochs": 10,
                        "source_provenance": source_identity,
                        "readout_groups": {"current": [8, 8], "history": [240, 16]},
                    }
                ),
            )
        )
    return WalkForwardProtocol(source_selection_artifact_sha256=source_identity, folds=tuple(folds))
