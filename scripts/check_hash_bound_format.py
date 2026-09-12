from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
EXCEPTIONS_PATH: Final = REPO_ROOT / "docs" / "reviews" / "hash-bound-format-exceptions.json"


def _trailing_whitespace_count(contents: bytes) -> int:
    return sum(1 for line in contents.splitlines() if line.endswith((b" ", b"\t")))


def _load_exceptions(path: Path) -> dict[str, tuple[str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("format exception schema is invalid")
    entries = payload.get("exceptions")
    if not isinstance(entries, list):
        raise ValueError("format exception list is invalid")
    exceptions: dict[str, tuple[str, int]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "sha256",
            "trailing_whitespace_line_count",
        }:
            raise ValueError("format exception entry is invalid")
        relative = entry["path"]
        digest = entry["sha256"]
        count = entry["trailing_whitespace_line_count"]
        if (
            not isinstance(relative, str)
            or not isinstance(digest, str)
            or not isinstance(count, int)
        ):
            raise ValueError("format exception entry types are invalid")
        if relative in exceptions:
            raise ValueError("format exception path is duplicated")
        exceptions[relative] = digest, count
    return exceptions


def validate_exception_inventory(repo_root: Path, exceptions_path: Path) -> None:
    for relative, (expected_digest, expected_count) in _load_exceptions(exceptions_path).items():
        contents = (repo_root / relative).read_bytes()
        if hashlib.sha256(contents).hexdigest() != expected_digest:
            raise ValueError(f"format exception digest mismatch: {relative}")
        if _trailing_whitespace_count(contents) != expected_count:
            raise ValueError(f"format exception count mismatch: {relative}")


def validate_paths(repo_root: Path, exceptions_path: Path, paths: Iterable[Path]) -> None:
    exceptions = _load_exceptions(exceptions_path)
    validate_exception_inventory(repo_root, exceptions_path)
    for path in paths:
        contents = path.read_bytes()
        count = _trailing_whitespace_count(contents)
        if count == 0:
            continue
        try:
            relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            relative = path.as_posix()
        expected = exceptions.get(relative)
        if expected is None:
            raise ValueError(f"unlisted trailing whitespace: {relative}")
        if expected != (hashlib.sha256(contents).hexdigest(), count):
            raise ValueError(f"format exception digest or count mismatch: {relative}")


def _changed_paths(repo_root: Path) -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMR", "--"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    relative_paths = sorted({*completed.stdout.splitlines(), *untracked.stdout.splitlines()})
    return tuple(
        repo_root / relative for relative in relative_paths if (repo_root / relative).is_file()
    )


def _validate_git_diff_check(repo_root: Path, exceptions_path: Path) -> None:
    completed = subprocess.run(
        ["git", "diff", "HEAD", "--check", "--"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    exceptions = _load_exceptions(exceptions_path)
    unexpected: list[str] = []
    skip_content = False
    for line in completed.stdout.splitlines():
        if skip_content and line.startswith("+"):
            skip_content = False
            continue
        if line.endswith(": trailing whitespace."):
            relative = line.split(":", maxsplit=1)[0]
            if relative in exceptions:
                skip_content = True
                continue
        unexpected.append(line)
    if unexpected or completed.stderr:
        details = "\n".join((*unexpected, completed.stderr.rstrip()))
        raise ValueError(f"git diff --check failed:\n{details}")


def main() -> int:
    validate_paths(REPO_ROOT, EXCEPTIONS_PATH, _changed_paths(REPO_ROOT))
    _validate_git_diff_check(REPO_ROOT, EXCEPTIONS_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
