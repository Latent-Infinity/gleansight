from __future__ import annotations

import re
from pathlib import Path

APPROVED = Path(__file__).resolve().parents[1] / "fixtures" / "approved"

_PATTERNS = (
    re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
)


def test_approved_fixtures_have_no_secret_regex_hits() -> None:
    hits: list[str] = []
    for path in sorted(APPROVED.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".md", ".toml", ".yaml", ".yml", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in _PATTERNS:
                if pattern.search(line):
                    hits.append(f"{path.relative_to(APPROVED)}:{lineno}:{line.strip()}")
    assert hits == []
