from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from tests.nsqd.operator_c_evidence_cycle_3_support import (
    MALFORMED_PACKET_CASES,
    MalformedPacketCase,
    tamper_packet,
    validate_json_document,
    validate_jsonl_document,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-2026-09-07"
type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

ARTIFACT_NAMES = {
    "ablation-results.json",
    "acquisition-receipts.json",
    "bibliographic-snapshot.json",
    "claim-extractions.jsonl",
    "direct-a-to-c-prior-art.jsonl",
    "evidence-ledger.json",
    "source-extracts.jsonl",
}
SOURCE_RECEIPTS = {
    "arXiv:1402.2198v1#pdf": (
        "https://arxiv.org/pdf/1402.2198v1",
        "4b65227e4da7eaaaaf381c20c8716e0c1c99d80abfd188d6bf0456c5f30bc166",
        1613669,
    ),
    "arXiv:1402.2198v1#source": (
        "https://arxiv.org/e-print/1402.2198v1",
        "cb671211b8a2dcbd7a8056c26e34cdf78e476c5703b2c617f398bb0f9d928b09",
        1347442,
    ),
    "arXiv:2602.04643v2#pdf": (
        "https://arxiv.org/pdf/2602.04643v2",
        "ef56d2b2f2d701667f853c0bb69795fa58f7acbca16fbca27629852550983668",
        2647744,
    ),
    "arXiv:2602.04643v2#source": (
        "https://export.arxiv.org/e-print/2602.04643v2",
        "563ed7a21c6aa19964ae89fdbf3bb81c40c998f36f5298d5aa5bc2161ac63217",
        2357454,
    ),
    "OpenReview:BZfkxSasd3#api2-note": (
        "https://api2.openreview.net/notes?id=BZfkxSasd3",
        "7b4de97b4708b9d3895a3a1d73470beb20caab9e5dd1df8c25520877f55cd20d",
        3892,
    ),
    "doi:10.2139/ssrn.6855118#repository-source": (
        "https://raw.githubusercontent.com/cedricwyh/fin-jepa/58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9/docs/jepa_paper.tex",
        "3b652f82d4ccd27d54e11c9b054e429fa41bc289aa2c82e5ec920416bf813bc6",
        45773,
    ),
}


def _json(path: Path) -> dict[str, JsonValue]:
    loaded: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    validate_json_document(path.name, loaded)
    return loaded


def _jsonl(path: Path) -> list[dict[str, JsonValue]]:
    rows: list[JsonValue] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert all(isinstance(row, dict) for row in rows)
    mappings = [row for row in rows if isinstance(row, dict)]
    validate_jsonl_document(path.name, mappings, path.parent)
    return mappings


def _mapping(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _mappings(value: JsonValue) -> list[dict[str, JsonValue]]:
    assert isinstance(value, list)
    return [_mapping(item) for item in value]


def _strings(value: JsonValue) -> set[str]:
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    strings = [item for item in value if isinstance(item, str)]
    assert len(strings) == len(set(strings))
    return set(strings)


def _string(value: JsonValue) -> str:
    assert isinstance(value, str)
    assert value.strip()
    return value


def _positive_integer(value: JsonValue) -> int:
    assert type(value) is int
    assert value > 0
    return value


def _validate_packet(root: Path) -> None:
    _json(root / "acquisition-receipts.json")
    _json(root / "bibliographic-snapshot.json")
    _jsonl(root / "source-extracts.jsonl")
    _jsonl(root / "claim-extractions.jsonl")
    _jsonl(root / "direct-a-to-c-prior-art.jsonl")


@pytest.mark.parametrize("case", MALFORMED_PACKET_CASES, ids=lambda case: case.name)
def test_cycle_3_packet_boundary_rejects_malformed_evidence(
    tmp_path: Path, case: MalformedPacketCase
) -> None:
    packet_root = tmp_path / "packet"
    shutil.copytree(EVIDENCE_ROOT, packet_root)
    tamper_packet(packet_root, case)

    with pytest.raises(AssertionError):
        _validate_packet(packet_root)


def test_cycle_3_packet_membership_and_digests_are_exact() -> None:
    summary = _json(EVIDENCE_ROOT / "review-summary.json")
    artifacts = _mapping(summary["artifact_sha256"])

    assert set(artifacts) == ARTIFACT_NAMES
    assert {path.name for path in EVIDENCE_ROOT.iterdir()} == ARTIFACT_NAMES | {
        "README.md",
        "review-seal.json",
        "review-summary.json",
    }
    for name, digest in artifacts.items():
        assert hashlib.sha256((EVIDENCE_ROOT / name).read_bytes()).hexdigest() == digest
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    assert summary["packet_digest"] == hashlib.sha256(preimage).hexdigest()


def test_cycle_3_acquisition_binds_exact_observed_source_bytes() -> None:
    receipts = _json(EVIDENCE_ROOT / "acquisition-receipts.json")
    records = _mappings(receipts["records"])
    by_id = {_string(record["receipt_id"]): record for record in records}

    assert receipts["cutoff_utc"] == "2026-09-07T00:00:00Z"
    assert set(by_id) == set(SOURCE_RECEIPTS)
    for receipt_id, (url, digest, byte_count) in SOURCE_RECEIPTS.items():
        assert by_id[receipt_id]["url"] == url
        assert by_id[receipt_id]["sha256"] == digest
        assert by_id[receipt_id]["byte_count"] == byte_count
    assert all(_string(record["retrieved_at_utc"]).endswith("Z") for record in records)
    assert all(_positive_integer(record["byte_count"]) > 0 for record in records)
    assert by_id["OpenReview:BZfkxSasd3#api2-note"]["url"] == (
        "https://api2.openreview.net/notes?id=BZfkxSasd3"
    )
    assert by_id["doi:10.2139/ssrn.6855118#repository-source"]["version"] == (
        "58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9"
    )


def test_cycle_3_records_exact_source_identities_and_counterevidence() -> None:
    snapshot = _json(EVIDENCE_ROOT / "bibliographic-snapshot.json")
    records = _mappings(snapshot["records"])
    by_id = {_string(record["source_id"]): record for record in records}

    assert set(by_id) == {
        "OpenReview:BZfkxSasd3v2",
        "arXiv:1402.2198v1",
        "arXiv:2602.04643v2",
        "doi:10.2139/ssrn.6855118",
    }
    assert by_id["arXiv:2602.04643v2"]["authors"] == [
        "Yanan He",
        "Yunshi Wen",
        "Xin Wang",
        "Tengfei Ma",
    ]
    assert by_id["arXiv:1402.2198v1"]["title"] == (
        "Multi-scale Representation of High Frequency Market Liquidity"
    )
    assert by_id["arXiv:1402.2198v1"]["authors"] == [
        "Anton Golub",
        "Gregor Chliamovitch",
        "Alexandre Dupuis",
        "Bastien Chopard",
    ]
    openreview = by_id["OpenReview:BZfkxSasd3v2"]
    assert openreview["venue"] == "ICML 2026"
    assert openreview["license"] == "CC BY 4.0"
    assert openreview["full_text_inspected"] is False
    assert openreview["pdf_locator"] == "/pdf/6ddc0f748a4cbe51806b18a848fcf17e6b28f3ee.pdf"
    fin_jepa = by_id["doi:10.2139/ssrn.6855118"]
    assert fin_jepa["repository_commit"] == "58506d6e31ecb2c65f9c69ea1f1bc146ef08f8b9"
    assert fin_jepa["approved_record_id"] == "N11-FIN-01"


def test_cycle_3_extracts_are_typed_and_receipt_bound() -> None:
    receipts = _json(EVIDENCE_ROOT / "acquisition-receipts.json")
    receipt_digests = {
        _string(record["receipt_id"]): _string(record["sha256"])
        for record in _mappings(receipts["records"])
    }
    extracts = _jsonl(EVIDENCE_ROOT / "source-extracts.jsonl")
    claims = _jsonl(EVIDENCE_ROOT / "claim-extractions.jsonl")
    prior_art = _jsonl(EVIDENCE_ROOT / "direct-a-to-c-prior-art.jsonl")
    extract_ids = {_string(extract["extract_id"]) for extract in extracts}

    assert {_string(row["source_id"]) for row in extracts} == {
        "OpenReview:BZfkxSasd3v2",
        "arXiv:1402.2198v1",
        "arXiv:2602.04643v2",
        "doi:10.2139/ssrn.6855118",
    }
    for extract in extracts:
        receipt_id = _string(extract["receipt_id"])
        assert extract["source_sha256"] == receipt_digests[receipt_id]
        assert extract["direction"] in {"A_to_B", "A_to_C", "B_to_C"}
        assert extract["polarity"] in {
            "negative_result",
            "positive",
            "scope_limitation",
        }
        assert _string(extract["quote"])
        assert _string(extract["source_location"])
    assert all(_strings(claim["factual_extract_ids"]) <= extract_ids for claim in claims)
    assert all(_strings(row["evidence_extract_ids"]) <= extract_ids for row in prior_art)


def test_cycle_3_controls_and_conclusion_do_not_authorize() -> None:
    ledger = _json(EVIDENCE_ROOT / "evidence-ledger.json")
    claims = _jsonl(EVIDENCE_ROOT / "claim-extractions.jsonl")
    prior_art = _jsonl(EVIDENCE_ROOT / "direct-a-to-c-prior-art.jsonl")
    ablations = _json(EVIDENCE_ROOT / "ablation-results.json")
    summary = _json(EVIDENCE_ROOT / "review-summary.json")

    assert ledger["authorization_state"] == "report_only"
    assert ledger["candidate_outputs"] == []
    assert ledger["noninteraction_conclusion"] == "unverified_absence_of_evidence_only"
    assert all(_string(claim["decision"]).startswith("rejected") for claim in claims)
    assert {_string(row["counterevidence_source_id"]) for row in prior_art} == {
        "OpenReview:BZfkxSasd3v2",
        "doi:10.2139/ssrn.6855118",
    }
    runs = _mappings(ablations["runs"])
    assert {_string(run["method"]) for run in runs} == {
        "normalized_shared_terms",
        "shuffled_literature_negative_control",
        "typed_predication_paths",
    }
    assert all(run["accepted_bridge_count"] == 0 for run in runs)
    assert all(run["candidate_count"] == len(claims) for run in runs)
    assert all(run["direct_counterevidence_count"] == len(prior_art) for run in runs)
    negative_control = _mapping(ablations["negative_control"])
    seed_material = _string(negative_control["seed_material"])
    assert negative_control["seed_sha256"] == hashlib.sha256(seed_material.encode()).hexdigest()
    assert negative_control["permutation"] == [
        {"receives_role": "literature_c", "source_id": "arXiv:2602.04643v2"},
        {"receives_role": "literature_a", "source_id": "arXiv:1402.2198v1"},
    ]
    assert ablations["candidate_output_count"] == 0
    assert ablations["rediscovery_result"] == "not_measured"
    required_metrics = _mapping(ablations["required_metrics"])
    support_counts = _mapping(required_metrics["support_counts"])
    assert support_counts["source_extract_count"] == len(
        _jsonl(EVIDENCE_ROOT / "source-extracts.jsonl")
    )
    assert support_counts["typed_hypothesis_count"] == len(claims)
    assert required_metrics["reviewer_decision"] == "pending"
    assert summary["review_decision"] == "insufficient_evidence"
    assert summary["evidence_sufficient"] is False
    assert summary["human_acceptance"] == "not_requested"
    assert summary["runtime_activation"] == "not_authorized"
    assert summary["operator_d_status"] == "blocked"
    independent_review = _mapping(summary["independent_review"])
    assert independent_review["review_status"] == "approved_negative_conclusion"
    assert independent_review["reviewer_id"] == (
        "openai/gpt-5.6-sol / independent-evidence-reviewer"
    )
    assert (EVIDENCE_ROOT / "review-seal.json").is_file()
