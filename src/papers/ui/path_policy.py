from __future__ import annotations

from pathlib import Path

from nsqd.domain.trusted_files import require_non_symlink_path

_PROTECTED_REPO_PATHS = (Path(".env"), Path(".omo"), Path("data"), Path("evidence/archive"))


def resolve_ui_input(raw_path: str, *, repo_root: Path, field: str) -> Path:
    candidate = _resolve_existing_file(raw_path, repo_root=repo_root, field=field)
    _reject_protected_repo_path(candidate, repo_root=repo_root, field=field)
    return candidate


def resolve_report_input(raw_path: str, *, repo_root: Path, field: str) -> Path:
    candidate = _resolve_existing_file(raw_path, repo_root=repo_root, field=field)
    _require_output_path(candidate, repo_root=repo_root, field=field)
    return candidate


def resolve_report_bundle(raw_path: str, *, repo_root: Path, field: str) -> Path:
    candidate = _resolve_existing_path(raw_path, repo_root=repo_root, field=field)
    if not candidate.is_dir():
        raise ValueError(f"{field} must be a directory")
    _require_output_path(candidate, repo_root=repo_root, field=field)
    return candidate


def _require_output_path(candidate: Path, *, repo_root: Path, field: str) -> None:
    output_root = (repo_root / "output").resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(f"{field} must be inside output/") from exc


def resolve_report_output(raw_path: str, *, repo_root: Path, field: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    candidate = candidate.resolve(strict=False)
    output_root = (repo_root / "output").resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError as exc:
        raise ValueError(f"{field} must be inside output/") from exc
    require_non_symlink_path(candidate, field=field)
    return candidate


def _resolve_existing_file(raw_path: str, *, repo_root: Path, field: str) -> Path:
    resolved = _resolve_existing_path(raw_path, repo_root=repo_root, field=field)
    if not resolved.is_file():
        raise ValueError(f"{field} must be a regular file")
    return resolved


def _resolve_existing_path(raw_path: str, *, repo_root: Path, field: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    require_non_symlink_path(candidate, field=field)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{field} is missing or unreadable") from exc
    return resolved


def _reject_protected_repo_path(candidate: Path, *, repo_root: Path, field: str) -> None:
    resolved_root = repo_root.resolve()
    for protected in _PROTECTED_REPO_PATHS:
        protected_path = (resolved_root / protected).resolve()
        if candidate == protected_path or protected_path in candidate.parents:
            raise ValueError(f"{field} is protected")
