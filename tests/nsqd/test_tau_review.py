from __future__ import annotations

from copy import deepcopy

import pytest

from nsqd.domain.tau_review import (
    build_tau_label_prompt,
    evaluate_tau_packet,
    parse_tau_label_proposal,
    tau_review_packet_digest,
)

POLICIES = ("finance/1", "optimization/1")
TRUSTED_REVIEWERS = frozenset({"human-reviewer"})


def _row(
    *,
    policy_id: str,
    label: str,
    index: int,
    evidence: float,
) -> dict[str, object]:
    pair_id = f"{policy_id}-{label}-{index}"
    return {
        "pair_id": pair_id,
        "domain_policy_id": policy_id,
        "snapshot_id": f"snapshot-{policy_id}",
        "snapshot_state": "production_valid" if policy_id == "finance/1" else "calibration",
        "candidate": {"artifact_hash": f"candidate-{pair_id}", "paraphrase": "candidate text"},
        "neighbor": {"record_id": f"neighbor-{pair_id}", "paraphrase": "neighbor text"},
        "measurement": {"evidence_mean_distance": evidence, "k": 5},
        "agent_proposal": {
            "pair_id": pair_id,
            "label": label,
            "confidence": 0.9,
            "rationale": "proposal only",
            "review_status": "pending",
            "prompt_version_id": "tau-label/1",
            "model": "qwen3.6:35b-a3b-q4_K_M",
            "profile": "ollama-local",
            "review_workflow": "one-writer-one-reviewer",
            "review_rounds": 4,
        },
        "human_review": {
            "label": label,
            "reviewer": "human-reviewer",
            "approved_at": "2026-08-28T00:00:00+00:00",
            "approval_revision": "review-1",
        },
    }


def _balanced_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for policy_id in POLICIES:
        rows.extend(
            _row(policy_id=policy_id, label="near_duplicate", index=index, evidence=0.10)
            for index in range(30)
        )
        rows.extend(
            _row(policy_id=policy_id, label="novel", index=index, evidence=0.70)
            for index in range(30)
        )
    return rows


def _manifest(rows: list[dict[str, object]]) -> dict[str, str]:
    return {
        "content_sha256": tau_review_packet_digest(rows),
        "reviewer": "human-reviewer",
        "approved_at": "2026-08-28T00:00:00+00:00",
        "approval_revision": "review-1",
    }


def test_tau_label_prompt_requires_pending_structured_proposal() -> None:
    prompt = build_tau_label_prompt(_balanced_rows()[0])
    assert "near_duplicate | novel | ambiguous" in prompt
    assert '"review_status": "pending"' in prompt
    assert "must not approve" in prompt.lower()


def test_tau_label_proposal_cannot_self_approve() -> None:
    proposal = {
        "pair_id": "finance/1-near_duplicate-0",
        "label": "near_duplicate",
        "confidence": 0.9,
        "rationale": "same mechanism and claim",
        "review_status": "approved",
        "prompt_version_id": "tau-label/1",
        "model": "qwen3.6:35b-a3b-q4_K_M",
        "profile": "ollama-local",
        "review_workflow": "one-writer-one-reviewer",
        "review_rounds": 4,
    }
    with pytest.raises(ValueError, match="agent proposals must remain pending"):
        parse_tau_label_proposal(proposal)


def test_tau_packet_selects_highest_threshold_within_false_kill_caps() -> None:
    rows = _balanced_rows()
    result = evaluate_tau_packet(
        rows,
        manifest=_manifest(rows),
        trusted_reviewers=TRUSTED_REVIEWERS,
    )
    assert result["selected_tau"] == 0.60
    assert result["approved_pair_count"] == 120
    assert result["counts_by_policy"] == {
        "finance/1": {"near_duplicate": 30, "novel": 30},
        "optimization/1": {"near_duplicate": 30, "novel": 30},
    }


def test_tau_packet_uses_caps_instead_of_balanced_accuracy() -> None:
    rows = _balanced_rows()
    novel_rows: list[dict[str, object]] = []
    for row in rows:
        review = row["human_review"]
        assert isinstance(review, dict)
        if review.get("label") == "novel":
            novel_rows.append(row)
    novel_rows[0]["measurement"] = {"evidence_mean_distance": 0.10, "k": 5}
    for row in novel_rows[1:4]:
        row["measurement"] = {"evidence_mean_distance": 0.20, "k": 5}

    result = evaluate_tau_packet(
        rows,
        manifest=_manifest(rows),
        trusted_reviewers=TRUSTED_REVIEWERS,
    )
    assert result["selected_tau"] == 0.15
    by_tau = {row["tau"]: row for row in result["thresholds"]}
    assert by_tau[0.15]["admissible"] is True
    assert by_tau[0.30]["admissible"] is False


def test_tau_packet_rejects_agent_only_or_unbalanced_evidence() -> None:
    rows = _balanced_rows()
    rows[0].pop("human_review")
    with pytest.raises(ValueError, match="human_review is required"):
        evaluate_tau_packet(
            rows,
            manifest=_manifest(rows),
            trusted_reviewers=TRUSTED_REVIEWERS,
        )

    rows = _balanced_rows()[:-1]
    with pytest.raises(ValueError, match="at least 30 approved novel"):
        evaluate_tau_packet(
            rows,
            manifest=_manifest(rows),
            trusted_reviewers=TRUSTED_REVIEWERS,
        )


def test_tau_packet_rejects_manifest_tampering_and_non_finite_evidence() -> None:
    rows = _balanced_rows()
    manifest = _manifest(rows)
    tampered = deepcopy(rows)
    tampered[0]["human_review"] = {
        "label": "novel",
        "reviewer": "human-reviewer",
        "approved_at": "2026-08-28T00:00:00+00:00",
        "approval_revision": "review-2",
    }
    with pytest.raises(ValueError, match="manifest content hash"):
        evaluate_tau_packet(
            tampered,
            manifest=manifest,
            trusted_reviewers=TRUSTED_REVIEWERS,
        )

    rows[0]["measurement"] = {"evidence_mean_distance": float("nan"), "k": 5}
    with pytest.raises(ValueError, match="finite non-negative"):
        evaluate_tau_packet(
            rows,
            manifest=_manifest(rows),
            trusted_reviewers=TRUSTED_REVIEWERS,
        )


def test_tau_packet_requires_out_of_band_trusted_reviewer() -> None:
    rows = _balanced_rows()
    with pytest.raises(ValueError, match="reviewer is not trusted"):
        evaluate_tau_packet(
            rows,
            manifest=_manifest(rows),
            trusted_reviewers=frozenset(),
        )


def test_tau_packet_rejects_model_or_profile_as_human_reviewer() -> None:
    rows = _balanced_rows()
    model_name = "qwen3.6:35b-a3b-q4_K_M"
    for row in rows:
        review = row["human_review"]
        assert isinstance(review, dict)
        label = review.get("label")
        assert isinstance(label, str)
        row["human_review"] = {
            "label": label,
            "reviewer": model_name,
            "approved_at": "2026-08-28T00:00:00+00:00",
            "approval_revision": "review-1",
        }
    manifest = {
        "content_sha256": tau_review_packet_digest(rows),
        "reviewer": model_name,
        "approved_at": "2026-08-28T00:00:00+00:00",
        "approval_revision": "review-1",
    }
    with pytest.raises(ValueError, match="reviewer cannot be the proposing model or profile"):
        evaluate_tau_packet(
            rows,
            manifest=manifest,
            trusted_reviewers=frozenset({model_name}),
        )
