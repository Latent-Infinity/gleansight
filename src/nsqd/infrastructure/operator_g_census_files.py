from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from nsqd.domain.operator_g_census import CensusIssue

ROOTS: Final = ("docs", "src", "tests")
STRUCTURED_SUFFIXES: Final = (".json", ".jsonl", ".toml", ".yaml", ".yml")
SYNTHETIC_FIXTURE: Final = "tests/nsqd/operator_dg_contract_support.py"
OUTPUT_DIRECTORIES: Final = frozenset(
    {
        "docs/reviews/nsqd-operator-g-readiness-census-2026-09-12-schema-closure",
    }
)


@dataclass(frozen=True, slots=True)
class CensusLimits:
    max_files: int = 10_000
    max_file_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024
    max_depth: int = 64
    max_structured_depth: int = 64


@dataclass(frozen=True, slots=True)
class ScannedFile:
    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class SafeReadError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


DEFAULT_LIMITS: Final = CensusLimits()


def discover(root: Path, limits: CensusLimits) -> tuple[list[ScannedFile], list[CensusIssue]]:
    files: list[ScannedFile] = []
    issues: list[CensusIssue] = []
    total_bytes = 0
    if root.is_symlink() or not root.is_dir():
        return [], [CensusIssue(".", "unsafe_repository_root")]
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        return [], [CensusIssue(".", "no_follow_reads_unsupported")]
    for scope in ROOTS:
        scope_path = root / scope
        if scope_path.is_symlink() or not scope_path.is_dir():
            issues.append(CensusIssue(scope, "missing_or_unsafe_scope_root"))
            continue
        for relative in _walk(scope_path, root, limits.max_depth, issues):
            if not _eligible(relative):
                continue
            if len(files) >= limits.max_files:
                issues.append(CensusIssue(relative, "file_count_limit_exceeded"))
                continue
            try:
                content = _read_nofollow(root, relative, limits.max_file_bytes)
            except SafeReadError as error:
                issues.append(CensusIssue(relative, error.reason))
                continue
            if total_bytes + len(content) > limits.max_total_bytes:
                issues.append(CensusIssue(relative, "total_size_limit_exceeded"))
                continue
            total_bytes += len(content)
            files.append(ScannedFile(relative, content, hashlib.sha256(content).hexdigest()))
    files.sort(key=lambda item: item.path)
    return files, issues


def read_trusted_evidence_paths(
    root: Path, paths: Iterable[str], limits: CensusLimits
) -> Mapping[str, frozenset[str]]:
    if (
        root.is_symlink()
        or not root.is_dir()
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
    ):
        return {}
    available: dict[str, set[str]] = {}
    total_bytes = 0
    for index, relative in enumerate(sorted(set(paths))):
        path = PurePosixPath(relative)
        if (
            index >= limits.max_files
            or not path.parts
            or path.parts[0] not in ROOTS
            or len(path.parts) - 1 > limits.max_depth
            or _excluded(relative)
        ):
            continue
        try:
            content = _read_nofollow(root, relative, limits.max_file_bytes)
        except SafeReadError:
            continue
        if total_bytes + len(content) > limits.max_total_bytes:
            continue
        total_bytes += len(content)
        digest = hashlib.sha256(content).hexdigest()
        available.setdefault(digest, set()).add(relative)
    return {digest: frozenset(found_paths) for digest, found_paths in available.items()}


def _walk(directory: Path, root: Path, max_depth: int, issues: list[CensusIssue]) -> Iterator[str]:
    relative = directory.relative_to(root)
    if len(relative.parts) > max_depth:
        issues.append(CensusIssue(relative.as_posix(), "depth_limit_exceeded"))
        return
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError:
        issues.append(CensusIssue(relative.as_posix(), "unreadable_directory"))
        return
    for entry in entries:
        child = Path(entry.path).relative_to(root).as_posix()
        if _excluded(child):
            continue
        if entry.is_symlink():
            issues.append(CensusIssue(child, "symlink_in_scope"))
        elif entry.is_dir(follow_symlinks=False):
            yield from _walk(Path(entry.path), root, max_depth, issues)
        elif entry.is_file(follow_symlinks=False):
            yield child


def _eligible(relative: str) -> bool:
    return (
        PurePosixPath(relative).suffix.lower() in STRUCTURED_SUFFIXES
        or relative == SYNTHETIC_FIXTURE
    )


def _excluded(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    excluded_parts = {
        ".omo",
        ".playwright-mcp",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
    }
    return bool(set(parts) & excluded_parts) or any(
        relative == output or relative.startswith(f"{output}/") for output in OUTPUT_DIRECTORIES
    )


def _read_nofollow(root: Path, relative: str, max_bytes: int) -> bytes:
    descriptors: list[int] = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(directory)
        parts = PurePosixPath(relative).parts
        for component in parts[:-1]:
            directory = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory,
            )
            descriptors.append(directory)
        file_descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        descriptors.append(file_descriptor)
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SafeReadError("non_regular_file")
        content = _read_bounded(file_descriptor, max_bytes)
        after = os.fstat(file_descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if identity_before != identity_after or len(content) != after.st_size:
            raise SafeReadError("file_changed_during_read")
        return content
    except OSError as error:
        raise SafeReadError("unsafe_nofollow_read") from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_bounded(file_descriptor: int, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(file_descriptor, min(1024 * 1024, max_bytes + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise SafeReadError("file_size_limit_exceeded")
