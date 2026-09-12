from __future__ import annotations

from pathlib import Path

import yaml

from nsqd.domain import contract_validation
from nsqd.domain.contract_validation import StructuredInput

D_PACKET_ROOT = (
    Path(__file__).resolve().parents[2] / "docs" / "reviews" / "nsqd-operator-activation-2026-08-30"
)
D_CONTRACT_PATH = D_PACKET_ROOT / "analogical-transport-contract.yaml"
G_CONTRACT_PATH = D_PACKET_ROOT / "failure-record-contract.yaml"
G_V2_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reviews"
    / "nsqd-operator-g-failure-record-contract-2026-09-11-v2"
    / "failure-record-contract-v2.yaml"
)


def operator_d_contract() -> dict[str, StructuredInput]:
    loaded: StructuredInput = yaml.safe_load(D_CONTRACT_PATH.read_text(encoding="utf-8"))
    mapping = contract_validation.as_mapping(loaded, "operator D mapping contract fixture")
    return mapping


def operator_d_graph(*, prefix: str, predicate: str) -> dict[str, StructuredInput]:
    return {
        "nodes": [
            {"id": f"{prefix}-problem", "role": "problem"},
            {"id": f"{prefix}-method", "role": "method"},
        ],
        "relations": [
            {
                "source": f"{prefix}-problem",
                "predicate": predicate,
                "target": f"{prefix}-method",
            }
        ],
    }


def operator_d_proposal() -> dict[str, StructuredInput]:
    return {
        "schema_version": 1,
        "proposal_id": "D-MAP-001",
        "authorization_state": "report_only",
        "runtime_authorized": False,
        "source_domain_policy_id": "optimization/1",
        "target_domain_policy_id": "finance/1",
        "source_record_id": "N11-OPT-02",
        "target_record_id": "N11-FIN-04",
        "source_graph": operator_d_graph(prefix="opt", predicate="solved_by"),
        "target_graph": operator_d_graph(prefix="fin", predicate="explained_by"),
        "allowed_relation_mappings": [
            {"source_predicate": "solved_by", "target_predicate": "explained_by"}
        ],
        "forbidden_surface_attributes": ["title", "venue"],
        "target_constraints": ["no_policy_leak", "no_approved_fact"],
        "mapping_method": "typed_structure_mapping",
        "baselines": ["typed_structure_mapping"],
        "negative_controls": ["surface_similarity_negative_control"],
        "metrics": [
            "held_out_analogy_recovery",
            "role_consistency",
            "target_contradiction_rate",
            "domain_policy_violation_count",
        ],
        "upstream_c": {
            "evidence_sufficient": False,
            "human_accepted": False,
            "selected_bridge_id": None,
        },
        "candidate_inferences": [],
        "provenance": {
            "generated_by": "agent:d-proposer",
            "source_artifact_digests": ["c" * 64],
        },
        "review": {
            "status": "pending",
            "human_reviewer": None,
            "human_approved_at_utc": None,
            "approved_proposal_digest": None,
        },
    }


def operator_g_contract() -> dict[str, StructuredInput]:
    loaded: StructuredInput = yaml.safe_load(G_CONTRACT_PATH.read_text(encoding="utf-8"))
    mapping = contract_validation.as_mapping(loaded, "Operator G failure contract fixture")
    return mapping


def operator_g_contract_v2() -> dict[str, StructuredInput]:
    loaded: StructuredInput = yaml.safe_load(G_V2_CONTRACT_PATH.read_text(encoding="utf-8"))
    return contract_validation.as_mapping(loaded, "Operator G v2 failure contract fixture")


def operator_g_record() -> dict[str, StructuredInput]:
    return {
        "schema_version": 1,
        "failure_record_id": "G-FAIL-001",
        "authorization_state": "report_only",
        "operator_g_eligible": False,
        "domain_policy_id": "finance/1",
        "experiment_id": "experiment-001",
        "source_class": "registered_experiment_artifact",
        "immutable_source_artifact_digests": ["a" * 64],
        "original_conditions": {
            "code_revision": "b" * 40,
            "data_snapshot_ids": ["c" * 64],
            "configuration_digest": "d" * 64,
            "model_or_method_identity": "forecast-model/1",
            "started_at_utc": "2026-09-05T18:00:00Z",
            "completed_at_utc": "2026-09-05T18:30:00Z",
        },
        "outcome": {
            "failure_class": "method",
            "bounded_observation": "Validation loss exceeded the registered baseline.",
            "measured_results": {"validation_loss": 1.2, "baseline_loss": 1.0},
            "evidence_artifact_digests": ["e" * 64],
        },
        "changed_condition_triggers": [
            {
                "trigger_id": "trigger-001",
                "predicate": "data regime changes from calm to stress",
                "previous_condition": "calm",
                "new_condition": "stress",
                "evidence_artifact_digests": ["f" * 64],
                "resurrection_scope": "test_only",
            }
        ],
        "restart_conditions": [
            {
                "condition_id": "restart-001",
                "predicate": "stress benchmark is available",
                "scope": "test_only",
            }
        ],
        "provenance": {"generated_by": "agent:g-recorder"},
        "review": {
            "review_status": "pending",
            "human_reviewer": None,
            "human_approved_at_utc": None,
            "approved_record_digest": None,
        },
    }
