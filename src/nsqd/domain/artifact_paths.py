from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

LEGACY_REVIEW_PREFIX: Final = Path("docs/reviews")
REVIEW_ARCHIVE_PREFIX: Final = Path("evidence/archive/reviews/v1")


@dataclass(frozen=True, slots=True)
class InvalidArtifactPathError(ValueError):
    logical_path: Path

    def __str__(self) -> str:
        return f"artifact path must be repo-relative without traversal: {self.logical_path}"


def resolve_artifact_path(repo_root: Path, logical_path: Path) -> Path:
    """Translate a persisted repo-relative artifact identity to its physical path."""
    if logical_path.is_absolute() or ".." in logical_path.parts:
        raise InvalidArtifactPathError(logical_path=logical_path)
    if logical_path.parts[:2] == LEGACY_REVIEW_PREFIX.parts:
        return repo_root / REVIEW_ARCHIVE_PREFIX / Path(*logical_path.parts[2:])
    return repo_root / logical_path
