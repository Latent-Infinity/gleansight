from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonMapping = dict[str, JsonValue]

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
REVIEWS_ROOT: Final = REPO_ROOT / "docs" / "reviews"
SUMMARY_NAME: Final = "technical-review-summary.json"
SEAL_NAME: Final = "technical-review-seal.json"
REVIEWED_AT: Final = "2026-09-11T18:46:01Z"
REVIEWER_IDENTITY: Final = "Sisyphus-Junior / independent-successor-reviewer"
REVIEWER_SESSION: Final = "ses_f6e3fb903ffeX24UAPy59bNEUv"
REVIEWER_MODEL: Final = "openai/gpt-5.6-sol"
EXECUTOR_SESSION: Final = "ses_f6e596d6fffeAOQmhjfEDustRj"
SCOPE_NAME: Final = "correction_successor_integrity_semantics_and_non_authority"


@dataclass(frozen=True, slots=True)
class Successor:
    label: str
    directory: str
    manifest_sha256: str
    packet_digest: str

    @property
    def root(self) -> Path:
        return REVIEWS_ROOT / self.directory


SUCCESSORS: Final = (
    Successor(
        "C",
        "nsqd-operator-c-evidence-resolution-2026-09-11-readme-correction",
        "fb27d839695e914051dad484d53cfd228de4724099dbc78f99793ab59528acf6",
        "65e6f4d684dec0ef3867a6664f0d542ed55b30b8a6067c0f3f331ec4d1509687",
    ),
    Successor(
        "F",
        "nsqd-operator-f-readiness-2026-09-11-formula-correction",
        "72e21375a988d73dcc4781e44739cccdd87ffc37f9eae22e83bf754543773b96",
        "677932da4b0ecfeea26a0a80558314e1ee1a11b635877e15860cc9fc88775a2b",
    ),
    Successor(
        "status",
        "nsqd-status-window-calendar-replay-2026-09-11-command-sync",
        "f2009436db6076604c0a64a1600834a1b5b1f5695f1dfcacd077f417611a01ab",
        "0839478d96311ef2540b0dc394051860b253d160de6f8ea6d34955f3dd424acd",
    ),
    Successor(
        "activation",
        "nsqd-operator-activation-2026-09-11-remediation",
        "0d1e835ce09827666f35cc1b23b5ad041b974b55f9525011a17a1fb57bb43ebc",
        "824e8f71cc3f18ff89b300736bcbdb31863fc2fc812af6a2095e45856dbc9b6e",
    ),
)

REVIEWER: Final[JsonMapping] = {
    "identity": REVIEWER_IDENTITY,
    "session_id": REVIEWER_SESSION,
    "model": REVIEWER_MODEL,
    "executor_session_id": EXECUTOR_SESSION,
    "reviewer_differs_from_executor": True,
    "predecessor_reviewer_identity_reused": False,
    "predecessor_review_time_reused": False,
}
REVIEW_SCOPE: Final[JsonMapping] = {
    "name": SCOPE_NAME,
    "successor_claims_within_scope_verified": True,
    "successor_members_parsed": 19,
    "covered": [
        "successor member hashes and manifest closure",
        "canonical packet digests and exact manifest SHA-256 values",
        "historical C/F/G/status/activation byte preservation",
        "predecessor links and absence of self or circular bindings",
        "C README-only correction and copied evidence identity",
        "F approved formulas and implementation/test bindings",
        "status retained replay, command synchronization, determinism, and fail-closed "
        "current-receipt behavior",
        "activation overlay bindings and disabled authority state",
        "exact nine-line historical whitespace exception inventory",
    ],
    "excluded": [
        "human evidence acceptance",
        "new schema or operational authorization",
        "live reacquisition of copied C external sources",
        "re-observation of the original historical scratch SQLite",
        "generation or approval of a final G census",
    ],
}
VERIFICATION: Final[JsonMapping] = {
    "member_hashes_and_packet_digests": "all exact",
    "historical_byte_pins": "all exact",
    "copied_C_evidence_members": "5/5 byte-identical",
    "copied_status_evidence_members": "3/3 byte-identical",
    "trailing_whitespace_exceptions": (
        "exactly 9 lines across the 3 declared path/digest/count entries"
    ),
    "focused_tests": "196 passed",
    "tamper_and_stale_tests": "120 passed",
    "ruff": "passed",
    "ty": "passed",
    "retained_replay": "passed with 11 records",
    "deterministic_rebuild": "two rebuilds reproduced all 6 status successor members exactly",
    "current_receipt": "strictly failed closed because historical SQLite was absent; no new "
    "current-receipt observation was claimed",
    "temporary_paths_remaining": 0,
}
LIMITATIONS: Final[list[JsonValue]] = [
    "The original historical scratch SQLite bytes were unavailable and were not independently "
    "re-observed. Their claim is preserved only as predecessor provenance; strict verification "
    "correctly failed closed.",
    "Copied C external source bytes were not independently reacquired or re-observed. This review "
    "confirms their byte-identical transfer and predecessor-only review status, not their "
    "underlying external evidence.",
    "This is a technical successor review only and does not broaden into human evidence "
    "acceptance.",
]
AUTHORITY: Final[JsonMapping] = {
    "technical_review_is_human_acceptance": False,
    "human_acceptance": "not_requested",
    "evidence_approval_authorized": False,
    "evidence_sufficiency_authorized": False,
    "schema_admission_authorized": False,
    "operational_authority_granted": False,
    "runtime_authorized": False,
    "operator_activation_authorized": False,
    "packet_inclusion_authorized": False,
    "restart_authorized": False,
    "resurrection_authorized": False,
    "todo_advancement_authorized": False,
    "final_g_census_authorized": False,
}


