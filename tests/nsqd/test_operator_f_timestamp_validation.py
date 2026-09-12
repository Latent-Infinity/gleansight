from __future__ import annotations

import pytest
from pydantic import ValidationError

from nsqd.domain.operator_f_evaluation import TrustedCorpusApproval


@pytest.mark.parametrize(
    "approved_at_utc",
    [
        "2026-99-99T99:99:99Z",
        "2026-02-29T12:00:00Z",
        "2026-04-31T12:00:00Z",
        "2026-09-09T24:00:00Z",
        "2026-09-09T23:60:00Z",
        "2026-09-09T23:59:60Z",
    ],
)
def test_trusted_corpus_approval_rejects_impossible_utc_instants(
    approved_at_utc: str,
) -> None:
    with pytest.raises(ValidationError):
        TrustedCorpusApproval(
            record_digest="a" * 64,
            reviewer_identity="human:corpus-reviewer",
            reviewer_session="session:corpus-reviewer",
            approved_at_utc=approved_at_utc,
            approval_scope="evaluation_only",
        )


def test_trusted_corpus_approval_preserves_canonical_utc_serialization() -> None:
    approved_at_utc = "2026-09-09T00:00:00Z"

    approval = TrustedCorpusApproval(
        record_digest="a" * 64,
        reviewer_identity="human:corpus-reviewer",
        reviewer_session="session:corpus-reviewer",
        approved_at_utc=approved_at_utc,
        approval_scope="evaluation_only",
    )

    assert approval.model_dump(mode="json")["approved_at_utc"] == approved_at_utc
