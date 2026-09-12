from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from tests.nsqd.operator_c_resolution_contracts import (
    CONTROLS,
    HISTORY,
    INTERACTION_CONTRACTS,
    INTERACTION_STATUS,
    PREDECESSOR,
)

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonMapping = dict[str, JsonValue]

A_SHA: Final = "ef56d2b2f2d701667f853c0bb69795fa58f7acbca16fbca27629852550983668"
B_SHA: Final = "4680476871fd7b23842977cec7fe35b69a838606cbddc0e5df3c68942897bd68"
C_SHA: Final = "4b65227e4da7eaaaaf381c20c8716e0c1c99d80abfd188d6bf0456c5f30bc166"
SOURCE_IMPORTS: Final = {
    "arXiv:2602.04643": ("v2", "https://arxiv.org/pdf/2602.04643v2", 2647744, A_SHA),
    "arXiv:2604.20949": ("v1", "https://arxiv.org/pdf/2604.20949v1", 1182734, B_SHA),
    "arXiv:1402.2198": ("v1", "https://arxiv.org/pdf/1402.2198v1", 1613669, C_SHA),
}

QUERY_SHA: Final = (
    "db0f457ecb85877db44453e50448294dcb0d93d6992ca62574bbe16c5e7cf9b6",
    "48f67d1c2822d97f7c291420321fd014be1cadbb389c8d35660c5bf2bdbbf3e8",
    "16bdbe34f18c8802353f24d88a42674b40a61cf65a98be2b4e754713068d41c3",
    "2c5b667689283e4550039326087d5c5e97e46bb1c28b47c1bf4b7f289fcb7149",
    "65ab993d12c5c2cc9b68e6da2bb79b326930283e520363ffcdc145f88cd5a148",
    "3f084a00ad86141fff57fc36587e0b8663990e331792f2b363a2a693ba6adede",
    "2974260a050cb569d8f909f642ffd835bd384c735afb7e16ab6abd6e6e0b65c8",
    "c1a97b6ac23febd28f182fa75aac6c89ed83d9f3d810d27f5035f67b336298c0",
    "a8048c93c9171c53e4dc24ca4798447a2d64711740cd36861b6be8cf0aa3ea58",
    "1932f767517e6e4100ea4788cd48da65d476d0c57f64e9146cc1638fc1656b7e",
    "2c8ef53ff482caf5e4cce3194c63378ee9649eb3da2662cccd8ac55e9ef5f7ed",
)
QUERY_RESPONSES: Final = {
    "arxiv-source-identity": (200, 6777, QUERY_SHA[0], 3),
    "openalex-exact-a-bridge": (200, 634, QUERY_SHA[1], 0),
    "openalex-exact-bridge-c": (200, 796, QUERY_SHA[2], 0),
    "openalex-exact-a-c": (200, 609, QUERY_SHA[3], 0),
    "s2-a-citations-references": (429, 174, QUERY_SHA[4], None),
    "s2-bridge-citations-references": (429, 174, QUERY_SHA[4], None),
    "s2-c-citations-references": (429, 174, QUERY_SHA[4], None),
    "openalex-normalized-a-bridge": (200, 511, QUERY_SHA[5], 0),
    "openalex-normalized-bridge-c": (200, 553, QUERY_SHA[6], 0),
    "openalex-normalized-a-c": (200, 565, QUERY_SHA[7], 0),
    "openalex-shuffled-1": (200, 633, QUERY_SHA[8], 0),
    "openalex-shuffled-2": (200, 961, QUERY_SHA[9], 0),
    "openalex-shuffled-3": (200, 883, QUERY_SHA[10], 0),
}

