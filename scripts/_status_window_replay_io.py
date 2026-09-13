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

from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.operator_baselines import verify_scratch_execution_receipt
from nsqd.domain.trusted_files import (
    read_verified_repo_file,
    read_verified_repo_text,
    require_non_symlink_leaf,
    require_non_symlink_path,
    require_non_symlink_path_within_root,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKET_DIR = resolve_artifact_path(
    REPO_ROOT, Path("docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01")
)
RETAINED_SOURCE_DIR = resolve_artifact_path(
    REPO_ROOT, Path("docs/reviews/nsqd-status-window-calendar-replay-2026-09-02")
)
ARTIFACT_NAME = "calendar-replay-artifact.json"
ROWS_NAME = "extracted-timestamp-rows.json"
SUMMARY_NAME = "review-summary.json"
REPORT_NAME = "report.md"
RUN_METADATA_NAME = "run-metadata.json"
MAX_PACKET_FILE_BYTES = 8 * 1024 * 1024


class ReplayValidationError(ValueError):
    pass


def _load_bytes(path: Path) -> bytes:
    absolute = path if path.is_absolute() else REPO_ROOT / path
    filesystem_root = Path(absolute.anchor)
    relative_path = absolute.relative_to(filesystem_root)
    return read_verified_repo_file(
        repo_root=filesystem_root,
        relative_path=relative_path,
        expected_root=relative_path.parent,
        field=str(path),
        max_bytes=MAX_PACKET_FILE_BYTES,
    )


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(_load_bytes(path))
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
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o666,
                dir_fd=output_descriptor,
            )
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise ReplayValidationError("output child must be a regular file")
            descriptors[name] = descriptor
        for name, content in files.items():
            descriptor = descriptors[name]
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


def _require_output_dir(path: Path) -> Path:
    expanded = path.expanduser()
    absolute = expanded if expanded.is_absolute() else REPO_ROOT / expanded
    current = Path(absolute.anchor)
    allowed_temp_aliases = {
        Path(tempfile.gettempdir()),
        Path("/tmp"),
    }
    for component in absolute.parts[1:]:
        current /= component
        if current.is_symlink() and current not in allowed_temp_aliases:
            raise ValueError("output_dir must not resolve through a symlink")
    candidate = absolute.resolve(strict=False)
    require_non_symlink_path(candidate, field="output_dir")
    require_non_symlink_leaf(path=candidate, field="output_dir")
    if not candidate.is_dir():
        raise ValueError("output_dir must be a created run directory")
    repository = REPO_ROOT.resolve()
    repository_output = repository / "output"
    if repository_output in candidate.parents:
        require_non_symlink_path_within_root(
            path=candidate, root=repository_output, field="output_dir"
        )
        return candidate
    if candidate == repository or repository in candidate.parents:
        raise ValueError("output_dir must be below repo_root/output")
    temp_root = Path(os.path.realpath(tempfile.gettempdir()))
    if temp_root in candidate.parents:
        require_non_symlink_path_within_root(path=candidate, root=temp_root, field="output_dir")
        return candidate
    raise ValueError("output_dir must be below repo_root/output or the system temporary directory")
