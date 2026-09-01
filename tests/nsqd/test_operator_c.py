from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nsqd.domain.diverge import require_operator
from nsqd.domain.operator_c import bind_operator_c_pair, classify_source_paper_id

PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
)
PROJECTION_ROOT = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reviews"
    / "nsqd-projection-review-2026-08-28"
    / "final"
)


def _packet(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operator": "C",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "evidence_sufficient": False,
        "algorithm_identity": "not_run",
        "candidate_outputs": [],
        "preferred_pair": {
            "literature_a": {
                "record_id": "N11-OPT-02",
                "domain_policy_id": "optimization/1",
            },
            "literature_c": {
                "record_id": "N11-FIN-04",
                "domain_policy_id": "finance/1",
            },
        },
        "backup_pair": {
            "literature_a": {
                "record_id": "N11-OPT-01",
                "domain_policy_id": "optimization/1",
            },
            "literature_c": {
                "record_id": "N11-FIN-01",
                "domain_policy_id": "finance/1",
            },
        },
    }
    payload.update(overrides)
    return payload


def _record(
    record_id: str,
    *,
    domain_policy_id: str,
    source_paper_id: str,
    title: str,
    review_status: str = "approved",
) -> dict[str, Any]:
    return {
        "id": record_id,
        "kind": "corpus-paper-paraphrase",
        "review_status": review_status,
        "domain_policy_id": domain_policy_id,
        "source_paper_id": source_paper_id,
        "title": title,
    }


APPROVED = {
    "N11-OPT-02": _record(
        "N11-OPT-02",
        domain_policy_id="optimization/1",
        source_paper_id="44b3b3bb40a9055eccdf86ea1702f6ae8b38934c",
        title=(
            "Decentralized Stochastic Optimization and Gossip Algorithms "
            "with Compressed Communication"
        ),
    ),
    "N11-FIN-04": _record(
        "N11-FIN-04",
        domain_policy_id="finance/1",
        source_paper_id="arxiv:2512.12727",
        title=(
            "EXFormer: A Multi-Scale Trend-Aware Transformer with Dynamic "
            "Variable Selection for Foreign Exchange Returns Prediction"
        ),
    ),
    "N11-OPT-01": _record(
        "N11-OPT-01",
        domain_policy_id="optimization/1",
        source_paper_id="4dabfd108c13cd730d3cc583e474b5d8bdf4685f",
        title=(
            "High-Probability Bounds for Stochastic Optimization and "
            "Variational Inequalities: the Case of Unbounded Variance"
        ),
    ),
    "N11-FIN-01": _record(
        "N11-FIN-01",
        domain_policy_id="finance/1",
        source_paper_id="doi:10.2139/ssrn.6855118",
        title=(
            "Fin-JEPA: Joint-Embedding Predictive Representation Learning for Financial Time Series"
        ),
    ),
}


def test_classify_source_paper_id_schemes() -> None:
    assert classify_source_paper_id("doi:10.2139/ssrn.6855118") == "doi"
    assert classify_source_paper_id("arxiv:2512.12727") == "arxiv"
    assert classify_source_paper_id("44b3b3bb40a9055eccdf86ea1702f6ae8b38934c") == "s2"
    assert classify_source_paper_id("local-only") == "unknown"


def test_bind_operator_c_pair_stamps_approved_identifiers() -> None:
    bound = bind_operator_c_pair(_packet(), approved_records=APPROVED)
    assert bound["pair"] == "preferred"
    assert bound["literature_a"]["record_id"] == "N11-OPT-02"
    assert bound["literature_a"]["source_paper_id"] == "44b3b3bb40a9055eccdf86ea1702f6ae8b38934c"
    assert bound["literature_a"]["identifier_scheme"] == "s2"
    assert bound["literature_c"]["source_paper_id"] == "arxiv:2512.12727"
    assert bound["literature_c"]["identifier_scheme"] == "arxiv"
    assert bound["noninteraction"]["status"] == "unverified"
    assert bound["evidence_sufficient"] is False
    assert bound["runtime_authorized"] is False
    assert bound["algorithm_identity"] == "not_run"


