from __future__ import annotations

from typing import Any

REQUIRED_CARD_FIELDS = (
    "card_id",
    "cell_id",
    "title",
    "generating_operator",
    "snapshot_id",
    "corpus_version",
    "viability",
    "nov",
    "mech",
    "fals",
    "dpred",
    "dval",
    "candidate_artifact_hash",
    "card_decision",
)


def missing_card_fields(card: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_CARD_FIELDS:
        if field not in card or card[field] is None or card[field] == "":
            missing.append(field)
    return missing


def corpus_ingest_rejection(payload: dict[str, Any]) -> str | None:
    if payload.get("kind") == "candidate-requirement-card":
        return "requirement-card is not a corpus record"
    return None


def card_decision(viability: int) -> str:
    return "rejected" if viability <= 0 else "accepted"


def needs_re_score(*, card_snapshot_id: str, current_snapshot_id: str) -> bool:
    return card_snapshot_id != current_snapshot_id
