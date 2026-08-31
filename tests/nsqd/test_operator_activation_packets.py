from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from nsqd.domain.diverge import operator_decisions
from nsqd.domain.snapshot import is_utc_datetime

PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
)
PACKET_IDS = ("c", "d", "e", "f", "g")


def _load(name: str) -> dict[str, Any]:
    payload = yaml.safe_load((PACKET_ROOT / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_deferred_operator_packets_bind_report_only_plan_metadata() -> None:
    for operator_id in PACKET_IDS:
        packet = _load(f"operator-{operator_id}.yaml")
        assert packet["packet_kind"] == "evidence_plan"
        assert packet["authorization_state"] == "report_only"
        assert packet["runtime_authorized"] is False
        assert packet["evidence_sufficient"] is False
        assert packet["algorithm_identity"] == "not_run"
        assert packet["prompt_identity"] == "not_run"
        assert packet["candidate_outputs"] == []
        assert packet["nearest_prior_art"] == []
        assert isinstance(packet["input_bindings"], list)
        assert isinstance(packet["known_limitations"], list)
        created_at = datetime.fromisoformat(str(packet["created_at_utc"]).replace("Z", "+00:00"))
        assert is_utc_datetime(created_at)


def test_packet_provenance_covers_selected_records_and_e_inventory() -> None:
    c_packet = _load("operator-c.yaml")
    assert c_packet["input_snapshot_ids"] == [
        "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5"
    ]
    assert c_packet["preferred_pair"]["literature_a"]["record_id"] == "N11-OPT-02"
    assert c_packet["preferred_pair"]["literature_c"]["record_id"] == "N11-FIN-04"

    e_packet = _load("operator-e.yaml")
    manifests = {binding["manifest"] for binding in e_packet["input_bindings"]}
    assert manifests == {
        "../nsqd-projection-review-2026-08-28/final/manifest.toml",
        "../../../tests/fixtures/approved/nsqd/manifest.toml",
    }
    assert e_packet["scope_decision"] == "same_policy_and_cross_policy_separate_tracks"
    assert "executable tau authorizes Operator E" in e_packet["forbidden_inferences"]


def test_failure_packet_and_contract_remain_empty_and_fail_closed() -> None:
    g_packet = _load("operator-g.yaml")
    contract = _load("failure-record-contract.yaml")
    assert g_packet["approved_failure_corpus"] is None
    assert g_packet["approved_failure_record_ids"] == []
    assert contract["template_only"] is True
    assert contract["operator_g_eligible_by_default"] is False
    assert "changed_condition_triggers" in contract["operator_g_eligibility_rules"][2]
    assert "restart_conditions" in contract["operator_g_eligibility_rules"][3]


def test_runtime_still_rejects_every_planned_operator() -> None:
    decisions = {row.operator_id: row for row in operator_decisions()}
    for operator_id in ("C", "D", "E", "F", "G"):
        assert decisions[operator_id].activation == "deferred"
        assert decisions[operator_id].runtime_enabled is False