def json_mapping(path: Path) -> JsonMapping:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"technical_review.mapping:{path.name}"
    return payload


def mapping(value: JsonValue) -> JsonMapping:
    assert isinstance(value, dict), "technical_review.value.mapping"
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_summary(summary: JsonMapping) -> None:
    assert set(summary) == {
        "schema_version",
        "verdict",
        "seal_ready",
        "reviewed_at_utc",
        "reviewer",
        "review_scope",
        "successors",
        "verification",
        "findings",
        "substantive_blocker",
        "limitations",
        "authority",
    }, "technical_review.summary.fields.exact"
    assert summary["schema_version"] == 1, "technical_review.summary.schema.exact"
    assert summary["verdict"] == "PASS", "technical_review.summary.verdict.pass"
    assert summary["seal_ready"] is True, "technical_review.summary.seal_ready.true"
    assert summary["reviewed_at_utc"] == REVIEWED_AT, "technical_review.time.exact"
    assert mapping(summary["reviewer"]) == REVIEWER, "technical_review.reviewer.exact"
    assert mapping(summary["review_scope"]) == REVIEW_SCOPE, "technical_review.scope.exact"
    assert mapping(summary["successors"]) == {
        item.label: {
            "manifest_sha256": item.manifest_sha256,
            "packet_digest": item.packet_digest,
            "review_status": "review_pending",
        }
        for item in SUCCESSORS
    }, "technical_review.successors.exact"
    assert mapping(summary["verification"]) == VERIFICATION, "technical_review.verification.exact"
    assert summary["findings"] == [], "technical_review.findings.empty"
    assert summary["substantive_blocker"] is None, "technical_review.blocker.absent"
    assert summary["limitations"] == LIMITATIONS, "technical_review.limitations.exact"
    assert mapping(summary["authority"]) == AUTHORITY, "technical_review.authority.exact"


def validate_seal(seal: JsonMapping, successor: Successor, summary_sha256: str) -> None:
    expected = {
        "schema_version": 1,
        "verdict": "PASS",
        "technical_review_summary_sha256": summary_sha256,
        "packet_manifest_sha256": successor.manifest_sha256,
        "packet_digest": successor.packet_digest,
        "reviewed_at_utc": REVIEWED_AT,
        "reviewer": REVIEWER,
        "review_scope": SCOPE_NAME,
        "limitations": LIMITATIONS,
        "authority": AUTHORITY,
    }
    assert seal == expected, "technical_review.seal.exact"


def validate_chain(successor: Successor) -> str:
    manifest = json_mapping(successor.root / "packet-manifest.json")
    artifacts = mapping(manifest["artifact_sha256"])
    assert SUMMARY_NAME not in artifacts and SEAL_NAME not in artifacts, (
        "technical_review.manifest.detached"
    )
    assert sha256(successor.root / "packet-manifest.json") == successor.manifest_sha256, (
        "technical_review.manifest.sha256.exact"
    )
    assert manifest["packet_digest"] == successor.packet_digest, (
        "technical_review.packet_digest.exact"
    )
    summary_path = successor.root / SUMMARY_NAME
    summary = json_mapping(summary_path)
    validate_summary(summary)
    summary_sha256 = sha256(summary_path)
    seal = json_mapping(successor.root / SEAL_NAME)
    validate_seal(seal, successor, summary_sha256)
    return summary_sha256