def test_bind_operator_c_backup_pair_uses_doi() -> None:
    bound = bind_operator_c_pair(_packet(), approved_records=APPROVED, pair="backup")
    assert bound["pair"] == "backup"
    assert bound["literature_a"]["record_id"] == "N11-OPT-01"
    assert bound["literature_c"]["identifier_scheme"] == "doi"
    assert bound["evidence_sufficient"] is False


def test_bind_operator_c_pair_rejects_unapproved_or_missing_records() -> None:
    unapproved = dict(APPROVED)
    unapproved["N11-FIN-04"] = _record(
        "N11-FIN-04",
        domain_policy_id="finance/1",
        source_paper_id="arxiv:2512.12727",
        title="EXFormer",
        review_status="pending",
    )
    with pytest.raises(ValueError, match="approved"):
        bind_operator_c_pair(_packet(), approved_records=unapproved)
    with pytest.raises(ValueError, match="unknown record"):
        bind_operator_c_pair(_packet(), approved_records={"N11-OPT-02": APPROVED["N11-OPT-02"]})


def test_bind_operator_c_pair_rejects_shared_identifier() -> None:
    records = dict(APPROVED)
    records["N11-FIN-04"] = _record(
        "N11-FIN-04",
        domain_policy_id="finance/1",
        source_paper_id="44b3b3bb40a9055eccdf86ea1702f6ae8b38934c",
        title="EXFormer",
    )
    with pytest.raises(ValueError, match="distinct literatures"):
        bind_operator_c_pair(_packet(), approved_records=records)


def test_bound_pair_does_not_authorize_operator_c() -> None:
    bound = bind_operator_c_pair(_packet(), approved_records=APPROVED)
    assert bound["runtime_authorized"] is False
    with pytest.raises(ValueError, match="operator C is not supported"):
        require_operator("C", enabled_operators=frozenset({"A", "B"}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("runtime_authorized", True),
        ("runtime_authorized", "false"),
        ("runtime_authorized", None),
        ("evidence_sufficient", True),
        ("evidence_sufficient", "false"),
        ("evidence_sufficient", None),
    ],
)
def test_bind_operator_c_pair_requires_explicit_false_safety_flags(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match=rf"{field} must be false"):
        bind_operator_c_pair(_packet(**{field: value}), approved_records=APPROVED)


@pytest.mark.parametrize("field", ["runtime_authorized", "evidence_sufficient"])
def test_bind_operator_c_pair_rejects_missing_safety_flags(field: str) -> None:
    packet = _packet()
    packet.pop(field)
    with pytest.raises(ValueError, match=rf"{field} must be false"):
        bind_operator_c_pair(packet, approved_records=APPROVED)


