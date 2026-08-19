from __future__ import annotations

from pathlib import Path

from tests.support.import_boundary import DEFAULT_TREES, scan_tree, scan_trees


def test_scanner_fails_on_isolated_domain_importing_lancedb(tmp_path: Path) -> None:
    package = tmp_path / "domain"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaky.py").write_text("import lancedb\n", encoding="utf-8")
    leaks = scan_tree(package)
    assert leaks, "scanner must report a domain module that imports lancedb"
    assert any("lancedb" in item for item in leaks)


def test_real_domain_and_use_cases_have_no_provider_imports() -> None:
    assert DEFAULT_TREES[0].is_dir()
    assert DEFAULT_TREES[1].is_dir()
    assert scan_trees() == []
