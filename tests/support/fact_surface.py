"""Parse the fact ledger and evidence index and apply Lifecycle coupling rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = REPO_ROOT / "docs" / "fact-ledger.md"
DEFAULT_EVIDENCE = REPO_ROOT / "docs" / "evidence-index.md"

_PENDING = re.compile(r"^Pending:\s*(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class EvidenceRow:
    evidence_id: str
    fact_ids: tuple[str, ...]
    command: str
    lifecycle: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class FactRow:
    fact_id: str
    lifecycle: str
    evidence_ids: tuple[str, ...]


def parse_markdown_tables(text: str) -> list[list[dict[str, str]]]:
    tables: list[list[dict[str, str]]] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if "|" in lines[index] and index + 1 < len(lines) and _is_sep_row(lines[index + 1]):
            header = _split_row(lines[index])
            index += 2
            rows: list[dict[str, str]] = []
            while index < len(lines) and "|" in lines[index] and not _is_sep_row(lines[index]):
                cells = _split_row(lines[index])
                if len(cells) == len(header):
                    rows.append(dict(zip(header, cells, strict=True)))
                index += 1
            tables.append(rows)
            continue
        index += 1
    return tables


def _is_sep_row(line: str) -> bool:
    body = line.strip().strip("|")
    if not body or "|" not in line:
        return False
    return all(re.fullmatch(r":?-{3,}:?", part.strip()) for part in body.split("|") if part.strip())


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def extract_test_paths(command: str) -> tuple[str, ...]:
    tokens = re.findall(r"`([^`]+)`|(\S+)", command)
    found: list[str] = []
    for quoted, bare in tokens:
        token = quoted or bare
        for part in token.split():
            if part.startswith("tests/") and part.endswith(".py"):
                found.append(part)
    return tuple(found)


def load_evidence_rows(path: Path = DEFAULT_EVIDENCE) -> list[EvidenceRow]:
    rows: list[EvidenceRow] = []
    for table in parse_markdown_tables(path.read_text(encoding="utf-8")):
        if not table or "Evidence ID" not in table[0]:
            continue
        for raw in table:
            command = raw.get("Path / Command", "")
            fact_ids = tuple(
                part.strip() for part in raw.get("Facts", "").split(",") if part.strip()
            )
            rows.append(
                EvidenceRow(
                    evidence_id=raw["Evidence ID"],
                    fact_ids=fact_ids,
                    command=command,
                    lifecycle=raw.get("Lifecycle", "").strip(),
                    paths=extract_test_paths(command),
                )
            )
    return rows


def load_fact_rows(path: Path = DEFAULT_LEDGER) -> list[FactRow]:
    rows: list[FactRow] = []
    for table in parse_markdown_tables(path.read_text(encoding="utf-8")):
        if not table or "Fact ID" not in table[0] or "Evidence" not in table[0]:
            continue
        for raw in table:
            evidence_ids = tuple(
                part.strip() for part in raw.get("Evidence", "").split(",") if part.strip()
            )
            rows.append(
                FactRow(
                    fact_id=raw["Fact ID"],
                    lifecycle=raw.get("Lifecycle", "").strip(),
                    evidence_ids=evidence_ids,
                )
            )
    return rows


def check_fact_surface(
    *,
    repo_root: Path = REPO_ROOT,
    ledger_path: Path | None = None,
    evidence_path: Path | None = None,
) -> list[str]:
    """Return human-readable violations. Empty list means the surface is consistent."""
    evidence = load_evidence_rows(evidence_path or DEFAULT_EVIDENCE)
    facts = load_fact_rows(ledger_path or DEFAULT_LEDGER)
    evidence_by_id = {row.evidence_id: row for row in evidence}
    violations: list[str] = []

    for row in evidence:
        required = row.lifecycle.casefold() == "required"
        pending = _PENDING.match(row.lifecycle) is not None
        if not required and not pending:
            violations.append(
                f"{row.evidence_id}: Lifecycle must be 'Required' or 'Pending: <phase>', "
                f"got {row.lifecycle!r}"
            )
            continue
        if not required:
            continue
        if not row.paths:
            violations.append(f"{row.evidence_id}: Required evidence has no tests/*.py path")
            continue
        for rel in row.paths:
            if not (repo_root / rel).is_file():
                violations.append(f"{row.evidence_id}: Required path missing: {rel}")

    for fact in facts:
        bound = [evidence_by_id[eid] for eid in fact.evidence_ids if eid in evidence_by_id]
        missing_ids = [eid for eid in fact.evidence_ids if eid not in evidence_by_id]
        if missing_ids:
            violations.append(f"{fact.fact_id}: unknown evidence ids {missing_ids}")
        if not bound:
            if fact.lifecycle.casefold() == "active":
                violations.append(f"{fact.fact_id}: Active fact has no Required evidence")
            continue
        all_required = all(item.lifecycle.casefold() == "required" for item in bound)
        any_required = any(item.lifecycle.casefold() == "required" for item in bound)
        if all_required and fact.lifecycle.casefold() == "proposed":
            violations.append(
                f"{fact.fact_id}: all evidence is Required but fact Lifecycle is still Proposed"
            )
        if fact.lifecycle.casefold() == "active" and not any_required:
            violations.append(f"{fact.fact_id}: Active fact has no Required evidence")

    return violations
