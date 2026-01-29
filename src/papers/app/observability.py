from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class MetricsSink(Protocol):
    def increment(self, name: str, value: int = 1, tags: dict[str, Any] | None = None) -> None: ...

    def observe(self, name: str, value: float, tags: dict[str, Any] | None = None) -> None: ...


@dataclass
class NoopMetrics(MetricsSink):
    def increment(self, name: str, value: int = 1, tags: dict[str, Any] | None = None) -> None:
        return None

    def observe(self, name: str, value: float, tags: dict[str, Any] | None = None) -> None:
        return None


@dataclass
class InMemoryMetrics(MetricsSink):
    increments: list[tuple[str, int, dict[str, Any]]] = field(default_factory=list)
    observations: list[tuple[str, float, dict[str, Any]]] = field(default_factory=list)

    def increment(self, name: str, value: int = 1, tags: dict[str, Any] | None = None) -> None:
        self.increments.append((name, value, tags or {}))

    def observe(self, name: str, value: float, tags: dict[str, Any] | None = None) -> None:
        self.observations.append((name, value, tags or {}))
