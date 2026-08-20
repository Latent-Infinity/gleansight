"""AST scanner: domain and use-case modules must not import provider SDKs."""

from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORTS = frozenset({"docling", "lancedb", "sentence_transformers", "httpx"})
NSQD_FORBIDDEN_IMPORT_PREFIXES = ("papers.infra",)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TREES = (
    REPO_ROOT / "src" / "papers" / "domain",
    REPO_ROOT / "src" / "papers" / "app" / "use_cases",
    REPO_ROOT / "src" / "nsqd" / "domain",
    REPO_ROOT / "src" / "nsqd" / "app",
)


def _imported_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module]
    return []


def scan_tree(root: Path) -> list[str]:
    leaks: list[str] = []
    if not root.exists():
        return [f"{root}: tree does not exist"]
    is_nsqd_tree = "nsqd" in root.parts
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for name in _imported_modules(node):
                provider_leak = name.split(".", 1)[0] in FORBIDDEN_IMPORTS
                nsqd_leak = is_nsqd_tree and any(
                    name == prefix or name.startswith(f"{prefix}.")
                    for prefix in NSQD_FORBIDDEN_IMPORT_PREFIXES
                )
                if provider_leak or nsqd_leak:
                    lineno = getattr(node, "lineno", 0)
                    leaks.append(f"{path}:{lineno} imports {name}")
    return leaks


def scan_trees(trees: tuple[Path, ...] = DEFAULT_TREES) -> list[str]:
    leaks: list[str] = []
    for tree in trees:
        leaks.extend(scan_tree(tree))
    return leaks
