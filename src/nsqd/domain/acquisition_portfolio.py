from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Target = Literal["calibration", "production_valid"]


@dataclass(frozen=True, slots=True)
class PortfolioError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PortfolioCaps(Contract):
    max_deficits: int = Field(default=12, ge=1, le=50)
    max_queries: int = Field(default=12, ge=1, le=50)
    max_sources: int = Field(default=6, ge=1, le=50)
    per_deficit_sources: int = Field(default=2, ge=1, le=10)
    candidates_per_query: int = Field(default=25, ge=1, le=25)


class RecallDeficit(Contract):
    probe_id: Text
    source: Text
    record_type: Text


class SearchContext(Contract):
    missing_cell_ids: tuple[Text, ...]
    missing_recall_probes: tuple[RecallDeficit, ...]
    unmet_record_types: tuple[Text, ...]
    domain_minima_unmet: bool


class SufficiencyObservation(Contract):
    snapshot_id: Text
    domain_policy_id: Text
    target: Target
    state: Text
    failures: tuple[Text, ...]
    search_context: SearchContext


class Deficit(Contract):
    deficit_id: Digest
    failure: Literal["expected_cell_empty", "recall_probe_missing", "domain_minima_unmet"]
    cell_id: Text | None = None
    probe_id: Text | None = None
    source: Text | None = None
    record_type: Text


class PortfolioQuery(Contract):
    query_id: Digest
    text: Text
    record_type: Text
    target_ids: tuple[Digest, ...]


class AcquisitionPortfolio(Contract):
    portfolio_id: Digest
    before: SufficiencyObservation
    route: Literal["manual", "search", "stop"]
    caps: PortfolioCaps
    deficits: tuple[Deficit, ...]
    queries: tuple[PortfolioQuery, ...]
    omitted_deficits: int = Field(ge=0)
    grants_approval: Literal[False] = False


class SourceBinding(Contract):
    source_paper_id: Text
    paper_id: Text
    query_ids: tuple[Digest, ...]
    target_ids: tuple[Digest, ...]
    draft: dict[str, JsonValue]


class RetrievalBinding(Contract):
    query_id: Digest
    target_ids: tuple[Digest, ...]
    discovered_source_ids: tuple[Text, ...]
    shortlisted_source_ids: tuple[Text, ...]


class StagedPortfolio(Contract):
    plan: AcquisitionPortfolio
    retrievals: tuple[RetrievalBinding, ...]
    sources: tuple[SourceBinding, ...]
    grants_approval: Literal[False] = False


def digest_json(value: JsonValue) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def model_digest(value: BaseModel) -> str:
    return digest_json(value.model_dump(mode="json"))