def test_bind_operator_c_pair_rejects_malformed_packet_and_records() -> None:
    with pytest.raises(ValueError, match="source_paper_id is required"):
        classify_source_paper_id("")
    with pytest.raises(ValueError, match="operator C packet"):
        bind_operator_c_pair({"operator": "E"}, approved_records=APPROVED)
    with pytest.raises(ValueError, match="report_only"):
        bind_operator_c_pair(
            _packet(authorization_state="authorized"),
            approved_records=APPROVED,
        )
    with pytest.raises(ValueError, match="runtime_authorized must be false"):
        bind_operator_c_pair(_packet(runtime_authorized=True), approved_records=APPROVED)
    for candidate_outputs in (None, "missing", [{"candidate_id": "invented"}]):
        with pytest.raises(ValueError, match="candidate_outputs must be an empty list"):
            bind_operator_c_pair(
                _packet(candidate_outputs=candidate_outputs),
                approved_records=APPROVED,
            )
    missing_outputs = _packet()
    missing_outputs.pop("candidate_outputs")
    with pytest.raises(ValueError, match="candidate_outputs must be an empty list"):
        bind_operator_c_pair(missing_outputs, approved_records=APPROVED)
    for algorithm_identity in (None, "  "):
        with pytest.raises(ValueError, match="algorithm_identity is required"):
            bind_operator_c_pair(
                _packet(algorithm_identity=algorithm_identity),
                approved_records=APPROVED,
            )
    with pytest.raises(ValueError, match="preferred or backup"):
        bind_operator_c_pair(_packet(), approved_records=APPROVED, pair="other")
    same_policy = dict(APPROVED)
    same_policy["N11-FIN-04"] = _record(
        "N11-FIN-04",
        domain_policy_id="optimization/1",
        source_paper_id="arxiv:2512.12727",
        title="EXFormer",
    )
    same_policy_packet = _packet()
    same_policy_packet["preferred_pair"]["literature_c"] = {"record_id": "N11-FIN-04"}
    with pytest.raises(ValueError, match="distinct domain policies"):
        bind_operator_c_pair(same_policy_packet, approved_records=same_policy)
    with pytest.raises(ValueError, match="does not match approved record"):
        bind_operator_c_pair(_packet(), approved_records=same_policy)
    mismatched = dict(APPROVED)
    mismatched["N11-OPT-02"] = dict(APPROVED["N11-OPT-02"], kind="requirement-card")
    with pytest.raises(ValueError, match="approved paraphrases"):
        bind_operator_c_pair(_packet(), approved_records=mismatched)
    with pytest.raises(ValueError, match="preferred_pair is required"):
        bind_operator_c_pair(_packet(preferred_pair="missing"), approved_records=APPROVED)
    with pytest.raises(ValueError, match="keys must be strings"):
        bind_operator_c_pair(_packet(preferred_pair={1: "x"}), approved_records=APPROVED)
    incomplete = _packet()
    incomplete["preferred_pair"] = {
        "literature_a": {"record_id": "N11-OPT-02"},
    }
    with pytest.raises(ValueError, match="literature_c is required"):
        bind_operator_c_pair(incomplete, approved_records=APPROVED)
    titled = _packet()
    titled["preferred_pair"]["literature_a"]["title"] = "not the approved title"
    with pytest.raises(ValueError, match="title does not match"):
        bind_operator_c_pair(titled, approved_records=APPROVED)
    blank_id = dict(APPROVED)
    blank_id["N11-OPT-02"] = dict(APPROVED["N11-OPT-02"], source_paper_id="  ")
    with pytest.raises(ValueError, match="source_paper_id is required"):
        bind_operator_c_pair(_packet(), approved_records=blank_id)


def test_committed_operator_c_packet_binds_n11_projection_identifiers() -> None:
    packet = yaml.safe_load((PACKET_ROOT / "operator-c.yaml").read_text(encoding="utf-8"))
    records = {
        record_id: yaml.safe_load(
            (PROJECTION_ROOT / f"{record_id}.yaml").read_text(encoding="utf-8")
        )
        for record_id in ("N11-OPT-02", "N11-FIN-04", "N11-OPT-01", "N11-FIN-01")
    }
    bound = bind_operator_c_pair(packet, approved_records=records)
    preferred = packet["preferred_pair"]
    assert bound["literature_a"]["source_paper_id"] == records["N11-OPT-02"]["source_paper_id"]
    assert bound["literature_c"]["source_paper_id"] == records["N11-FIN-04"]["source_paper_id"]
    assert preferred["literature_a"]["source_paper_id"] == bound["literature_a"]["source_paper_id"]
    assert (
        preferred["literature_c"]["identifier_scheme"] == bound["literature_c"]["identifier_scheme"]
    )
    assert bound["evidence_sufficient"] is False
    assert packet["runtime_authorized"] is False
    assert packet["evidence_sufficient"] is False
    assert packet["algorithm_identity"] == "operator-c-evidence-audit/1"
    assert bound["algorithm_identity"] == packet["algorithm_identity"]
