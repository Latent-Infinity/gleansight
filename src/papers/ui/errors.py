from __future__ import annotations

import re
from pathlib import Path

_SECRET_ASSIGNMENT = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*([^\s,;]+)")


def public_ui_error(exc: Exception) -> str:
    message = str(exc).strip() or "operation failed"
    for path, replacement in ((Path.cwd(), "<repo>"), (Path.home(), "<home>")):
        path_text = str(path)
        if path_text:
            message = message.replace(path_text, replacement)
    return _SECRET_ASSIGNMENT.sub(r"\1=<redacted>", message)
