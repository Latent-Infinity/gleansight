from __future__ import annotations

from pathlib import Path

from research.catalog.artifacts import document
from research.catalog.baseline import verify_baseline
from research.catalog.capacity import verify_capacity
from research.catalog.diagnostics import verify_diagnostics
from research.catalog.models import CatalogError, VerifiedRun


def verify_bundle(path: Path) -> VerifiedRun:
    """Verify only existing selected outputs; never execute a research workflow."""
    try:
        metadata = document(path / "run-metadata.json")
        match metadata.get("workflow"):
            case "financial-jepa":
                return verify_baseline(path)
            case "financial-jepa-diagnostics":
                return verify_diagnostics(path)
            case None:
                return verify_capacity(path)
            case _:
                raise CatalogError(
                    "Unsupported research workflow; preregistration is not an executed run"
                )
    except KeyError as exc:
        raise CatalogError(f"Research bundle contract is missing {exc.args[0]}") from exc
