from __future__ import annotations

from research.financial_jepa.contracts import YieldVector


def curve(level: float, spacing: float) -> YieldVector:
    return (
        level,
        level + spacing,
        level + 2 * spacing,
        level + 3 * spacing,
        level + 4 * spacing,
        level + 5 * spacing,
        level + 6 * spacing,
        level + 7 * spacing,
    )


def scale(values: YieldVector, factor: float) -> YieldVector:
    return (
        values[0] * factor,
        values[1] * factor,
        values[2] * factor,
        values[3] * factor,
        values[4] * factor,
        values[5] * factor,
        values[6] * factor,
        values[7] * factor,
    )
