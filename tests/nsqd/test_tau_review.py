from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from nsqd.domain.project import PROJECTOR_VERSION, canonical_reviewed_projection_digest
from nsqd.domain.snapshot import sha256_hex
from nsqd.domain.tau_measurement import tau_measurement_artifact_digest
from nsqd.domain.tau_review import (
    build_tau_label_prompt,
    evaluate_tau_packet,
    parse_tau_label_proposal,
    qualify_tau_measurement_pair,
    require_tau_measurement_inventory,
    tau_measurement_inventory,
    tau_review_packet_digest,
)

POLICIES = ("finance/1", "optimization/1")
TRUSTED_REVIEWERS = frozenset({"human-reviewer"})
AS_OF = datetime(2026, 8, 28, tzinfo=UTC)


def _approved_neighbor(*, policy_id: str, rank: int) -> dict[str, object]:
    paraphrase = f"approved {policy_id} neighbor {rank}"
    projection: dict[str, object] = {
        "domain_policy_id": policy_id,
        "paraphrase": paraphrase,
        "paraphrase_source": "model_assisted",
        "source_paper_id": f"paper-{policy_id}-{rank}",
        "source": f"doi:10.1/{policy_id}-{rank}",
        "source_abstract_sha256": sha256_hex(f"abstract {policy_id} {rank}".encode()),
        "source_markdown_sha256": sha256_hex(f"markdown {policy_id} {rank}".encode()),
        "paraphrase_sha256": sha256_hex(paraphrase.encode()),
        "human_reviewer": "human-reviewer",
        "human_approved_at": AS_OF.isoformat(),
        "review_status": "approved",
    }
    return {
        "record_id": f"record-{policy_id}-{rank}",
        "source_id": projection["source"],
        "source_paper_id": projection["source_paper_id"],
        "domain_policy_id": policy_id,
        "text_digest": projection["paraphrase_sha256"],
        "projector_version": PROJECTOR_VERSION,
        "reviewed_projection_digest": canonical_reviewed_projection_digest(projection),
        "reviewed_projection": projection,
        "distance": (rank + 1) / 10,
        "rank": rank,
    }


APPROVED_PROJECTION_DIGESTS = frozenset(
    str(_approved_neighbor(policy_id=policy_id, rank=rank)["reviewed_projection_digest"])
    for policy_id in POLICIES
    for rank in range(1, 6)
)


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


def _measurement_row(
    *,
    policy_id: str,
    index: int,
    snapshot_state: str = "production_valid",
    evidence: float = 0.40,
    **overrides: object,
) -> dict[str, object]:
    pair_id = f"{policy_id}-measure-{index}"
    candidate_hash = sha256_hex(pair_id.encode("utf-8"))
    candidate_text = f"candidate text {pair_id}"
    neighbors = [_approved_neighbor(policy_id=policy_id, rank=rank) for rank in range(1, 6)]
    distances = [float(neighbor["distance"]) for neighbor in neighbors]
    snapshot_digest = sha256_hex(f"snapshot-{policy_id}".encode())
    row: dict[str, object] = {
        "pair_id": pair_id,
        "candidate_artifact_hash": candidate_hash,
        "domain_policy_id": policy_id,
        "snapshot_id": snapshot_digest,
        "snapshot_digest": snapshot_digest,
        "snapshot_state": snapshot_state,
        "corpus_version": 1,
        "candidate": {
            "artifact_hash": candidate_hash,
            "paraphrase": candidate_text,
            "text_digest": sha256_hex(candidate_text.encode("utf-8")),
        },
        "neighbor": dict(neighbors[0]),
        "neighbors": neighbors,
        "measurement": {
            "evidence_mean_distance": evidence,
            "k": 5,
            "distances": distances,
            "embedding_model_id": "qwen3-embedding:latest",
            "embedding_model_version": "latest",
            "embedding_dimension": 4096,
            "normalization_policy": "l2",
            "distance_metric": "cosine_distance",
            "algorithm_contract_version": "1.1",
            "measured_at": AS_OF.isoformat(),
        },
    }
    row.update(overrides)
    row["measurement_artifact_digest"] = tau_measurement_artifact_digest(row)
    return row


def _trusted_measurements(rows: list[dict[str, object]]) -> frozenset[str]:
    digests: set[str] = set()
    for row in rows:
        digest = tau_measurement_artifact_digest(row)
        row["measurement_artifact_digest"] = digest
        digests.add(digest)
    return frozenset(digests)


