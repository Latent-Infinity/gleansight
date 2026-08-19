"""AST scanner: domain and use-case modules must not import provider SDKs."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORTS = frozenset({"docling", "lancedb", "sentence_transformers", "httpx"})
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TREES = (
    REPO_ROOT / "src" / "papers" / "domain",
    REPO_ROOT / "src" / "papers" / "app" / "use_cases",
)


def _imported_roots(node: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(node, ast.Import):
        names.extend(alias.name.split(".", 1)[0] for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        names.append(node.module.split(".", 1)[0])
    return names


def scan_tree(root: Path) -> list[str]:
    leaks: list[str] = []
    if not root.exists():
        return [f"{root}: tree does not exist"]
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for name in _imported_roots(node):
                if name in FORBIDDEN_IMPORTS:
                    lineno = getattr(node, "lineno", 0)
                    leaks.append(f"{path}:{lineno} imports {name}")
    return leaks


def scan_trees(trees: tuple[Path, ...] = DEFAULT_TREES) -> list[str]:
    leaks: list[str] = []
    for tree in trees:
        leaks.extend(scan_tree(tree))
    return leaks
