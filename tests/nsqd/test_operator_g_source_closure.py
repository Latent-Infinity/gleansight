from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from nsqd.domain.operator_g_census import CensusStatus
from nsqd.domain.operator_g_readiness import readiness_source_bindings
from nsqd.infrastructure.operator_g_census import census_operator_g_evidence
from tests.nsqd.operator_g_census_support import census_contract, initialize_repository

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
REQUIRED_ARTIFACTS: Final = {
    "docs/reviews/nsqd-operator-g-failure-record-contract-2026-09-11-v2/"
    "failure-record-contract-v2.yaml",
    "docs/reviews/nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup/"
    "packet-manifest.json",
    "docs/reviews/nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup/"
    "technical-review-summary.json",
    "docs/reviews/nsqd-operator-g-readiness-census-2026-09-11-typed-contract-cleanup/"
    "technical-review-seal.json",
    "docs/reviews/nsqd-operator-f-readiness-2026-09-12-implementation-binding/packet-manifest.json",
    "docs/reviews/nsqd-operator-f-readiness-2026-09-12-implementation-binding/"
    "technical-review-summary.json",
    "docs/reviews/nsqd-operator-f-readiness-2026-09-12-implementation-binding/"
    "technical-review-seal.json",
    "docs/reviews/nsqd-operator-activation-2026-09-12-pointer-sync/packet-manifest.json",
    "docs/reviews/nsqd-operator-activation-2026-09-12-pointer-sync/technical-review-summary.json",
    "docs/reviews/nsqd-operator-activation-2026-09-12-pointer-sync/technical-review-seal.json",
}


def _local_module_path(module_parts: tuple[str, ...]) -> Path | None:
    for root in (REPO_ROOT / "src", REPO_ROOT):
        module_path = root.joinpath(*module_parts).with_suffix(".py")
        if module_path.is_file():
            return module_path
        package_path = root.joinpath(*module_parts, "__init__.py")
        if package_path.is_file():
            tree = ast.parse(package_path.read_text(encoding="utf-8"))
            if any(
                not isinstance(node, ast.Expr)
                or not isinstance(node.value, ast.Constant)
                or not isinstance(node.value.value, str)
                for node in tree.body
            ):
                return package_path
    return None


def _local_imports(path: Path) -> set[Path]:
    try:
        relative = path.relative_to(REPO_ROOT / "src")
    except ValueError:
        relative = path.relative_to(REPO_ROOT)
    package_parts = relative.with_suffix("").parts[:-1]
    imports: set[Path] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        targets: list[tuple[str, ...]] = []
        if isinstance(node, ast.Import):
            targets.extend(tuple(alias.name.split(".")) for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            retained = len(package_parts) - node.level + 1 if node.level else 0
            base = package_parts[:retained] if node.level else ()
            if node.module:
                base += tuple(node.module.split("."))
            targets.append(base)
            targets.extend(base + tuple(alias.name.split(".")) for alias in node.names)
        for target in targets:
            imported = _local_module_path(target)
            if imported is not None:
                imports.add(imported)
    return imports


def _transitive_local_import_closure(bound_paths: set[str]) -> set[str]:
    closure = set(bound_paths)
    pending = [REPO_ROOT / path for path in bound_paths if path.endswith(".py")]
    while pending:
        for imported in _local_imports(pending.pop()):
            relative = imported.relative_to(REPO_ROOT).as_posix()
            if relative not in closure:
                closure.add(relative)
                pending.append(imported)
    return closure


def test_g_source_bindings_cover_transitive_local_import_closure() -> None:
    bound_paths = {binding.path for binding in readiness_source_bindings(REPO_ROOT)}

    assert bound_paths == _transitive_local_import_closure(bound_paths)


def test_g_source_bindings_cover_current_contract_and_reviewed_upstream_artifacts() -> None:
    bound_paths = {binding.path for binding in readiness_source_bindings(REPO_ROOT)}

    assert REQUIRED_ARTIFACTS <= bound_paths


def test_out_of_scope_and_agent_state_are_ignored(tmp_path: Path) -> None:
    initialize_repository(tmp_path)
    (tmp_path / ".omo").mkdir()
    (tmp_path / ".omo" / "record.json").write_text('{"failure_record_id":"x"}')
    (tmp_path / "outside.json").write_text('{"failure_record_id":"x"}')
    (tmp_path / "tests" / "unrelated.py").write_text('failure_record_id = "ignored"\n')

    census = census_operator_g_evidence(tmp_path, contract=census_contract())

    assert census.status is CensusStatus.COMPLETE
    assert census.candidates == ()
