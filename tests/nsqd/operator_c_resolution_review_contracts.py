from __future__ import annotations

from typing import Final

PACKET_DIGEST: Final = "8bec12564b873d1ae59a60ed0988b766e66909e7efa62a11a3fc027cfe06dd90"
MANIFEST_SHA256: Final = "baf5ab583e294c4eebee2fcaa2cc73c5e4a985cfd74005af7cf21a39e4aa0abf"
SUMMARY_SHA256: Final = "643fc415cc2f6b266a7a8bf4c04fdf11e34ede3947dd3be090ad241d3a5f04d4"
REVIEWED_AT: Final = "2026-09-10T02:28:53Z"
REVIEWER_IDENTITY: Final = "oracle / independent-evidence-reviewer"
REVIEWER_SESSION: Final = "ses_f76edce6dffe6gPRxa2M13UADd"
PRODUCER_IDENTITY: Final = "Sisyphus-Junior"
PRODUCER_SESSION: Final = "ses_f782300deffeTwlc03Dk8T8Cdz"
APPROVAL_SCOPE: Final = "bounded_negative_report_only_evidence_conclusion"

EVIDENCE_ARTIFACTS: Final = {
    "README.md": "213382cf673e63049d941bbf3e37b461a6bad48ff91c25f595ed91df6993bd36",
    "acquisition-receipts.json": "082168d9014904b3eee00c4fa0358a9f100acf8a029dabb9fc910b6bb38ea213",
    "bibliographic-query-receipts.json": (
        "b0be5323ddd7b46939320ce2efe488785742d090c0722e0626716d390e2e67a8"
    ),
    "evidence-ledger.json": "fc70c082fb821a5eaf21d6ec56acaa83194536f6bd64311ceb19355d7cd1a71c",
    "source-extracts.jsonl": "d9c92f4257fd41cc32bb204c765254125288088d8c08b19e828e4aae1fa355d4",
    "typed-relations.json": "f737e4747d2bc18deb2cb4c5fd4150ca8797e5f1a6092356d8d6c44ca4ceff0c",
}

SUMMARY_FIELDS: Final = {
    "schema_version",
    "packet_digest",
    "packet_digest_algorithm",
    "packet_manifest_sha256",
    "artifact_sha256",
    "independent_review",
    "adversarial_verify",
    "findings",
    "source_replay",
    "passage_replay",
    "relation_analysis",
    "interaction_analysis",
    "live_query_replay",
    "control_replay",
    "verification",
    "predecessor_and_chain",
    "authority",
    "limitations",
    "cleanup",
}
REVIEW_FIELDS: Final = {
    "reviewer_identity",
    "reviewer_agent_type",
    "reviewer_model",
    "reviewer_session_id",
    "producer_identity",
    "producer_session_id",
    "reviewer_differs_from_producer",
    "reviewer_session_differs_from_producer_session",
    "reviewed_at_utc",
    "approval_scope",
}
SEAL_FIELDS: Final = {
    "schema_version",
    "packet_digest",
    "review_summary_sha256",
    "reviewer_identity",
    "reviewer_agent_type",
    "reviewer_model",
    "reviewer_session_id",
    "producer_identity",
    "producer_session_id",
    "reviewed_at_utc",
    "verdict",
    "approval_scope",
    "authorization_state",
    "accepted_bridge",
    "evidence_sufficient",
    "technical_review_is_human_acceptance",
    "human_acceptance",
    "schema_admission_authorized",
    "runtime_authorized",
    "todo_7_advancement_authorized",
}

SOURCE_REPLAY: Final = {
    "arXiv:2602.04643v2": (
        2647744,
        "ef56d2b2f2d701667f853c0bb69795fa58f7acbca16fbca27629852550983668",
    ),
    "arXiv:2604.20949v1": (
        1182734,
        "4680476871fd7b23842977cec7fe35b69a838606cbddc0e5df3c68942897bd68",
    ),
    "arXiv:1402.2198v1": (
        1613669,
        "4b65227e4da7eaaaaf381c20c8716e0c1c99d80abfd188d6bf0456c5f30bc166",
    ),
}

AUTHORITY: Final = {
    "authorization_state": "report_only",
    "source_scope": "fresh_external_evidence_not_admitted_to_approved_corpus",
    "accepted_bridge": False,
    "candidate_combinations": [],
    "candidate_outputs": [],
    "evidence_sufficient": False,
    "result": "insufficient_evidence",
    "technical_review": "confirmed_negative_conclusion",
    "technical_review_is_human_acceptance": False,
    "human_acceptance": "not_requested",
    "operator_c_status": "blocked",
    "operator_d_status": "blocked",
    "schema_admission_authorized": False,
    "runtime_authorized": False,
    "universal_absence_claimed": False,
    "todo_7_advancement_authorized": False,
}
