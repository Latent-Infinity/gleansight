from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from nsqd.domain.operator_g_types import StructuredValue

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWS_ROOT = REPO_ROOT / "docs" / "reviews"
PREDECESSOR = REVIEWS_ROOT / "nsqd-operator-activation-2026-09-11-remediation"
CLARIFICATION = REVIEWS_ROOT / "nsqd-operator-activation-2026-09-11-authority-clarification"
HISTORICAL_ACTIVATION = REVIEWS_ROOT / "nsqd-operator-activation-2026-08-30"
ACTIVE_DOCS = (
    REPO_ROOT / "docs" / "ablations" / "alg-operators.md",
    REPO_ROOT / "docs" / "ablations" / "alg-status-window.md",
    REPO_ROOT / "docs" / "algorithm-contract-nsqd.md",
    REPO_ROOT / "docs" / "development-plan-ns-qd.md",
    REPO_ROOT / "docs" / "evidence-index.md",
    REPO_ROOT / "docs" / "fact-ledger.md",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, StructuredValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _historical_tree_digest() -> str:
    payload = bytearray()
    for path in sorted(item for item in HISTORICAL_ACTIVATION.rglob("*") if item.is_file()):
        payload.extend(path.relative_to(REVIEWS_ROOT).as_posix().encode())
        payload.extend(b"\0")
        payload.extend(_sha256(path).encode())
        payload.extend(b"\0")
    return hashlib.sha256(payload).hexdigest()


def test_authority_clarification_binds_inherited_predecessor_and_base() -> None:
    status = yaml.safe_load((CLARIFICATION / "authority-status.yaml").read_text(encoding="utf-8"))
    assert isinstance(status, dict)

    assert status["review_status"] == "review_pending"
    assert status["authorization_state"] == "report_only"
    assert status["predecessor"] == {
        "manifest": "../nsqd-operator-activation-2026-09-11-remediation/packet-manifest.json",
        "manifest_sha256": "0d1e835ce09827666f35cc1b23b5ad041b974b55f9525011a17a1fb57bb43ebc",
        "packet_digest": "824e8f71cc3f18ff89b300736bcbdb31863fc2fc812af6a2095e45856dbc9b6e",
        "review_validity": "valid_for_predecessor_only",
    }
    assert status["inherited_activation_tree"] == {
        "path": "../nsqd-operator-activation-2026-08-30",
        "tree_sha256": "34dccff0d4c15c2bf193e66a79c933963af51c7553a4159f00a506f0906e0709",
    }
    assert status["base_reference"] == {
        "commit": "e29685b92d2f8ee88fcf0584556e5e8bc9df31aa",
        "tree": "8ce1217183659ad05b2544f0390a9ee2eb4bf6ea",
    }
    assert _historical_tree_digest() == status["inherited_activation_tree"]["tree_sha256"]
    assert _sha256(PREDECESSOR / "packet-manifest.json") == status["predecessor"]["manifest_sha256"]


def test_historical_f_claim_is_unverified_and_non_authorizing() -> None:
    status = yaml.safe_load((CLARIFICATION / "authority-status.yaml").read_text(encoding="utf-8"))
    assert isinstance(status, dict)

    claim = status["historical_claim"]
    assert claim["proposal_id"] == "F-PROP-001"
    assert claim["recorded_status"] == "human_approved"
    assert claim["current_trust_status"] == "historical_claim_unverified"
    assert claim["detached_trust_evidence_present"] is False
    assert claim["actual_human_decision_disposition"] == "not_determined"
    authority = status["authority"]
    assert isinstance(authority, dict)
    assert authority and all(value is False for value in authority.values())


def test_authority_clarification_manifest_is_closed_and_deterministic() -> None:
    manifest = _json(CLARIFICATION / "packet-manifest.json")
    artifacts = manifest["artifact_sha256"]
    assert isinstance(artifacts, dict)
    assert set(artifacts) == {"README.md", "authority-status.yaml"}
    assert artifacts == {name: _sha256(CLARIFICATION / name) for name in sorted(artifacts)}
    preimage = json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()
    assert manifest["packet_digest"] == hashlib.sha256(preimage).hexdigest()


def test_active_docs_publish_current_trust_classification() -> None:
    for path in ACTIVE_DOCS:
        body = path.read_text(encoding="utf-8")
        assert "nsqd-operator-activation-2026-09-11-authority-clarification" in body
        assert "historical_claim_unverified" in body


def test_ev_n20_requires_portable_replay_and_keeps_strict_check_separate() -> None:
    documents = (
        REPO_ROOT / "docs" / "evidence-index.md",
        REPO_ROOT / "docs" / "development-plan-ns-qd.md",
    )
    for path in documents:
        ev_n20 = next(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("| EV-N20 |")
        )
        command = ev_n20.split("|")[3]
        assert "--verify-retained-replay" in command
        assert "--verify-current-receipt" not in command
