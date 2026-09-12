from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXCEPTIONS_PATH = REPO_ROOT / "docs" / "reviews" / "hash-bound-format-exceptions.json"
CHECKER_PATH = REPO_ROOT / "scripts" / "check_hash_bound_format.py"
EXPECTED_EXCEPTIONS = [
    {
        "path": "docs/reviews/nsqd-operator-c-evidence-2026-09-08/README.md",
        "sha256": "0bda7dd5c053a528312eb199b80ae4f4138f94b199f71dc5d8d2189891b771a7",
        "trailing_whitespace_line_count": 1,
    },
    {
        "path": "docs/reviews/nsqd-operator-c-evidence-2026-09-09-resolution/README.md",
        "sha256": "34d5d5391ddaf0afbe4c7a6ae1973b7fc91620a496e95e03096635ad2f28cd0c",
        "trailing_whitespace_line_count": 4,
    },
    {
        "path": "docs/reviews/nsqd-operator-c-evidence-resolution-2026-09-09/README.md",
        "sha256": "213382cf673e63049d941bbf3e37b461a6bad48ff91c25f595ed91df6993bd36",
        "trailing_whitespace_line_count": 4,
    },
]


def _checker():
    assert CHECKER_PATH.is_file()
    spec = importlib.util.spec_from_file_location("hash_bound_format_checker", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exception_inventory_is_exact_and_validates_repository() -> None:
    payload = json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))
    assert payload == {"schema_version": 1, "exceptions": EXPECTED_EXCEPTIONS}
    _checker().validate_exception_inventory(REPO_ROOT, EXCEPTIONS_PATH)


@pytest.mark.parametrize("field", ("sha256", "trailing_whitespace_line_count"))
def test_exception_validator_rejects_changed_digest_or_count(tmp_path: Path, field: str) -> None:
    exceptions = [dict(item) for item in EXPECTED_EXCEPTIONS]
    exceptions[0][field] = "0" * 64 if field == "sha256" else 2
    payload = {"schema_version": 1, "exceptions": exceptions}
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="digest|count"):
        _checker().validate_exception_inventory(REPO_ROOT, path)


def test_exception_validator_rejects_unlisted_violation(tmp_path: Path) -> None:
    violating = tmp_path / "unlisted.md"
    violating.write_bytes(b"unlisted trailing space \n")

    with pytest.raises(ValueError, match="unlisted trailing whitespace"):
        _checker().validate_paths(REPO_ROOT, EXCEPTIONS_PATH, (violating,))