def _enough_measurements() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for policy_id in POLICIES:
        state = "production_valid" if policy_id == "finance/1" else "calibration"
        rows.extend(
            _measurement_row(policy_id=policy_id, index=index, snapshot_state=state)
            for index in range(60)
        )
    return rows


def test_qualify_tau_measurement_rejects_smoke_synthetic_and_unapproved() -> None:
    valid = _measurement_row(policy_id="finance/1", index=0)
    ok = qualify_tau_measurement_pair(
        valid,
        approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        trusted_measurement_digests=_trusted_measurements([valid]),
    )
    assert ok["domain_policy_id"] == "finance/1"
    assert ok["measurement"]["k"] == 5
    with pytest.raises(ValueError, match="calibration or production_valid"):
        qualify_tau_measurement_pair(
            _measurement_row(policy_id="finance/1", index=1, snapshot_state="smoke_only"),
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset(),
        )
    with pytest.raises(ValueError, match="synthetic"):
        qualify_tau_measurement_pair(
            _measurement_row(policy_id="finance/1", index=2, synthetic=True),
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset(),
        )
    with pytest.raises(ValueError, match="unapproved"):
        qualify_tau_measurement_pair(
            _measurement_row(
                policy_id="finance/1",
                index=3,
                source_class="requirement_card",
            ),
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset(),
        )


def test_measurement_inventory_is_not_ready_until_sixty_pairs_per_policy() -> None:
    short = [_measurement_row(policy_id="finance/1", index=0)]
    inventory = tau_measurement_inventory(
        short,
        approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        trusted_measurement_digests=_trusted_measurements(short),
    )
    assert inventory["ready_for_label_proposals"] is False
    assert inventory["counts_by_policy"]["finance/1"] == 1
    assert inventory["counts_by_policy"]["optimization/1"] == 0
    assert "do not fabricate" in inventory["shortfall"].lower()
    with pytest.raises(ValueError, match="do not fabricate"):
        require_tau_measurement_inventory(
            short,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=_trusted_measurements(short),
        )

    enough = _enough_measurements()
    trusted_enough = _trusted_measurements(enough)
    ready = tau_measurement_inventory(
        enough,
        approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        trusted_measurement_digests=trusted_enough,
    )
    assert ready["ready_for_label_proposals"] is True
    assert ready["qualified_pair_count"] == 120
    require_tau_measurement_inventory(
        enough,
        approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        trusted_measurement_digests=trusted_enough,
    )


def test_measurement_inventory_rejects_invented_or_duplicate_candidate_rows() -> None:
    invented = {
        "pair_id": "invented",
        "domain_policy_id": "finance/1",
        "snapshot_id": "snapshot",
        "snapshot_state": "calibration",
        "candidate": {},
        "neighbor": {},
        "measurement": {"evidence_mean_distance": 0.4, "k": 5},
    }
    with pytest.raises(ValueError, match="measurement_artifact_digest"):
        tau_measurement_inventory(
            [invented],
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset(),
        )

    first = _measurement_row(policy_id="finance/1", index=0)
    second = _measurement_row(policy_id="finance/1", index=1)
    second["candidate_artifact_hash"] = first["candidate_artifact_hash"]
    second["candidate"] = deepcopy(first["candidate"])
    with pytest.raises(ValueError, match="duplicate candidate"):
        tau_measurement_inventory(
            [first, second],
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=_trusted_measurements([first, second]),
        )

    fabricated_inventory = _enough_measurements()
    _trusted_measurements(fabricated_inventory)
    with pytest.raises(ValueError, match="trusted persisted grounding"):
        tau_measurement_inventory(
            fabricated_inventory,
            approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
            trusted_measurement_digests=frozenset(),
        )


def test_measurement_inventory_does_not_mutate_runtime_tau() -> None:
    from nsqd.domain.novelty import NOVELTY_THRESHOLD_TAU

    rows = _enough_measurements()
    tau_measurement_inventory(
        rows,
        approved_projection_digests=APPROVED_PROJECTION_DIGESTS,
        trusted_measurement_digests=_trusted_measurements(rows),
    )
    assert NOVELTY_THRESHOLD_TAU == 0.45
