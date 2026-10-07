from scripts.research.compression_panel_v2 import (
    cluster_bootstrap_kappa,
    cohen_kappa,
    make_tiebreak_packet,
    primary_disagreements,
    resolve_disagreement,
    validate_tiebreak_votes,
)


def claim(claim_id: str) -> dict[str, object]:
    return {
        "claim_id": claim_id,
        "claim": f"Claim {claim_id}.",
        "condition_caveat": "Under the stated scope.",
        "source_id": f"S-{claim_id}",
        "evidence": [
            {
                "locator": "p. 1",
                "byte_start": 10,
                "byte_end": 20,
                "excerpt": "supplied evidence",
            }
        ],
    }


def vote(claim_id: str, label: str, citation: str | None = None) -> dict[str, object]:
    expected = f"S-{claim_id}:p. 1:[10,20)"
    return {
        "claim_id": claim_id,
        "label": label,
        "rationale": "The supplied excerpt supports this label.",
        "evidence_refs": [citation or expected],
    }


def test_tiebreak_payload_contains_only_valid_primary_disagreements() -> None:
    claims = [claim("A"), claim("B"), claim("C"), claim("D")]
    primaries = {
        "claude": [
            vote("A", "supported"),
            vote("B", "supported"),
            vote("C", "contradicted"),
            vote("D", "insufficient_evidence"),
        ],
        "codex": [
            vote("A", "supported"),
            vote("B", "insufficient_evidence"),
            vote("C", "contradicted"),
            vote("D", "supported"),
        ],
    }
    disagreements = primary_disagreements(claims, primaries)
    packet = make_tiebreak_packet("compression-evidence-review-v1", disagreements)
    assert [item["claim_id"] for item in packet["claims"]] == ["B", "D"]
    assert all(len(item["primary_votes"]) == 2 for item in packet["claims"])
    assert not {"author", "title"} & set(packet["claims"][0])


def test_added_locator_is_an_invalid_missing_tiebreak_vote() -> None:
    disputed = [claim("B")]
    packet = make_tiebreak_packet(
        "compression-evidence-review-v1",
        [
            {
                "claim_id": "B",
                "claim": "Claim B.",
                "condition_caveat": "Under the stated scope.",
                "source_id": "S-B",
                "evidence": disputed[0]["evidence"],
                "primary_votes": [
                    {"label": "supported", "rationale": "First primary rationale."},
                    {
                        "label": "insufficient_evidence",
                        "rationale": "Second primary rationale.",
                    },
                ],
            }
        ],
    )
    output = {
        "protocol_version": "compression-evidence-review-v1",
        "votes": [vote("B", "supported", "S-B:p. 1, Added locator:[10,20)")],
    }
    effective, invalid = validate_tiebreak_votes(packet, output)
    assert effective == {"B": None}
    assert invalid == [
        {"claim_id": "B", "reason": "invalid_or_unbound_evidence_reference"}
    ]


def test_cohen_kappa_fixtures() -> None:
    assert cohen_kappa(
        ["supported", "supported", "contradicted", "contradicted"],
        ["supported", "supported", "contradicted", "contradicted"],
    ) == 1.0
    assert cohen_kappa(
        ["supported", "supported", "contradicted", "contradicted"],
        ["supported", "contradicted", "supported", "contradicted"],
    ) == 0.0
    assert cohen_kappa(["supported"] * 4, ["supported"] * 4) is None


def test_perfect_cluster_bootstrap_has_2000_finite_replicates() -> None:
    rows = [
        (
            f"cluster-{cluster}",
            "supported" if index < 3 else "contradicted",
            "supported" if index < 3 else "contradicted",
        )
        for cluster in range(10)
        for index in range(5)
    ]
    result = cluster_bootstrap_kappa(rows, replicates=2000, seed=17)
    assert result["finite_replicates"] == 2000
    assert result["interval_95"] == [1.0, 1.0]
    assert result["point_kappa"] == 1.0


def test_strict_two_of_three_resolution() -> None:
    assert resolve_disagreement(["supported", "insufficient_evidence"], "supported") == "supported"
    assert resolve_disagreement(["supported", "insufficient_evidence"], "contradicted") is None
    assert resolve_disagreement(["supported", "insufficient_evidence"], None) is None
    assert resolve_disagreement(["supported", "insufficient_evidence"], "invalid") is None
