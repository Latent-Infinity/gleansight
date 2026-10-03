"""Reconcile DOI and provider identities while retaining immutable observations."""

import hashlib
import json
import sqlite3
from dataclasses import dataclass

from pydantic import TypeAdapter

from papers.domain.errors import ConflictError
from papers.domain.screening import Observation, SearchResult


def canonical_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "http://dx.doi.org/",
        "https://dx.doi.org/",
        "doi:",
    ):
        normalized = normalized.removeprefix(prefix).strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class Reconciler:
    connection: sqlite3.Connection

    def observe(self, item: SearchResult, previous: tuple[Observation, ...]) -> Observation:
        doi = canonical_doi(
            next((v for k, v in (item.external_ids or {}).items() if k.lower() == "doi"), None)
        )
        alias = self.connection.execute(
            "SELECT candidate_id FROM screening_aliases WHERE source = ? AND source_paper_id = ?",
            ("semantic_scholar", item.source_paper_id),
        ).fetchone()
        identity = (
            self.connection.execute(
                "SELECT candidate_id FROM screening_identities WHERE doi = ?", (doi,)
            ).fetchone()
            if doi
            else None
        )
        if alias is not None and identity is not None and alias[0] != identity[0]:
            raise ConflictError("Provider identity conflicts with an existing canonical DOI.")
        source = self.connection.execute(
            "SELECT candidate_id FROM candidates WHERE source = ? AND source_paper_id = ?",
            ("semantic_scholar", item.source_paper_id),
        ).fetchone()
        candidate_id = str((alias or identity or source)[0])
        if alias is None and identity is None and doi:
            for identifier, encoded in self.connection.execute(
                "SELECT candidate_id, external_ids_json FROM candidates "
                "WHERE external_ids_json IS NOT NULL ORDER BY imported_paper_id "
                "IS NULL, created_at, candidate_id"
            ):
                ids = TypeAdapter(dict[str, str]).validate_json(encoded)
                if any(k.lower() == "doi" and canonical_doi(v) == doi for k, v in ids.items()):
                    candidate_id = str(identifier)
                    break
        current = self.connection.execute(
            "SELECT doi FROM screening_identities WHERE candidate_id = ?", (candidate_id,)
        ).fetchone()
        if current is not None and current[0] is not None and doi and current[0] != doi:
            raise ConflictError("A known provider identity changed its canonical DOI.")
        self.connection.execute(
            "INSERT INTO screening_identities(candidate_id, doi) VALUES (?, ?) "
            "ON CONFLICT(candidate_id) DO UPDATE SET doi = "
            "COALESCE(screening_identities.doi, excluded.doi)",
            (candidate_id, doi),
        )
        self.connection.execute(
            "INSERT INTO screening_aliases VALUES (?, ?, ?, ?) ON "
            "CONFLICT(source, source_paper_id) "
            "DO NOTHING",
            ("semantic_scholar", item.source_paper_id, candidate_id, item.model_dump_json()),
        )
        external_ids = dict(item.external_ids or {})
        if doi:
            external_ids = {k: v for k, v in external_ids.items() if k.lower() != "doi"}
            external_ids["DOI"] = doi
        self.connection.execute(
            "UPDATE candidates SET title=?, year=?, venue=?, authors_json=?, abstract=?, "
            "external_ids_json=? WHERE candidate_id=?",
            (
                item.title,
                item.year,
                item.venue,
                json.dumps(item.authors),
                item.abstract,
                json.dumps(external_ids),
                candidate_id,
            ),
        )
        comparable = item.model_dump(mode="json", exclude={"source_paper_id", "external_ids"})
        comparable["doi"] = doi
        comparable["external_ids"] = {
            key.casefold(): doi if key.casefold() == "doi" else value
            for key, value in (item.external_ids or {}).items()
            if key.casefold() not in {"semanticscholar", "corpusid"}
        }
        fingerprint = hashlib.sha256(json.dumps(comparable, sort_keys=True).encode()).hexdigest()
        prior = next((old for old in reversed(previous) if old.candidate_id == candidate_id), None)
        return Observation(
            candidate_id=candidate_id,
            source="semantic_scholar",
            source_paper_id=item.source_paper_id,
            doi=doi,
            metadata=item,
            metadata_sha256=fingerprint,
            delta="new"
            if prior is None
            else "seen"
            if prior.metadata_sha256 == fingerprint
            else "metadata_changed",
        )
