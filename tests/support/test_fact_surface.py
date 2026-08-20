from __future__ import annotations

from pathlib import Path

from tests.support.fact_surface import (
    check_fact_surface,
    extract_test_paths,
    load_evidence_rows,
    load_fact_rows,
    parse_markdown_tables,
)


def test_parse_markdown_tables_reads_header_and_rows() -> None:
    text = """
# Title

| Evidence ID | Lifecycle |
|-------------|---------|
| EV-X | Pending: V1 |
| EV-Y | Required |
"""
    tables = parse_markdown_tables(text)
    assert len(tables) == 1
    assert tables[0][0]["Evidence ID"] == "EV-X"
    assert tables[0][1]["Lifecycle"] == "Required"


def test_extract_test_paths_from_pytest_command() -> None:
    command = "`uv run pytest tests/facts/test_hybrid_search.py tests/support/foo.py -q`"
    assert extract_test_paths(command) == (
        "tests/facts/test_hybrid_search.py",
        "tests/support/foo.py",
    )


def test_required_missing_path_fails(tmp_path: Path) -> None:
    ledger = tmp_path / "fact-ledger.md"
    evidence = tmp_path / "evidence-index.md"
    ledger.write_text(
        """
| Fact ID | Lifecycle | Evidence |
|---------|-----------|----------|
| F.ONE.v1 | Proposed | EV-X |
""",
        encoding="utf-8",
    )
    evidence.write_text(
        """
| Evidence ID | Facts | Path / Command | Lifecycle |
|-------------|-------|----------------|-----------|
| EV-X | F.ONE.v1 | `uv run pytest tests/facts/missing.py -q` | Required |
""",
        encoding="utf-8",
    )
    violations = check_fact_surface(repo_root=tmp_path, ledger_path=ledger, evidence_path=evidence)
    assert any("missing.py" in item for item in violations)


def test_pending_missing_path_is_allowed(tmp_path: Path) -> None:
    ledger = tmp_path / "fact-ledger.md"
    evidence = tmp_path / "evidence-index.md"
    ledger.write_text(
        """
| Fact ID | Lifecycle | Evidence |
|---------|-----------|----------|
| F.ONE.v1 | Proposed | EV-X |
""",
        encoding="utf-8",
    )
    evidence.write_text(
        """
| Evidence ID | Facts | Path / Command | Lifecycle |
|-------------|-------|----------------|-----------|
| EV-X | F.ONE.v1 | `uv run pytest tests/facts/missing.py -q` | Pending: V1 |
""",
        encoding="utf-8",
    )
    assert check_fact_surface(repo_root=tmp_path, ledger_path=ledger, evidence_path=evidence) == []


def test_all_required_evidence_cannot_leave_fact_proposed(tmp_path: Path) -> None:
    existing = tmp_path / "tests" / "facts"
    existing.mkdir(parents=True)
    (existing / "present.py").write_text("# ok\n", encoding="utf-8")
    ledger = tmp_path / "fact-ledger.md"
    evidence = tmp_path / "evidence-index.md"
    ledger.write_text(
        """
| Fact ID | Lifecycle | Evidence |
|---------|-----------|----------|
| F.ONE.v1 | Proposed | EV-X |
""",
        encoding="utf-8",
    )
    evidence.write_text(
        """
| Evidence ID | Facts | Path / Command | Lifecycle |
|-------------|-------|----------------|-----------|
| EV-X | F.ONE.v1 | `uv run pytest tests/facts/present.py -q` | Required |
""",
        encoding="utf-8",
    )
    violations = check_fact_surface(repo_root=tmp_path, ledger_path=ledger, evidence_path=evidence)
    assert any("still Proposed" in item for item in violations)


def test_active_fact_requires_required_evidence(tmp_path: Path) -> None:
    ledger = tmp_path / "fact-ledger.md"
    evidence = tmp_path / "evidence-index.md"
    ledger.write_text(
        """
| Fact ID | Lifecycle | Evidence |
|---------|-----------|----------|
| F.ONE.v1 | Active | EV-X |
""",
        encoding="utf-8",
    )
    evidence.write_text(
        """
| Evidence ID | Facts | Path / Command | Lifecycle |
|-------------|-------|----------------|-----------|
| EV-X | F.ONE.v1 | `uv run pytest tests/facts/missing.py -q` | Pending: V1 |
""",
        encoding="utf-8",
    )
    violations = check_fact_surface(repo_root=tmp_path, ledger_path=ledger, evidence_path=evidence)
    assert any("Active fact has no Required evidence" in item for item in violations)


def test_real_ledgers_parse_and_satisfy_current_rules() -> None:
    facts = load_fact_rows()
    evidence = load_evidence_rows()
    assert facts, "fact-ledger.md main table must parse"
    assert evidence, "evidence-index.md main table must parse"
    assert {row.lifecycle for row in facts} <= {"Proposed", "Active"}
    assert all(
        row.lifecycle == "Required" or row.lifecycle.startswith("Pending:") for row in evidence
    )
    assert check_fact_surface() == []
