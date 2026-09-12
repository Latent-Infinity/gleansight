from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from tests.nsqd.operator_c_resolution_support import validate_resolution_semantics
from tests.nsqd.operator_c_resolution_test_support import TamperCase, _tampered_packet

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
REJECTED_PACKET_ROOT: Final = (
    REPO_ROOT / "docs" / "reviews" / "nsqd-operator-c-evidence-2026-09-09-resolution"
)
REJECTED_ARTIFACT_SHA256: Final = {
    "README.md": "34d5d5391ddaf0afbe4c7a6ae1973b7fc91620a496e95e03096635ad2f28cd0c",
    "acquisition-receipts.json": "75702f8d65e400a0a31eff38a70f167fbb8d27e2662f85cd090cee0b990aa108",
    "bibliographic-query-receipts.json": (
        "4bd46862cf38cd8e72822c2ceccb82cb29856efdbaa4fc522a38ed5196aaf111"
    ),
    "evidence-ledger.json": "16881767921380f7b6cf77e0621a666de69100a97656c75fabe23a1faa60a05b",
    "packet-manifest.json": "745b16df316fd61c19949c2d046b15b86399b5d0633c1b4f5d2fd6f527e46788",
    "source-extracts.jsonl": "74c609059109c3e30d50fc22b9b285eae5d7a3f3a7ac97f2beb7a4f1f1fc2e1f",
    "typed-relations.json": "d7e0a2941ac46c9ae71288a504d0de34305fc23fb7e9ce11cf9327cf708030be",
}

SEMANTIC_TAMPER_CASES: Final = (
    TamperCase(
        "receipt_stable_source_id",
        "acquisition-receipts.json",
        ("records", 0, "stable_source_id"),
        "arXiv:9999.99999",
        "resolution.acquisition.source.known",
    ),
    TamperCase(
        "receipt_version_id",
        "acquisition-receipts.json",
        ("records", 0, "version_id"),
        "v1",
        "resolution.acquisition.source.exact",
    ),
    TamperCase(
        "repeated_historical_pair",
        "evidence-ledger.json",
        ("historical_cycle_comparison", "new_primary_source"),
        "arXiv:2602.04643v2",
        "resolution.ledger.history.new_primary_source",
    ),
    TamperCase(
        "renamed_historical_bridge",
        "evidence-ledger.json",
        ("historical_cycle_comparison", "distinct_middle_object"),
        "market_stress_regime",
        "resolution.ledger.history.middle_object",
    ),
    TamperCase(
        "reversed_relation",
        "typed-relations.json",
        ("A_to_bridge", "source", "direction"),
        "bridge_to_A",
        "resolution.relation.direction.exact",
    ),
    TamperCase(
        "extract_stable_source_id",
        "source-extracts.jsonl",
        (0, "stable_source_id"),
        "arXiv:2604.20949",
        "resolution.extract.stable_source_id.match",
    ),
    TamperCase(
        "extract_version_id",
        "source-extracts.jsonl",
        (0, "version_id"),
        "v1",
        "resolution.extract.version_id.match",
    ),
    TamperCase(
        "relation_source_identity",
        "typed-relations.json",
        ("A_to_bridge", "source", "source_identity"),
        "arXiv:1402.2198v1",
        "resolution.relation.source_identity.exact",
    ),
    TamperCase(
        "relation_subject_type",
        "typed-relations.json",
        ("bridge_to_C", "source", "subject_object_type"),
        "learned_time_series_anomaly_prediction_representation",
        "resolution.relation.object_types.exact",
    ),
    TamperCase(
        "relation_predicate",
        "typed-relations.json",
        ("bridge_to_C", "target", "predicate_type"),
        "instantiates_as",
        "resolution.relation.predicate.exact",
    ),
    TamperCase(
        "missing_assumptions",
        "typed-relations.json",
        ("A_to_bridge", "target", "assumptions"),
        [],
        "resolution.value.nonempty_string_list",
    ),
    TamperCase(
        "missing_limitations",
        "typed-relations.json",
        ("bridge_to_C", "target", "limitations"),
        [],
        "resolution.value.nonempty_string_list",
    ),
    TamperCase(
        "counterevidence_extract_mismatch",
        "evidence-ledger.json",
        ("interaction_checks", 5, "extract_ids"),
        ["A-SOFT-CODEBOOK"],
        "resolution.ledger.counterevidence.extracts.exact",
    ),
    TamperCase(
        "interaction_status",
        "evidence-ledger.json",
        ("interaction_checks", 0, "status"),
        "observed",
        "resolution.ledger.interactions.exact",
    ),
    TamperCase(
        "negative_control_status",
        "evidence-ledger.json",
        (
            "negative_controls",
            "sha256_seeded_shuffled_literature_pair_control_under_identical_query_budget",
        ),
        "not_observed_within_bounded_queries",
        "resolution.ledger.controls.exact",
    ),
    TamperCase(
        "missing_historical_comparison",
        "evidence-ledger.json",
        ("historical_cycle_comparison",),
        {},
        "resolution.ledger.history.exact",
    ),
    TamperCase(
        "fabricated_control_derivation",
        "bibliographic-query-receipts.json",
        ("query_batches", 2, "derivation", "status"),
        "reproducible",
        "resolution.query.shuffled_derivation.unavailable",
    ),
)


@pytest.mark.parametrize("case", SEMANTIC_TAMPER_CASES, ids=lambda case: case.name)
def test_corrected_resolution_semantics_fail_closed(tmp_path: Path, case: TamperCase) -> None:
    packet = _tampered_packet(tmp_path, case)

    with pytest.raises(AssertionError, match=f"^{case.guard}$"):
        validate_resolution_semantics(packet)


def test_rejected_packet_artifacts_remain_byte_identical() -> None:
    import hashlib

    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in REJECTED_PACKET_ROOT.iterdir()
    }

    assert actual == REJECTED_ARTIFACT_SHA256