RELATION_FIELDS: Final = {
    "source_identity",
    "subject_object_type",
    "predicate_type",
    "object_object_type",
    "direction",
    "polarity",
    "passage",
    "passage_location",
    "passage_extract_id",
    "assumptions",
    "limitations",
}
RELATIONS: Final = {
    "A_to_bridge": {
        "source": (
            "arXiv:2602.04643v2",
            "learned_time_series_anomaly_prediction_representation",
            "instantiates_as",
            "causal_limit_order_book_latent_build_up_regime",
            "A_to_bridge",
            "A-SOFT-CODEBOOK",
        ),
        "target": (
            "arXiv:2604.20949v1",
            "learned_time_series_anomaly_prediction_representation",
            "instantiates_as",
            "causal_limit_order_book_latent_build_up_regime",
            "A_to_bridge",
            "BRIDGE-THREE-REGIME",
        ),
    },
    "bridge_to_C": {
        "source": (
            "arXiv:2604.20949v1",
            "causal_limit_order_book_latent_build_up_regime",
            "maps_to_or_drives",
            "intrinsic_network_liquidity_measure",
            "bridge_to_C",
            "BRIDGE-IDENTIFIABILITY",
        ),
        "target": (
            "arXiv:1402.2198v1",
            "causal_limit_order_book_latent_build_up_regime",
            "maps_to_or_drives",
            "intrinsic_network_liquidity_measure",
            "bridge_to_C",
            "C-LIQUIDITY-DEFINITION",
        ),
    },
}


def _json(path: Path) -> JsonMapping:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"resolution.document.mapping:{path.name}"
    return payload


def _mapping(value: JsonValue) -> JsonMapping:
    assert isinstance(value, dict), "resolution.value.mapping"
    return value


def _mappings(value: JsonValue) -> list[JsonMapping]:
    assert isinstance(value, list), "resolution.value.mapping_list"
    return [_mapping(item) for item in value]


def _string(value: JsonValue) -> str:
    assert isinstance(value, str) and value.strip(), "resolution.value.nonblank_string"
    return value


def _strings(value: JsonValue) -> list[str]:
    assert isinstance(value, list), "resolution.value.string_list"
    values = [_string(item) for item in value]
    assert values, "resolution.value.nonempty_string_list"
    return values


def validate_relations(root: Path, extracts: dict[str, JsonMapping]) -> None:
    packet = _json(root / "typed-relations.json")
    assert packet["accepted_bridge"] is False, "resolution.relation.accepted_bridge.false"
    assert packet["shared_bridge_identity"] == "latent_limit_order_book_build_up_regime", (
        "resolution.relation.shared_bridge.exact"
    )
    assert packet["composition_justification"] == "unsupported", (
        "resolution.relation.composition.unsupported"
    )
    for relation_name, expected_sides in RELATIONS.items():
        relation = _mapping(packet[relation_name])
        assert set(relation) == {"source", "target"}, "resolution.relation.sides.exact"
        for side_name, expected in expected_sides.items():
            fields = _mapping(relation[side_name])
            assert set(fields) == RELATION_FIELDS, "resolution.relation.fields.exact"
            identity, subject, predicate, object_type, direction, extract_id = expected
            assert fields["source_identity"] == identity, (
                "resolution.relation.source_identity.exact"
            )
            assert (fields["subject_object_type"], fields["object_object_type"]) == (
                subject,
                object_type,
            ), "resolution.relation.object_types.exact"
            assert fields["predicate_type"] == predicate, "resolution.relation.predicate.exact"
            assert fields["direction"] == direction, "resolution.relation.direction.exact"
            assert fields["polarity"] == "unsupported", "resolution.relation.polarity.unsupported"
            assert fields["passage_extract_id"] == extract_id, "resolution.relation.extract.exact"
            extract = extracts[extract_id]
            assert fields["passage"] == extract["quote"], "resolution.relation.passage.bound"
            assert fields["passage_location"] == extract["source_location"], (
                "resolution.relation.passage_location.bound"
            )
            _strings(fields["assumptions"])
            _strings(fields["limitations"])


