from __future__ import annotations

from nsqd.cli import app


def main() -> None:
    app()


__all__ = ["app", "main"]
