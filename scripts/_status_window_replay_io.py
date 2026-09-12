from __future__ import annotations

import json
import os
import sqlite3
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from nsqd.domain.operator_baselines import verify_scratch_execution_receipt
from nsqd.domain.trusted_files import (
    read_verified_repo_text,
    require_non_symlink_leaf,
    require_non_symlink_path,
    require_non_symlink_path_within_root,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKET_DIR = REPO_ROOT / "docs" / "reviews" / "nsqd-jepa-ideas-gaps-2026-09-01"
RETAINED_SOURCE_DIR = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-status-window-calendar-replay-2026-09-02"
)
OUTPUT_DIR = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-status-window-calendar-replay-2026-09-11-command-sync"
)
ARTIFACT_NAME = "calendar-replay-artifact.json"
ROWS_NAME = "extracted-timestamp-rows.json"
SUMMARY_NAME = "review-summary.json"
README_NAME = "README.md"
SUCCESSION_NAME = "succession.json"
MANIFEST_NAME = "packet-manifest.json"
MAX_PACKET_FILE_BYTES = 8 * 1024 * 1024
ALLOWED_TEMP_ROOTS = tuple(
    {
        Path(tempfile.gettempdir()).resolve(strict=False),
        Path(tempfile.gettempdir()),
        Path("/tmp").resolve(strict=False),
        Path("/tmp"),
    }
)


class ReplayValidationError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    absolute = path if path.is_absolute() else REPO_ROOT / path
    filesystem_root = Path(absolute.anchor)
    relative_path = absolute.relative_to(filesystem_root)
    value = json.loads(
        read_verified_repo_text(
            repo_root=filesystem_root,
            relative_path=relative_path,
            expected_root=relative_path.parent,
            field=str(path),
            max_bytes=MAX_PACKET_FILE_BYTES,
        )
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


@contextmanager
def _open_output_dir_nofollow(path: Path) -> Iterator[int]:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ReplayValidationError("output writes require no-follow support")
    descriptors: list[int] = []
    try:
        directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        for component in path.parts[1:]:
            try:
                next_directory = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
            except FileNotFoundError:
                try:
                    os.mkdir(component, dir_fd=directory)
                except FileExistsError:
                    pass
                next_directory = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory,
                )
            descriptors.append(next_directory)
            directory = next_directory
        yield directory
    except OSError as exc:
        raise ReplayValidationError(
            "output_dir must not resolve through a symlink or unsafe path"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _write_output_files(output_descriptor: int, files: Mapping[str, bytes]) -> None:
    descriptors: dict[str, int] = {}
    try:
        for name in files:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW,
                0o666,
                dir_fd=output_descriptor,
            )
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise ReplayValidationError("output child must be a regular file")
            descriptors[name] = descriptor
        for name, content in files.items():
            descriptor = descriptors[name]
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            remaining = memoryview(content)
            while remaining:
                written = os.write(descriptor, remaining)
                remaining = remaining[written:]
    except OSError as exc:
        raise ReplayValidationError("output child must not be a symlink or unsafe path") from exc
    finally:
        for descriptor in reversed(tuple(descriptors.values())):
            os.close(descriptor)


def _load_verified_baseline_evidence() -> dict[str, Any]:
    payload = json.loads(
        read_verified_repo_text(
            repo_root=REPO_ROOT,
            relative_path=Path(
                "docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01/baseline-evidence.json"
            ),
            expected_root=Path("docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01"),
            field="baseline_evidence_path",
            max_bytes=MAX_PACKET_FILE_BYTES,
        )
    )
    if not isinstance(payload, dict):
        raise ValueError("baseline_evidence_path must contain a JSON object")
    return payload


def _verify_historical_receipt() -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = _load_verified_baseline_evidence()
    runtime = verify_scratch_execution_receipt(
        baseline["execution_receipt"],
        scratch_runtime=baseline["scratch_runtime"],
    )
    return baseline, runtime


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    uri = db_path.resolve(strict=False).as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _require_output_path_without_descendant_symlinks(path: Path) -> None:
    absolute = path if path.is_absolute() else REPO_ROOT / path
    current = Path(absolute.anchor) if absolute.anchor else Path(".")
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    allowed_alias_prefixes: set[Path] = set()
    for root in ALLOWED_TEMP_ROOTS:
        lexical = root if root.is_absolute() else root.resolve(strict=False)
        allowed_alias_prefixes.add(lexical)
        allowed_alias_prefixes.update(lexical.parents)
        resolved = lexical.resolve(strict=False)
        allowed_alias_prefixes.add(resolved)
        allowed_alias_prefixes.update(resolved.parents)
    for part in parts:
        current = current / part
        if current.is_symlink() and current not in allowed_alias_prefixes:
            raise ValueError("output_dir must not resolve through a symlink")


def _allowed_temp_output_dir(path: Path) -> Path | None:
    expanded = path.expanduser()
    resolved = expanded.resolve(strict=False)
    for root in ALLOWED_TEMP_ROOTS:
        root_resolved = root.resolve(strict=False)
        if expanded == root or root in expanded.parents:
            require_non_symlink_path_within_root(
                path=resolved, root=root_resolved, field="output_dir"
            )
            return resolved
        if resolved == root_resolved or root_resolved in resolved.parents:
            require_non_symlink_path_within_root(
                path=resolved, root=root_resolved, field="output_dir"
            )
            return resolved
    return None


def _require_output_dir(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.is_absolute() and ".." in candidate.parts:
        raise ValueError("output_dir must not contain parent traversal")
    if not candidate.is_absolute() and ".." in candidate.parts:
        raise ValueError("output_dir must not contain parent traversal")
    _require_output_path_without_descendant_symlinks(candidate)
    repo_candidate = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    repo_resolved = repo_candidate.resolve(strict=False)
    root_resolved = REPO_ROOT.resolve(strict=False)
    if repo_resolved == OUTPUT_DIR.resolve(strict=False):
        require_non_symlink_path(repo_candidate, field="output_dir")
        require_non_symlink_path_within_root(
            path=repo_candidate,
            root=REPO_ROOT,
            field="output_dir",
        )
        require_non_symlink_leaf(path=repo_candidate, field="output_dir")
        if repo_candidate.exists() and not repo_candidate.is_dir():
            raise ValueError("output_dir must be a directory")
        return OUTPUT_DIR.resolve()
    if (
        repo_candidate == REPO_ROOT
        or REPO_ROOT in repo_candidate.parents
        or repo_resolved == root_resolved
        or root_resolved in repo_resolved.parents
    ):
        raise ReplayValidationError("repository output_dir must be the sealed output directory")
    temp_match = _allowed_temp_output_dir(candidate)
    if temp_match is not None:
        require_non_symlink_leaf(path=temp_match, field="output_dir")
        if candidate.exists() and not candidate.is_dir():
            raise ValueError("output_dir must be a directory")
        return temp_match
    raise ValueError(
        "output_dir must stay inside the sealed output directory or an allowlisted system temp root"
    )