def validate_ledger(root: Path, query_ids: set[str], extract_ids: set[str]) -> None:
    ledger = _json(root / "evidence-ledger.json")
    assert ledger["protocol_packet_digest"] == (
        "460986b339301e9012d56d34e5dca93bcfa30493d23b60317b9e992f9a5dc69c"
    ), "resolution.protocol.digest.frozen"
    assert ledger["authorization_state"] == "report_only", (
        "resolution.ledger.authorization.report_only"
    )
    assert ledger["source_scope"] == "fresh_external_evidence_not_admitted_to_approved_corpus", (
        "resolution.ledger.source_scope.exact"
    )
    assert ledger["full_text_inspected"] is True, "resolution.ledger.full_text.true"
    checks = _mappings(ledger["interaction_checks"])
    statuses = {_string(row["check"]): row["status"] for row in checks}
    assert statuses == INTERACTION_STATUS, "resolution.ledger.interactions.exact"
    assert len(checks) == len(INTERACTION_CONTRACTS), "resolution.ledger.interactions.exact"
    for row in checks:
        assert set(_strings(row["query_receipt_ids"])) <= query_ids, (
            "resolution.ledger.query_references.known"
        )
        observed_count, expected_queries, expected_extracts = INTERACTION_CONTRACTS[
            _string(row["check"])
        ]
        extract_values = row.get("extract_ids", [])
        assert isinstance(extract_values, list), "resolution.value.string_list"
        actual_extracts = tuple(_string(value) for value in extract_values)
        if row["check"] == "counterevidence":
            assert actual_extracts == expected_extracts, (
                "resolution.ledger.counterevidence.extracts.exact"
            )
        actual = (
            row["observed_count"],
            tuple(_strings(row["query_receipt_ids"])),
            actual_extracts,
        )
        assert actual == (observed_count, expected_queries, expected_extracts), (
            "resolution.ledger.interaction_binding.exact"
        )
    counterevidence = next(row for row in checks if row["check"] == "counterevidence")
    cited_extracts = set(_strings(counterevidence["extract_ids"]))
    assert cited_extracts <= extract_ids, "resolution.ledger.counterevidence.extracts.known"
    assert cited_extracts == {"BRIDGE-REAL-MARKET-LIMIT", "BRIDGE-SAMPLE-LIMIT"}, (
        "resolution.ledger.counterevidence.extracts.exact"
    )
    assert _mapping(ledger["negative_controls"]) == CONTROLS, "resolution.ledger.controls.exact"
    history = _mapping(ledger["historical_cycle_comparison"])
    assert set(history) == set(HISTORY), "resolution.ledger.history.exact"
    assert history["new_primary_source"] == HISTORY["new_primary_source"], (
        "resolution.ledger.history.new_primary_source"
    )
    assert history["distinct_middle_object"] == HISTORY["distinct_middle_object"], (
        "resolution.ledger.history.middle_object"
    )
    assert history == HISTORY, "resolution.ledger.history.exact"
    assert _mapping(ledger["predecessor"]) == PREDECESSOR, "resolution.ledger.predecessor.exact"
    assert ledger["typed_relation_results"] == {
        "A_to_bridge": "unsupported",
        "bridge_to_C": "unsupported",
        "composition": "unsupported",
    }, "resolution.ledger.relations.exact"
    assert ledger["result"] == "insufficient_evidence", "resolution.ledger.result.insufficient"
    assert ledger["candidate_combinations"] == [], "resolution.ledger.combinations.empty"
    assert ledger["candidate_outputs"] == [], "resolution.ledger.outputs.empty"
    assert ledger["accepted_bridge"] is False, "resolution.ledger.accepted_bridge.false"
    assert ledger["evidence_sufficient"] is False, "resolution.ledger.evidence_sufficient.false"
    assert ledger["human_acceptance"] == "not_requested", (
        "resolution.ledger.acceptance.not_requested"
    )
    assert ledger["operator_c_status"] == "blocked", "resolution.ledger.operator_c.blocked"
    assert ledger["operator_d_status"] == "blocked", "resolution.ledger.operator_d.blocked"
    assert ledger["runtime_authorized"] is False, "resolution.ledger.runtime.false"
    assert ledger["schema_admission_authorized"] is False, "resolution.ledger.schema.false"
    assert ledger["universal_absence_claimed"] is False, "resolution.ledger.universal_absence.false"
    assert ledger["independent_review_status"] == "not_requested_todo_6_separate", (
        "resolution.ledger.review.todo_6_separate"
    )
