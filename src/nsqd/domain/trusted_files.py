from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

MAX_VERIFIED_REPO_TEXT_BYTES = 8 * 1024 * 1024


def read_verified_repo_file(
    *,
    repo_root: Path,
    relative_path: Path,
    expected_root: Path,
    field: str,
    max_bytes: int | None = None,
) -> bytes:
    if relative_path.is_absolute() or expected_root.is_absolute():
        raise ValueError(f"{field} is outside the approved root")
    if ".." in relative_path.parts or ".." in expected_root.parts:
        raise ValueError(f"{field} is outside the approved root")
    repo_root_path = repo_root.resolve(strict=False)
    candidate_path = repo_root_path / relative_path
    expected_root_path = repo_root_path / expected_root
    try:
        candidate_path.relative_to(expected_root_path)
    except ValueError as exc:
        raise ValueError(f"{field} is outside the approved root") from exc
    if expected_root_path.exists() and expected_root_path.is_symlink():
        raise ValueError(f"{field} must not resolve through a symlink")
    require_non_symlink_path_within_root(path=candidate_path, root=expected_root_path, field=field)
    require_non_symlink_leaf(path=candidate_path, field=field)
    if not candidate_path.exists():
        raise ValueError(f"{field} is missing")
    if not candidate_path.is_file():
        raise ValueError(f"{field} must be a regular file")
    raw_bytes = candidate_path.read_bytes()
    if max_bytes is not None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if len(raw_bytes) > max_bytes:
            raise ValueError(f"{field} exceeds the verified byte limit")
    return raw_bytes


def read_verified_repo_text(
    *,
    repo_root: Path,
    relative_path: Path,
    expected_root: Path,
    field: str,
    max_bytes: int = MAX_VERIFIED_REPO_TEXT_BYTES,
) -> str:
    raw_bytes = read_verified_repo_file(
        repo_root=repo_root,
        relative_path=relative_path,
        expected_root=expected_root,
        field=field,
        max_bytes=max_bytes,
    )
    if len(raw_bytes) > max_bytes:
        raise ValueError(f"{field} exceeds the verified byte limit")
    return raw_bytes.decode("utf-8")


def require_non_symlink_path(path: Path, *, field: str) -> None:
    absolute = path if path.is_absolute() else path.resolve(strict=False)
    current = Path(absolute.anchor) if absolute.anchor else Path(".")
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for part in parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"{field} must not resolve through a symlink")


def require_non_symlink_descendants_within_root(*, path: Path, root: Path, field: str) -> None:
    absolute = path if path.is_absolute() else path.resolve(strict=False)
    root_absolute = root if root.is_absolute() else root.resolve(strict=False)
    try:
        relative = absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise ValueError(f"{field} is outside the approved root") from exc
    current = root_absolute
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"{field} must not resolve through a symlink")


def require_non_symlink_path_within_root(*, path: Path, root: Path, field: str) -> None:
    absolute = path.resolve(strict=False) if not path.is_absolute() else path
    root_absolute = root.resolve(strict=False) if not root.is_absolute() else root
    try:
        relative = absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise ValueError(f"{field} is outside the approved root") from exc
    current = root_absolute
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"{field} must not resolve through a symlink")


def require_non_symlink_leaf(*, path: Path, field: str) -> None:
    if path.exists() and path.is_symlink():
        raise ValueError(f"{field} must not be a symlink")


def load_verified_yaml_mapping(
    *,
    repo_root: Path,
    relative_path: Path,
    expected_root: Path,
    field: str,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    import yaml

    raw_bytes = read_verified_repo_file(
        repo_root=repo_root,
        relative_path=relative_path,
        expected_root=expected_root,
        field=field,
        max_bytes=max_bytes,
    )
    loaded = yaml.safe_load(raw_bytes.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("projection binding must load a YAML mapping")
    return {str(key): item for key, item in loaded.items()}


def sha256_file_digest(path: Path, *, max_bytes: int, chunk_size: int = 1024 * 1024) -> str:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("sqlite exceeds the verified byte limit")
            digest.update(chunk)
    return digest.hexdigest()
