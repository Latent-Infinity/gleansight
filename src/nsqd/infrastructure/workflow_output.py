from __future__ import annotations

import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

_WORKFLOW_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class WorkflowOutputError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def _create_directory_nofollow(path: Path) -> None:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise WorkflowOutputError(reason="workflow output requires no-follow directory support")
    descriptors: list[int] = []
    try:
        directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for component in path.parts[1:-1]:
            try:
                next_directory = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
            except FileNotFoundError:
                os.mkdir(component, dir_fd=directory)
                next_directory = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
            descriptors.append(next_directory)
            directory = next_directory
        os.mkdir(path.name, dir_fd=directory)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _explicit_output_path(repo_root: Path, output_dir: Path) -> Path:
    if ".." in output_dir.parts:
        raise WorkflowOutputError(reason="output directory must not contain parent traversal")
    candidate = output_dir.expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    current = Path(candidate.anchor)
    allowed_temp_aliases = {Path(tempfile.gettempdir()), Path("/tmp")}
    for component in candidate.parts[1:]:
        current /= component
        if current.is_symlink() and current not in allowed_temp_aliases:
            raise WorkflowOutputError(reason="output directory must not resolve through a symlink")
    resolved = candidate.resolve(strict=False)
    repository = repo_root.resolve()
    repository_output = repository / "output"
    if resolved == repository or repository in resolved.parents:
        if resolved == repository_output or repository_output not in resolved.parents:
            raise WorkflowOutputError(
                reason="repository output directory must be below repo_root/output"
            )
        return resolved
    temp_root = Path(tempfile.gettempdir()).resolve()
    if resolved == temp_root or temp_root not in resolved.parents:
        raise WorkflowOutputError(
            reason="external output directory must be below the system temporary directory"
        )
    return resolved


def create_run_directory(
    repo_root: Path,
    workflow: str,
    output_dir: Path | None = None,
) -> Path:
    """Create and return a fresh, non-symlinked workflow run directory."""
    if _WORKFLOW_PATTERN.fullmatch(workflow) is None:
        raise WorkflowOutputError(reason="workflow must be a lowercase hyphenated path segment")
    if output_dir is not None:
        explicit = _explicit_output_path(repo_root, output_dir)
        _create_directory_nofollow(explicit)
        return explicit

    parent = repo_root.resolve() / "output" / workflow
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    while True:
        candidate = parent / f"{timestamp}-{uuid.uuid4().hex[:12]}"
        try:
            _create_directory_nofollow(candidate)
        except FileExistsError:
            continue
        return candidate
