from __future__ import annotations

from typing import Any

MECHANISM_VALUES = frozenset(
    {
        "behavioral",
        "institutional",
        "microstructure",
        "balance-sheet",
        "reflexivity",
        "flow-driven",
        "shock-propagation",
    }
)
TARGET_VALUES = frozenset(
    {
        "returns",
        "volatility",
        "drawdown",
        "liquidity",
        "slippage",
        "crowding",
        "signal-decay",
        "regime-transition",
    }
)
HORIZON_VALUES = frozenset(
    {
        "tick",
        "intraday",
        "daily",
        "weekly",
        "event-time",
        "regime-time",
    }
)


def cell_id_from_descriptor(descriptor: dict[str, Any]) -> str:
    mechanism = descriptor.get("mechanism")
    target = descriptor.get("target")
    horizon = descriptor.get("horizon")
    if (
        mechanism not in MECHANISM_VALUES
        or target not in TARGET_VALUES
        or horizon not in HORIZON_VALUES
    ):
        raise ValueError("unlisted research descriptor value")
    return f"mechanism={mechanism}|target={target}|horizon={horizon}"
