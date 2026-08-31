from __future__ import annotations

from typing import Any

REQUIRED_CARD_FIELDS = (
    "card_id",
    "domain_policy_id",
    "cell_id",
    "archive_cell_key",
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


def needs_re_score(
    *,
    card_snapshot_id: str,
    current_snapshot_id: str,
    card_tau: float | None = None,
    current_tau: float | None = None,
    compare_tau: bool = False,
) -> bool:
    if card_snapshot_id != current_snapshot_id:
        return True
    if not compare_tau:
        return False
    return _novelty_tau_mismatch(card_tau=card_tau, current_tau=current_tau)


def _novelty_tau_mismatch(*, card_tau: float | None, current_tau: float | None) -> bool:
    if current_tau is None:
        return False
    if card_tau is None:
        return True
    return float(card_tau) != float(current_tau)


def novelty_tau_stamp(artifact: dict[str, Any] | None) -> tuple[bool, float | None]:
    if artifact is None:
        return False, None
    novelty = artifact.get("novelty")
    if not isinstance(novelty, dict) or "tau" not in novelty:
        return False, None
    tau = novelty["tau"]
    if tau is None or isinstance(tau, bool) or not isinstance(tau, (int, float)):
        return True, None
    return True, float(tau)
