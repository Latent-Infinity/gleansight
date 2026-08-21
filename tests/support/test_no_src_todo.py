from __future__ import annotations

import re
from pathlib import Path

_MARKER = re.compile(r"\b(TODO|FIXME|XXX)\b")
_SRC = Path("src")


def test_src_has_no_todo_fixme_xxx_markers() -> None:
    hits: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _MARKER.search(line):
                hits.append(f"{path}:{line_no}:{line.strip()}")
    assert hits == [], "marker comments under src/:\n" + "\n".join(hits)
