from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from nsqd.domain.card import card_decision, missing_card_fields
from nsqd.domain.diverge import (
    normalize_axiom_rows,
    require_no_axiom_inversion,
    require_operator,
    select_target_cell,
)
from nsqd.domain.grounding import GroundingClass
from nsqd.domain.novelty import (
    NOVELTY_TAU_SEMANTICS,
    NOVELTY_THRESHOLD_TAU,
    SnapshotState,
    apply_novelty_threshold,
    novelty_term,
    require_snapshot_state,
)
from nsqd.domain.operator_e import (
    OPERATOR_E_ATYPICALITY_INTERPRETATION,
    report_only_operator_e_candidate_hash,
)
from nsqd.domain.policy import FINANCE_POLICY, archive_cell_key
from nsqd.domain.project import (
    canonical_reviewed_projection_digest,
    normalize_paraphrase,
    projection_record_id,
)
from nsqd.domain.snapshot import canonical_json, sha256_hex
from nsqd.domain.status import require_cell_status
from nsqd.domain.tau_measurement import (
    qualify_tau_measurement_pair,
    tau_measurement_artifact_digest,
)
from nsqd.domain.trusted_files import (
    read_verified_repo_file,
    require_non_symlink_leaf,
    require_non_symlink_path_within_root,
)
from nsqd.domain.trusted_files import (
    sha256_file_digest as _trusted_sha256_file_digest,
)
from nsqd.domain.viability import score_dpred, score_dval, score_fals, score_mech, viability

MATCHED_COUNT = 3
FINANCE_POLICY_ID = "finance/1"
APPROVED_CORPUS_SNAPSHOT_ID = "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5"
APPROVED_CORPUS_VERSION = 11
APPROVED_CORPUS_RECORD_COUNT = 11
FILTERED_FINANCE_RECORD_COUNT = 6
APPROVED_SNAPSHOT_SCOPE = "approved_corpus_snapshot"
APPROVED_FINANCE_RECORD_IDS = (
    "DATA-NSQD-03",
    "N11-FIN-01",
    "N11-FIN-02",
    "N11-FIN-03",
    "N11-FIN-04",
    "N11-FIN-05",
)
APPROVED_EMBEDDING_MODEL = {
    "provider": "ollama",
    "model_name": "qwen3-embedding:latest",
    "model_id": "qwen3-embedding",
    "model_version": "latest",
    "installed_model_digest": ("64b933495768fbd3b87c20583d379728a07471e0c66733a9df87cd1901b3c44b"),
    "model_blob_sha256": "3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85",
    "embedding_dimension": 4096,
    "distance_metric": "cosine_distance",
    "normalization_policy": "l2",
}
REPO_ROOT = Path(__file__).resolve().parents[3]
APPROVED_FIXTURE_MANIFEST_PATH = Path("tests/fixtures/approved/nsqd/manifest.toml")
APPROVED_FINAL_MANIFEST_PATH = Path(
    "docs/reviews/nsqd-projection-review-2026-08-28/final/manifest.toml"
)
APPROVED_FIXTURE_ROOT = Path("tests/fixtures/approved/nsqd")
APPROVED_FINAL_ROOT = Path("docs/reviews/nsqd-projection-review-2026-08-28/final")
BLIND_REVIEW_SALT = "nsqd-jepa-human-review/1"
ALLOWED_SCRATCH_PREFIX = "nsqd-jepa-baselines-"
MAX_RECEIPT_TREE_FILES = 4096
MAX_RECEIPT_TREE_BYTES = 64 * 1024 * 1024
MAX_RECEIPT_SQLITE_BYTES = 512 * 1024 * 1024
ALLOWED_DUPLICATE_DECISIONS = frozenset({"distinct", "collapse_same_idea_variants"})
PLACEHOLDER_REVIEWER_IDENTITIES = frozenset({"human_required", "not_requested"})
BLIND_REVIEW_CONTENT_FIELDS = (
    "proposal_title",
    "proposal_summary",
    "mechanistic_rationale",
    "falsifiable_test",
    "primary_metric",
)
BLIND_FORBIDDEN_TOKENS = (
    "operator",
    "a-base",
    "b-base",
    "e-report",
    "jepa-idea",
    "source_fact_id",
    "source_record_id",
    "n11-fin",
    "data-nsqd",
    "artifact_hash",
)


def evaluate_matched_count_operator_baselines(
    ideas: Sequence[Mapping[str, object]],
    *,
    extracted_facts: Sequence[Mapping[str, object]],
    baseline_execution: Mapping[str, object],
    operator_e_candidates: Sequence[Mapping[str, object]],
    blinded_review_packet: Mapping[str, object],
    audit_manifest: Mapping[str, object],
) -> dict[str, Any]:
    idea_rows = _require_ideas(ideas)
    ideas_by_id = {str(row["candidate_id"]): row for row in idea_rows}
    fact_rows = _require_extracted_facts(extracted_facts)
    facts_by_id = {str(row["fact_id"]): row for row in fact_rows}
    baseline = _require_baseline_execution(baseline_execution)
    raw_candidate_ids = (
        [
            _required_string(
                _required_string_keyed_mapping(row, "operator_a_artifact"), "candidate_id"
            )
            for row in baseline["operator_a_artifacts"]
        ]
        + [
            _required_string(
                _required_string_keyed_mapping(row, "operator_b_artifact"), "candidate_id"
            )
            for row in baseline["operator_b_artifacts"]
        ]
        + [
            _required_string(
                _required_string_keyed_mapping(row, "operator_e_candidate"), "artifact_id"
            )
            for row in operator_e_candidates
        ]
    )
    if len(raw_candidate_ids) != len(set(raw_candidate_ids)):
        raise ValueError("candidate ids must be unique across A/B/E")
    raw_artifact_hashes = (
        [
            _required_sha256(
                _required_string_keyed_mapping(row, "operator_a_artifact"),
                "candidate_artifact_hash",
            )
            for row in baseline["operator_a_artifacts"]
        ]
        + [
            _required_sha256(
                _required_string_keyed_mapping(row, "operator_b_artifact"),
                "candidate_artifact_hash",
            )
            for row in baseline["operator_b_artifacts"]
        ]
        + [
            _required_sha256(
                _required_string_keyed_mapping(row, "operator_e_candidate"), "artifact_hash"
            )
            for row in operator_e_candidates
        ]
    )
    if len(raw_artifact_hashes) != len(set(raw_artifact_hashes)):
        raise ValueError("artifact hashes must be unique across A/B/E")
    runtime_receipt = _require_execution_receipt(baseline["execution_receipt"])
    a_rows = [
        _require_a_artifact(
            row,
            index=index,
            approved_projection_digests=baseline["approved_projection_digests"],
            projected_bindings=baseline["projected_bindings"],
            facts_by_id=facts_by_id,
        )
        for index, row in enumerate(baseline["operator_a_artifacts"])
    ]
    b_rows = [
        _require_b_artifact(
            row,
            index=index,
            approved_projection_digests=baseline["approved_projection_digests"],
            projected_bindings=baseline["projected_bindings"],
        )
        for index, row in enumerate(baseline["operator_b_artifacts"])
    ]
    e_rows = [
        _require_e_candidate(row, index=index, ideas_by_id=ideas_by_id)
        for index, row in enumerate(operator_e_candidates)
    ]
    candidate_ids = (
        [str(row["candidate_id"]) for row in a_rows]
        + [str(row["candidate_id"]) for row in b_rows]
        + [str(row["artifact_id"]) for row in e_rows]
    )
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate ids must be unique across A/B/E")
    a_fact_ids = [str(row["source_fact_id"]) for row in a_rows]
    if len(a_fact_ids) != len(set(a_fact_ids)):
        raise ValueError("Operator A source_fact_id values must be unique")
    artifact_hashes = (
        [str(row["artifact_hash"]) for row in a_rows]
        + [str(row["artifact_hash"]) for row in b_rows]
        + [str(row["artifact_hash"]) for row in e_rows]
    )
    if len(artifact_hashes) != len(set(artifact_hashes)):
        raise ValueError("artifact hashes must be unique across A/B/E")
    _validate_execution_receipt_against_packet(
        runtime_receipt,
        candidate_rows=[*a_rows, *b_rows],
    )
    review_packet = _require_blinded_review_packet(
        blinded_review_packet,
        expected_item_count=len(artifact_hashes),
    )
    known_artifacts = {row["artifact_hash"]: row for row in [*a_rows, *b_rows, *e_rows]}
    audit = _require_audit_manifest(
        audit_manifest,
        review_packet=review_packet,
        known_hashes={row["artifact_hash"]: row["operator"] for row in [*a_rows, *b_rows, *e_rows]},
    )
    _validate_blinded_review_item_content(
        review_packet=review_packet,
        audit_manifest=audit,
        known_artifacts=known_artifacts,
    )
    human_review = _validate_human_review_consistency(
        review_packet=review_packet, audit_manifest=audit
    )
    review_ids = [str(item["blind_id"]) for item in review_packet["items"]]
    audit_ids = [str(item["blind_id"]) for item in audit["items"]]
    if review_ids != audit_ids:
        raise ValueError("audit manifest blind_id order must match blinded review packet")
    if len(review_ids) != len(artifact_hashes):
        raise ValueError("blinded review packet must contain exactly 9 items")
    return {
        "matched_candidate_count": MATCHED_COUNT,
        "operator_a_baseline_status": "executed_report_only",
        "operator_b_baseline_status": "executed_report_only",
        "operator_a_candidate_ids": [str(row["candidate_id"]) for row in a_rows],
        "operator_b_candidate_ids": [str(row["candidate_id"]) for row in b_rows],
        "operator_e_candidate_ids": [str(row["artifact_id"]) for row in e_rows],
        "idea_candidate_ids": sorted(ideas_by_id),
        "reviewed_usefulness_at_matched_candidate_count": human_review["matched_candidate_metrics"],
        "usefulness_review_status": human_review["usefulness_review_status"],
        "human_usefulness_review": human_review["summary"],
        "operator_e_authorization_state": "unauthorized",
        "runtime_authorized": False,
        "candidate_combinations": [],
        "blinded_review_item_count": len(review_ids),
    }


def blinded_review_packet_digest(packet: Mapping[str, object]) -> str:
    body = _mapping_without(packet, exclude={"packet_digest"})
    return sha256_hex(canonical_json(body))


def blinded_review_sort_key(*, artifact_hash: str) -> str:
    return sha256_hex(
        canonical_json({"artifact_hash": artifact_hash, "blind_review_salt": BLIND_REVIEW_SALT})
    )


def audit_manifest_digest(manifest: Mapping[str, object]) -> str:
    body = _mapping_without(manifest, exclude={"manifest_digest"})
    return sha256_hex(canonical_json(body))


def lancedb_tree_digest(path: Path) -> str:
    files: list[dict[str, str]] = []
    total_bytes = 0
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError("scratch index tree must not contain symlinks")
        if not item.is_file():
            continue
        if len(files) >= MAX_RECEIPT_TREE_FILES:
            raise ValueError("scratch index tree exceeds the verified file limit")
        payload = item.read_bytes()
        total_bytes += len(payload)
        if total_bytes > MAX_RECEIPT_TREE_BYTES:
            raise ValueError("scratch index tree exceeds the verified byte limit")
        files.append(
            {
                "path": item.relative_to(path).as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    if not files:
        raise ValueError("scratch index tree is empty")
    return sha256_hex(canonical_json({"files": files}))


def _require_baseline_execution(value: Mapping[str, object]) -> dict[str, Any]:
    baseline = _required_string_keyed_mapping(value, "baseline_execution")
    if baseline.get("packet_kind") != "matched_count_operator_baseline_report":
        raise ValueError("baseline_execution packet_kind is invalid")
    if baseline.get("authorization_state") != "report_only":
        raise ValueError("baseline_execution must be report_only")
    if baseline.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if baseline.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    if baseline.get("candidate_combinations") != []:
        raise ValueError("candidate_combinations must be empty")
    source_snapshot = _required_string_keyed_mapping(
        baseline.get("source_snapshot"), "source_snapshot"
    )
    if source_snapshot != {
        "snapshot_id": APPROVED_CORPUS_SNAPSHOT_ID,
        "corpus_version": APPROVED_CORPUS_VERSION,
        "snapshot_state": "production_valid",
        "snapshot_scope": APPROVED_SNAPSHOT_SCOPE,
        "approved_record_count": APPROVED_CORPUS_RECORD_COUNT,
        "filtered_domain_policy_id": FINANCE_POLICY_ID,
        "filtered_record_count": FILTERED_FINANCE_RECORD_COUNT,
    }:
        raise ValueError(
            "source_snapshot does not match the approved corpus snapshot filter contract"
        )
    embedding = _required_string_keyed_mapping(baseline.get("embedding_model"), "embedding_model")
    expected_embedding = dict(APPROVED_EMBEDDING_MODEL)
    expected_embedding["embedded_at_utc"] = "2026-09-02T06:45:00+00:00"
    if embedding != expected_embedding:
        raise ValueError("embedding_model does not match the approved runtime contract")
    source_manifests = baseline.get("source_manifests")
    if not isinstance(source_manifests, list) or len(source_manifests) != 2:
        raise ValueError("source_manifests must contain the approved manifest bindings")
    expected_source_manifests = [APPROVED_FINAL_MANIFEST_PATH, APPROVED_FIXTURE_MANIFEST_PATH]
    seen_source_manifests: list[Path] = []
    for raw_item, expected_path in zip(source_manifests, expected_source_manifests, strict=True):
        manifest = _required_string_keyed_mapping(raw_item, "source_manifest")
        manifest_rel = _require_safe_repo_relative_path(
            _required_string(manifest, "manifest_path"), expected=expected_path
        )
        manifest_path = (REPO_ROOT / manifest_rel).resolve(strict=False)
        expected_manifest_path = (REPO_ROOT / expected_path).resolve(strict=False)
        if manifest_path != expected_manifest_path:
            raise ValueError("source_manifests manifest_path is outside the approved root")
        if manifest_path in seen_source_manifests:
            raise ValueError("source_manifests manifest_path values must be unique")
        seen_source_manifests.append(manifest_path)
        manifest_bytes = read_verified_repo_file(
            repo_root=REPO_ROOT,
            relative_path=manifest_rel,
            expected_root=expected_path.parent,
            field="manifest_path",
        )
        if hashlib.sha256(manifest_bytes).hexdigest() != _required_sha256(manifest, "sha256"):
            raise ValueError("manifest sha256 does not match file bytes")
    scratch_runtime = _required_scratch_runtime(baseline.get("scratch_runtime"))
    bindings = _require_projection_bindings(baseline.get("projection_bindings"))
    a_rows = baseline.get("operator_a_artifacts")
    b_rows = baseline.get("operator_b_artifacts")
    if not isinstance(a_rows, list) or not isinstance(b_rows, list):
        raise ValueError("baseline operator artifact rows are required")
    if len(a_rows) != MATCHED_COUNT or len(b_rows) != MATCHED_COUNT:
        raise ValueError("matched count must be 3 Operator A and 3 Operator B rows")
    execution_receipt = _required_string_keyed_mapping(
        baseline.get("execution_receipt"), "execution_receipt"
    )
    return {
        "operator_a_artifacts": list(a_rows),
        "operator_b_artifacts": list(b_rows),
        "projected_bindings": bindings["by_projected_record_id"],
        "approved_projection_digests": bindings["approved_projection_digests"],
        "scratch_runtime": scratch_runtime,
        "execution_receipt": execution_receipt,
    }


def _required_scratch_runtime(value: object, *, require_exists: bool = False) -> dict[str, Any]:
    scratch = _required_string_keyed_mapping(value, "scratch_runtime")
    db_path = Path(_required_string(scratch, "db_path"))
    index_path = Path(_required_string(scratch, "index_path"))
    _require_confined_scratch_runtime_paths(db_path=db_path, index_path=index_path)
    if require_exists and not db_path.exists():
        raise ValueError("scratch runtime db_path is missing")
    if require_exists and not index_path.exists():
        raise ValueError("scratch runtime index_path is missing")
    if db_path.exists():
        require_non_symlink_leaf(path=db_path, field="scratch runtime db_path")
    if index_path.exists():
        require_non_symlink_leaf(path=index_path, field="scratch runtime index_path")
    if require_exists and not db_path.is_file():
        raise ValueError("scratch runtime db_path must be a regular file")
    if require_exists and not index_path.is_dir():
        raise ValueError("scratch runtime index_path must be a directory")
    if scratch.get("no_production_writes") is not True:
        raise ValueError("scratch runtime must declare no_production_writes")
    if scratch.get("production_write_paths") != []:
        raise ValueError("scratch runtime must not declare production write paths")
    return {"db_path": db_path, "index_path": index_path}


def _require_projection_bindings(value: object) -> dict[str, object]:
    bindings = value
    if not isinstance(bindings, list) or len(bindings) != len(APPROVED_FINANCE_RECORD_IDS):
        raise ValueError("projection_bindings must contain the six approved finance records")
    approved_ids: list[str] = []
    by_projected_record_id: dict[str, dict[str, Any]] = {}
    approved_projection_digests: set[str] = set()
    for item in bindings:
        binding = _required_string_keyed_mapping(item, "projection_binding")
        approved_record_id = _required_string(binding, "approved_record_id")
        approved_ids.append(approved_record_id)
        expected_manifest_rel, expected_root_rel = _approved_binding_roots(approved_record_id)
        manifest_rel = _require_safe_repo_relative_path(
            _required_string(binding, "manifest_path"), expected=expected_manifest_rel
        )
        projection_rel = _require_safe_repo_relative_path(
            _required_string(binding, "projection_path")
        )
        excerpt_rel = _require_safe_repo_relative_path(
            _required_string(binding, "approved_excerpt")
        )
        manifest_path = (REPO_ROOT / manifest_rel).resolve(strict=False)
        expected_manifest_path = (REPO_ROOT / expected_manifest_rel).resolve(strict=False)
        if manifest_path != expected_manifest_path:
            raise ValueError("projection binding manifest_path is outside the approved root")
        manifest_bytes = read_verified_repo_file(
            repo_root=REPO_ROOT,
            relative_path=manifest_rel,
            expected_root=expected_manifest_rel.parent,
            field="manifest_path",
        )
        manifest_row = _load_manifest_fixture_row(
            manifest_path, approved_record_id=approved_record_id, raw_bytes=manifest_bytes
        )
        if _required_string(manifest_row, "id") != approved_record_id:
            raise ValueError("manifest row id does not match approved_record_id")
        row_projection_name = _required_string(manifest_row, "path")
        row_excerpt_name = _required_string(manifest_row, "excerpt_path")
        expected_projection_path = (REPO_ROOT / expected_root_rel / row_projection_name).resolve(
            strict=False
        )
        expected_excerpt_path = (REPO_ROOT / expected_root_rel / row_excerpt_name).resolve(
            strict=False
        )
        projection_path = (REPO_ROOT / projection_rel).resolve(strict=False)
        excerpt_path = (REPO_ROOT / excerpt_rel).resolve(strict=False)
        if projection_path != expected_projection_path:
            raise ValueError("projection binding projection_path is outside the approved root")
        if excerpt_path != expected_excerpt_path:
            raise ValueError("projection binding approved_excerpt is outside the approved root")
        if _required_string(manifest_row, "domain_policy_id") != FINANCE_POLICY_ID:
            raise ValueError("manifest row must stay in finance/1")
        if _required_string(binding, "domain_policy_id") != FINANCE_POLICY_ID:
            raise ValueError("projection binding domain_policy_id must stay in finance/1")
        projection_sha256 = _required_sha256(binding, "projection_sha256")
        excerpt_sha256 = _required_sha256(binding, "approved_excerpt_sha256")
        projection_bytes = read_verified_repo_file(
            repo_root=REPO_ROOT,
            relative_path=projection_rel,
            expected_root=expected_root_rel,
            field="projection_path",
        )
        excerpt_bytes = read_verified_repo_file(
            repo_root=REPO_ROOT,
            relative_path=excerpt_rel,
            expected_root=expected_root_rel,
            field="approved_excerpt",
        )
        if hashlib.sha256(projection_bytes).hexdigest() != projection_sha256:
            raise ValueError("projection_sha256 does not match projection file bytes")
        if hashlib.sha256(excerpt_bytes).hexdigest() != excerpt_sha256:
            raise ValueError("approved_excerpt_sha256 does not match excerpt file bytes")
        if _required_sha256(binding, "manifest_declared_projection_sha256") != projection_sha256:
            raise ValueError(
                "projection binding manifest_declared_projection_sha256 "
                "does not match projection file bytes"
            )
        if _required_sha256(binding, "manifest_declared_excerpt_sha256") != excerpt_sha256:
            raise ValueError(
                "projection binding manifest_declared_excerpt_sha256 "
                "does not match excerpt file bytes"
            )
        if _required_sha256(manifest_row, "content_sha256") != projection_sha256:
            raise ValueError("manifest row content_sha256 does not match projection file bytes")
        if _required_sha256(manifest_row, "excerpt_sha256") != excerpt_sha256:
            raise ValueError("manifest row excerpt_sha256 does not match excerpt file bytes")
        payload = _load_yaml_mapping(projection_path, raw_bytes=projection_bytes)
        projected_record_id = projection_record_id(payload)
        if projected_record_id != _required_string(binding, "projected_record_id"):
            raise ValueError("projected_record_id does not match projection identity")
        reviewed_projection_digest = canonical_reviewed_projection_digest(payload)
        if reviewed_projection_digest != _required_sha256(binding, "reviewed_projection_digest"):
            raise ValueError("reviewed_projection_digest does not match projection contract")
        manifest_reviewed_projection_sha256 = manifest_row.get("reviewed_projection_sha256")
        if (
            manifest_reviewed_projection_sha256 is not None
            and _required_sha256(manifest_row, "reviewed_projection_sha256")
            != reviewed_projection_digest
        ):
            raise ValueError(
                "manifest row reviewed_projection_sha256 does not match projection contract"
            )
        if payload.get("title") != binding.get("title"):
            raise ValueError("projection binding title does not match projection file")
        if payload.get("source_paper_id") != binding.get("source_paper_id"):
            raise ValueError("projection binding source_paper_id does not match projection file")
        if payload.get("domain_policy_id") != FINANCE_POLICY_ID:
            raise ValueError("projection binding must stay in finance/1")
        approved_projection_digests.add(reviewed_projection_digest)
        by_projected_record_id[projected_record_id] = {
            "approved_record_id": approved_record_id,
            "reviewed_projection_digest": reviewed_projection_digest,
            "manifest_path": manifest_path,
            "projection_path": projection_path,
            "excerpt_path": excerpt_path,
        }
    if approved_ids != list(APPROVED_FINANCE_RECORD_IDS):
        raise ValueError("projection_bindings must stay in approved finance record order")
    if len(set(approved_ids)) != len(approved_ids):
        raise ValueError("projection_bindings approved_record_id values must be unique")
    if len(by_projected_record_id) != len(bindings):
        raise ValueError("projection_bindings projected_record_id values must be unique")
    return {
        "by_projected_record_id": by_projected_record_id,
        "approved_projection_digests": frozenset(approved_projection_digests),
    }


def _approved_binding_roots(approved_record_id: str) -> tuple[Path, Path]:
    if approved_record_id == "DATA-NSQD-03":
        return APPROVED_FIXTURE_MANIFEST_PATH, APPROVED_FIXTURE_ROOT
    if approved_record_id in APPROVED_FINANCE_RECORD_IDS[1:]:
        return APPROVED_FINAL_MANIFEST_PATH, APPROVED_FINAL_ROOT
    raise ValueError("approved_record_id is not supported by the finance packet")


def _require_safe_repo_relative_path(value: str, *, expected: Path | None = None) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("projection binding path must stay inside the approved root")
    if expected is not None and candidate != expected:
        raise ValueError("projection binding manifest_path is outside the approved root")
    resolved = (REPO_ROOT / candidate).resolve(strict=False)
    if expected is not None and resolved != (REPO_ROOT / expected).resolve(strict=False):
        raise ValueError("projection binding manifest_path is outside the approved root")
    return candidate


def _load_manifest_fixture_row(
    manifest_path: Path, *, approved_record_id: str, raw_bytes: bytes | None = None
) -> dict[str, Any]:
    if not manifest_path.exists():
        raise ValueError("manifest_path is missing")
    manifest = tomllib.loads((raw_bytes or manifest_path.read_bytes()).decode("utf-8"))
    fixture = manifest.get("fixture")
    if not isinstance(fixture, dict):
        raise ValueError("manifest fixture table is required")
    row = fixture.get(approved_record_id)
    if not isinstance(row, dict):
        raise ValueError("manifest fixture row is required")
    return {str(key): value for key, value in row.items()}


def _require_execution_receipt(receipt: Mapping[str, object]) -> dict[str, Any]:
    payload = _required_string_keyed_mapping(receipt, "execution_receipt")
    candidate_hashes = _required_string_list(
        payload.get("candidate_artifact_hashes"), "candidate_artifact_hashes"
    )
    card_hashes = _required_string_list(payload.get("frontier_card_hashes"), "frontier_card_hashes")
    candidate_payload_sha256 = _required_string_keyed_mapping(
        payload.get("candidate_payload_sha256"), "candidate_payload_sha256"
    )
    card_payload_sha256 = _required_string_keyed_mapping(
        payload.get("frontier_card_payload_sha256"), "frontier_card_payload_sha256"
    )
    for artifact_hash in candidate_hashes:
        _required_sha256(candidate_payload_sha256, artifact_hash)
    for card_hash in card_hashes:
        _required_sha256(card_payload_sha256, card_hash)
    return {
        "sqlite_sha256": _required_sha256(payload, "sqlite_sha256"),
        "lancedb_tree_sha256": _required_sha256(payload, "lancedb_tree_sha256"),
        "candidate_count": _required_nonnegative_int(payload, "candidate_count"),
        "card_count": _required_nonnegative_int(payload, "card_count"),
        "candidate_artifact_hashes": candidate_hashes,
        "frontier_card_hashes": card_hashes,
        "candidate_payload_sha256": candidate_payload_sha256,
        "frontier_card_payload_sha256": card_payload_sha256,
    }


def verify_scratch_execution_receipt(
    receipt: Mapping[str, object],
    *,
    scratch_runtime: Mapping[str, object],
) -> dict[str, Any]:
    payload = _require_execution_receipt(receipt)
    runtime_paths = _required_scratch_runtime(scratch_runtime, require_exists=True)
    db_path = runtime_paths["db_path"]
    index_path = runtime_paths["index_path"]
    assert isinstance(db_path, Path)
    assert isinstance(index_path, Path)
    sqlite_sha256 = _trusted_sha256_file_digest(db_path, max_bytes=MAX_RECEIPT_SQLITE_BYTES)
    if sqlite_sha256 != payload["sqlite_sha256"]:
        raise ValueError("execution receipt sqlite_sha256 does not match scratch sqlite")
    index_digest = lancedb_tree_digest(index_path)
    if index_digest != payload["lancedb_tree_sha256"]:
        raise ValueError("execution receipt lancedb_tree_sha256 does not match scratch index")
    runtime = _load_runtime_store(db_path)
    if payload["candidate_count"] != len(runtime["candidate_payloads"]):
        raise ValueError("execution receipt candidate_count does not match scratch sqlite")
    if payload["card_count"] != len(runtime["frontier_card_payloads"]):
        raise ValueError("execution receipt card_count does not match scratch sqlite")
    if sorted(payload["candidate_artifact_hashes"]) != sorted(runtime["candidate_payloads"]):
        raise ValueError("execution receipt candidate hashes do not match scratch sqlite")
    if sorted(payload["frontier_card_hashes"]) != sorted(runtime["frontier_card_payloads"]):
        raise ValueError("execution receipt frontier card hashes do not match scratch sqlite")
    for artifact_hash, runtime_payload in runtime["candidate_payloads"].items():
        expected = _required_sha256(payload["candidate_payload_sha256"], artifact_hash)
        candidate_payload = _required_string_keyed_mapping(runtime_payload, artifact_hash)
        if expected != _canonical_payload_sha256(candidate_payload):
            raise ValueError(
                "execution receipt candidate payload sha does not match scratch sqlite"
            )
    for card_hash, runtime_payload in runtime["frontier_card_payloads"].items():
        expected = _required_sha256(payload["frontier_card_payload_sha256"], card_hash)
        card_payload = _required_string_keyed_mapping(runtime_payload, card_hash)
        if expected != _canonical_payload_sha256(card_payload):
            raise ValueError(
                "execution receipt frontier card payload sha does not match scratch sqlite"
            )
    return runtime


def _validate_execution_receipt_against_packet(
    receipt: Mapping[str, Any],
    *,
    candidate_rows: Sequence[Mapping[str, object]],
) -> None:
    packet_candidate_hashes = [str(row["artifact_hash"]) for row in candidate_rows]
    packet_card_hashes = [str(row["artifact_hash"]) for row in candidate_rows]
    if receipt["candidate_count"] != len(packet_candidate_hashes):
        raise ValueError("execution receipt candidate_count does not match packet rows")
    if receipt["card_count"] != len(packet_card_hashes):
        raise ValueError("execution receipt card_count does not match packet rows")
    candidate_receipt_hashes = list(receipt["candidate_artifact_hashes"])
    card_receipt_hashes = list(receipt["frontier_card_hashes"])
    candidate_payload_sha256 = _required_string_keyed_mapping(
        receipt["candidate_payload_sha256"], "candidate_payload_sha256"
    )
    frontier_card_payload_sha256 = _required_string_keyed_mapping(
        receipt["frontier_card_payload_sha256"], "frontier_card_payload_sha256"
    )
    if sorted(candidate_receipt_hashes) != sorted(packet_candidate_hashes):
        raise ValueError("execution receipt candidate hashes do not match packet rows")
    if sorted(card_receipt_hashes) != sorted(packet_card_hashes):
        raise ValueError("execution receipt card hashes do not match packet rows")
    for row in candidate_rows:
        artifact_hash = str(row["artifact_hash"])
        candidate_payload = row["artifact"]
        scored_card = row["card"]
        candidate_payload_mapping = _required_string_keyed_mapping(candidate_payload, artifact_hash)
        if _required_sha256(candidate_payload_sha256, artifact_hash) != _canonical_payload_sha256(
            candidate_payload_mapping
        ):
            raise ValueError("execution receipt candidate payload sha does not match packet rows")
        scored_card_mapping = _required_string_keyed_mapping(scored_card, artifact_hash)
        if _required_sha256(
            frontier_card_payload_sha256, artifact_hash
        ) != _canonical_payload_sha256(scored_card_mapping):
            raise ValueError(
                "execution receipt frontier card payload sha does not match packet rows"
            )


def _load_runtime_store(db_path: Path) -> dict[str, dict[str, dict[str, Any]]]:
    connection = sqlite3.connect(db_path.resolve(strict=False).as_uri() + "?mode=ro", uri=True)
    try:
        candidate_rows = connection.execute(
            "SELECT artifact_hash, payload_json FROM nsqd_candidates ORDER BY artifact_hash"
        ).fetchall()
        card_rows = connection.execute(
            "SELECT card_id, payload_json FROM nsqd_frontier_cards ORDER BY card_id"
        ).fetchall()
    finally:
        connection.close()
    candidate_payloads = {
        str(artifact_hash): _json_mapping(raw_json) for artifact_hash, raw_json in candidate_rows
    }
    frontier_card_payloads = {
        str(card_id): _json_mapping(raw_json) for card_id, raw_json in card_rows
    }
    return {
        "candidate_payloads": candidate_payloads,
        "frontier_card_payloads": frontier_card_payloads,
    }


def _require_ideas(ideas: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not isinstance(ideas, Sequence) or isinstance(ideas, (str, bytes)):
        raise ValueError("ideas is required")
    rows: list[dict[str, object]] = []
    for idea in ideas:
        if not isinstance(idea, Mapping):
            raise ValueError("ideas is required")
        if idea.get("result_class") != "proposed_idea":
            raise ValueError("ideas must be proposed_idea rows")
        if idea.get("runtime_authorized") is True:
            raise ValueError("runtime_authorized must be false")
        rows.append(
            {
                "candidate_id": _required_string(idea, "candidate_id"),
                "component_record_ids": _required_string_list(
                    idea.get("component_record_ids"), "component_record_ids"
                ),
                "supporting_fact_ids": _required_string_list(
                    idea.get("supporting_fact_ids"), "supporting_fact_ids"
                ),
                "cooccurrence_snapshot_id": _required_string(idea, "cooccurrence_snapshot_id"),
            }
        )
    if len(rows) != MATCHED_COUNT:
        raise ValueError("matched count must include exactly 3 idea rows")
    ids = [str(row["candidate_id"]) for row in rows]
    if len(set(ids)) != MATCHED_COUNT:
        raise ValueError("idea candidate_id values must be unique")
    return rows


def _require_extracted_facts(
    extracted_facts: Sequence[Mapping[str, object]],
) -> list[dict[str, str]]:
    if not isinstance(extracted_facts, Sequence) or isinstance(extracted_facts, (str, bytes)):
        raise ValueError("extracted_facts is required")
    rows: list[dict[str, str]] = []
    fact_ids: set[str] = set()
    for row in extracted_facts:
        if not isinstance(row, Mapping):
            raise ValueError("extracted_facts is required")
        if row.get("result_class") != "extracted_fact":
            raise ValueError("extracted_facts must be extracted_fact rows")
        fact_id = _required_string(row, "fact_id")
        if fact_id in fact_ids:
            raise ValueError("extracted_facts fact_id values must be unique")
        fact_ids.add(fact_id)
        rows.append(
            {
                "fact_id": fact_id,
                "source_record_id": _required_string(row, "source_record_id"),
                "claim": _required_string(row, "claim"),
            }
        )
    return rows


def _require_a_artifact(
    row: Mapping[str, object],
    *,
    index: int,
    approved_projection_digests: frozenset[str],
    projected_bindings: Mapping[str, Mapping[str, object]],
    facts_by_id: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    payload = _required_string_keyed_mapping(row, f"operator_a_artifact[{index}]")
    candidate_id = _required_string(payload, "candidate_id")
    source_fact_id = _required_string(payload, "source_fact_id")
    source_record_id = _required_string(payload, "source_record_id")
    inverted_axiom = _required_string(payload, "inverted_axiom")
    fact = facts_by_id.get(source_fact_id)
    if fact is None:
        raise ValueError("Operator A source_fact_id must exist in extracted_facts")
    if fact["source_record_id"] != source_record_id:
        raise ValueError("Operator A source_fact_id/source_record_id binding is invalid")
    if fact["claim"] == inverted_axiom:
        raise ValueError("Operator A inverted_axiom must differ from the source claim")
    artifact_hash, artifact, grounding, card = _require_artifact_triplet(
        payload,
        operator="A",
        approved_projection_digests=approved_projection_digests,
        projected_bindings=projected_bindings,
    )
    return {
        "candidate_id": candidate_id,
        "source_fact_id": source_fact_id,
        "artifact_hash": artifact_hash,
        "operator": "A",
        "artifact": artifact,
        "grounding": grounding,
        "card": card,
    }


def _require_b_artifact(
    row: Mapping[str, object],
    *,
    index: int,
    approved_projection_digests: frozenset[str],
    projected_bindings: Mapping[str, Mapping[str, object]],
) -> dict[str, Any]:
    payload = _required_string_keyed_mapping(row, f"operator_b_artifact[{index}]")
    candidate_id = _required_string(payload, "candidate_id")
    artifact_hash, artifact, grounding, card = _require_artifact_triplet(
        payload,
        operator="B",
        approved_projection_digests=approved_projection_digests,
        projected_bindings=projected_bindings,
    )
    assumed_status = _required_string(payload, "assumed_status")
    row_cell_id = _required_string(payload, "cell_id")
    if assumed_status != "Missing":
        raise ValueError("Operator B assumed_status must be Missing")
    proof = _required_string_keyed_mapping(payload.get("diverge_proof"), "diverge_proof")
    allowlist = frozenset(
        _required_string_list(proof.get("enabled_operators"), "enabled_operators")
    )
    require_operator("B", enabled_operators=allowlist)
    target = _required_string(proof, "selected_target_cell")
    statuses_raw = _required_string_keyed_mapping(proof.get("cell_statuses"), "cell_statuses")
    statuses: dict[str, Any] = {}
    for cell_id, status in statuses_raw.items():
        statuses[cell_id] = require_cell_status(status)
    if set(statuses) != FINANCE_POLICY.universe():
        raise ValueError("Operator B proof must include the full finance status universe")
    if select_target_cell(statuses) != target:
        raise ValueError("Operator B target must match ALG-SEL")
    if statuses.get(target) != "Missing":
        raise ValueError("Operator B target must stay Missing in the matched-count report")
    if row_cell_id != target:
        raise ValueError("Operator B row cell_id must match the selected target")
    candidate = _required_string_keyed_mapping(artifact.get("candidate"), "candidate")
    descriptor = _required_string_keyed_mapping(
        candidate.get("research_descriptor"), "research_descriptor"
    )
    if FINANCE_POLICY.cell_id(descriptor) != target:
        raise ValueError("research_descriptor must resolve to the Operator B target")
    axioms_input = proof.get("axioms")
    if not isinstance(axioms_input, list):
        raise ValueError("Operator B proof axioms are required")
    require_no_axiom_inversion(candidate=candidate, axioms=axioms_input)
    axioms = normalize_axiom_rows(deepcopy(axioms_input))
    if not any(item.get("cell_id") == target for item in axioms):
        raise ValueError("Operator B requires a target-bound axiom")
    for item in axioms:
        if item.get("cell_id") not in {None, target}:
            raise ValueError("axiom cell_id must match the ALG-SEL target")
    if artifact.get("target_cell_id") != target:
        raise ValueError("stored Operator B artifact target does not match proof target")
    if card.get("cell_id") != target:
        raise ValueError("Operator B scored card cell_id does not match proof target")
    return {
        "candidate_id": candidate_id,
        "artifact_hash": artifact_hash,
        "operator": "B",
        "artifact": artifact,
        "grounding": grounding,
        "card": card,
    }


def _require_artifact_triplet(
    payload: Mapping[str, object],
    *,
    operator: str,
    approved_projection_digests: frozenset[str],
    projected_bindings: Mapping[str, Mapping[str, object]],
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    artifact_hash = _required_sha256(payload, "candidate_artifact_hash")
    artifact = _required_string_keyed_mapping(
        payload.get("candidate_artifact"), "candidate_artifact"
    )
    if artifact.get("operator") != operator:
        raise ValueError(f"operator {operator} artifact must set operator {operator}")
    candidate = _required_string_keyed_mapping(artifact.get("candidate"), "candidate")
    if _candidate_artifact_hash(candidate) != artifact_hash:
        raise ValueError("candidate_artifact_hash does not match candidate body")
    generator_run_id = _required_string(artifact, "generator_run_id")
    grounding = _required_string_keyed_mapping(payload.get("grounding"), "grounding")
    if grounding != artifact.get("grounding"):
        raise ValueError("grounding must match the persisted candidate artifact grounding")
    _require_grounding(
        grounding,
        candidate=candidate,
        artifact_hash=artifact_hash,
        approved_projection_digests=approved_projection_digests,
        projected_bindings=projected_bindings,
    )
    novelty = _required_string_keyed_mapping(artifact.get("novelty"), "novelty")
    _require_novelty(novelty, grounding=grounding)
    card = _required_string_keyed_mapping(payload.get("scored_card"), "scored_card")
    _require_scored_card(
        card,
        artifact_hash=artifact_hash,
        operator=operator,
        generator_run_id=generator_run_id,
        candidate=candidate,
        grounding=grounding,
    )
    return artifact_hash, artifact, grounding, card


def _require_grounding(
    grounding: Mapping[str, object],
    *,
    candidate: Mapping[str, object],
    artifact_hash: str,
    approved_projection_digests: frozenset[str],
    projected_bindings: Mapping[str, Mapping[str, object]],
) -> None:
    if grounding.get("candidate_artifact_hash") != artifact_hash:
        raise ValueError("grounding candidate_artifact_hash does not match row")
    if grounding.get("snapshot_id") != APPROVED_CORPUS_SNAPSHOT_ID:
        raise ValueError("grounding snapshot_id must match the approved corpus snapshot")
    if grounding.get("snapshot_digest") != APPROVED_CORPUS_SNAPSHOT_ID:
        raise ValueError("grounding snapshot_digest must match the approved corpus snapshot")
    if grounding.get("corpus_version") != APPROVED_CORPUS_VERSION:
        raise ValueError("grounding corpus_version must match the approved corpus snapshot")
    if grounding.get("snapshot_state") != "production_valid":
        raise ValueError("grounding snapshot_state must be production_valid")
    expected_pair_id = sha256_hex(
        canonical_json(
            {
                "candidate_artifact_hash": artifact_hash,
                "domain_policy_id": FINANCE_POLICY_ID,
                "snapshot_id": APPROVED_CORPUS_SNAPSHOT_ID,
            }
        )
    )
    if grounding.get("pair_id") != expected_pair_id:
        raise ValueError("grounding pair_id does not match runtime grounding identity")
    expected_candidate_text = normalize_paraphrase(_required_string(candidate, "paraphrase"))
    exported_candidate = _required_string_keyed_mapping(grounding.get("candidate"), "candidate")
    if exported_candidate.get("artifact_hash") != artifact_hash:
        raise ValueError("grounding candidate artifact_hash does not match row")
    if exported_candidate.get("paraphrase") != expected_candidate_text:
        raise ValueError("grounding candidate paraphrase does not match candidate artifact")
    if exported_candidate.get("text_digest") != sha256_hex(expected_candidate_text.encode("utf-8")):
        raise ValueError("grounding candidate text_digest does not match candidate paraphrase")
    qualified = qualify_tau_measurement_pair(
        grounding,
        approved_projection_digests=approved_projection_digests,
        trusted_measurement_digests=frozenset(
            {_required_sha256(grounding, "measurement_artifact_digest")}
        ),
    )
    if tau_measurement_artifact_digest(grounding) != _required_sha256(
        grounding, "measurement_artifact_digest"
    ):
        raise ValueError("measurement artifact digest does not match row")
    measurement_stamp = _required_string_keyed_mapping(
        grounding.get("measurement_stamp"), "measurement_stamp"
    )
    if measurement_stamp != {
        "embedding_model_id": APPROVED_EMBEDDING_MODEL["model_id"],
        "embedding_model_version": APPROVED_EMBEDDING_MODEL["model_version"],
        "embedding_dimension": APPROVED_EMBEDDING_MODEL["embedding_dimension"],
        "normalization_policy": APPROVED_EMBEDDING_MODEL["normalization_policy"],
        "distance_metric": APPROVED_EMBEDDING_MODEL["distance_metric"],
        "algorithm_contract_version": "1.1",
    }:
        raise ValueError(
            "grounding measurement_stamp does not match the approved embedding contract"
        )
    if grounding.get("measurement") != qualified["measurement"]:
        raise ValueError("grounding measurement distances must match neighbors")
    closest = _required_string_keyed_mapping(
        grounding.get("closest_prior_art"), "closest_prior_art"
    )
    first_neighbor = qualified["neighbors"][0]
    if (
        closest.get("record_id") != first_neighbor["record_id"]
        or closest.get("distance") != first_neighbor["distance"]
    ):
        raise ValueError("closest_prior_art must match the closest grounded neighbor")
    for neighbor in qualified["neighbors"]:
        binding = projected_bindings.get(str(neighbor["record_id"]))
        if binding is None:
            raise ValueError("grounding neighbor must bind to an approved projection record")
        if binding["reviewed_projection_digest"] != neighbor["reviewed_projection_digest"]:
            raise ValueError("grounding neighbor reviewed projection digest does not match binding")


def _require_novelty(novelty: Mapping[str, object], *, grounding: Mapping[str, object]) -> None:
    evidence, snapshot_state, grounding_class = _grounding_novelty_inputs(grounding)
    expected_term = apply_novelty_threshold(
        novelty_term(
            evidence=evidence,
            snapshot_state=snapshot_state,
            grounding_class=grounding_class,
        ),
        evidence=evidence,
        tau=NOVELTY_THRESHOLD_TAU,
    )
    if novelty.get("evidence") != grounding.get("evidence"):
        raise ValueError("novelty evidence must match grounding evidence")
    if novelty.get("term") != expected_term:
        raise ValueError("novelty term does not match grounding evidence")
    if novelty.get("tau") != NOVELTY_THRESHOLD_TAU:
        raise ValueError("novelty tau does not match the active threshold")
    if novelty.get("tau_semantics") != NOVELTY_TAU_SEMANTICS:
        raise ValueError("novelty tau_semantics does not match the active contract")
    if novelty.get("snapshot_id") != APPROVED_CORPUS_SNAPSHOT_ID:
        raise ValueError("novelty snapshot_id must match the approved corpus snapshot")
    if novelty.get("snapshot_state") != "production_valid":
        raise ValueError("novelty snapshot_state must match grounding state")
    if novelty.get("corpus_version") != APPROVED_CORPUS_VERSION:
        raise ValueError("novelty corpus_version must match the approved corpus snapshot")
    if novelty.get("measurement_stamp") != grounding.get("measurement_stamp"):
        raise ValueError("novelty measurement_stamp must match grounding measurement_stamp")


def _require_scored_card(
    card: Mapping[str, object],
    *,
    artifact_hash: str,
    operator: str,
    generator_run_id: str,
    candidate: Mapping[str, object],
    grounding: Mapping[str, object],
) -> None:
    if card.get("card_id") != artifact_hash or card.get("candidate_artifact_hash") != artifact_hash:
        raise ValueError("scored card must bind the candidate_artifact_hash")
    if card.get("generating_operator") != operator:
        raise ValueError("scored card generating_operator is invalid")
    if card.get("domain_policy_id") != FINANCE_POLICY_ID:
        raise ValueError("scored card must stay in finance/1")
    descriptor = _required_string_keyed_mapping(
        candidate.get("research_descriptor"), "research_descriptor"
    )
    expected_cell_id = FINANCE_POLICY.cell_id(descriptor)
    if card.get("cell_id") != expected_cell_id:
        raise ValueError("scored card cell_id does not match candidate research_descriptor")
    expected_archive_key = archive_cell_key(
        domain_policy_id=FINANCE_POLICY_ID, cell_id=expected_cell_id
    )
    if card.get("archive_cell_key") != expected_archive_key:
        raise ValueError("scored card archive_cell_key is invalid")
    if card.get("snapshot_id") != APPROVED_CORPUS_SNAPSHOT_ID:
        raise ValueError("scored card snapshot_id must match the approved corpus snapshot")
    if card.get("corpus_version") != APPROVED_CORPUS_VERSION:
        raise ValueError("scored card corpus_version must match the approved corpus snapshot")
    evaluator_run_id = _required_string(card, "evaluator_run_id")
    if evaluator_run_id == generator_run_id:
        raise ValueError("evaluator_run_id must differ from generator_run_id")
    if card.get("generator_run_id") != generator_run_id:
        raise ValueError("scored card generator_run_id must match the persisted artifact")
    evidence, snapshot_state, grounding_class = _grounding_novelty_inputs(grounding)
    expected_nov = apply_novelty_threshold(
        novelty_term(
            evidence=evidence,
            snapshot_state=snapshot_state,
            grounding_class=grounding_class,
        ),
        evidence=evidence,
        tau=NOVELTY_THRESHOLD_TAU,
    )
    expected_mech = score_mech(dict(candidate), domain_pack=FINANCE_POLICY_ID)
    expected_fals = score_fals(dict(candidate))
    expected_dpred = score_dpred(dict(candidate))
    expected_dval = score_dval(dict(candidate))
    expected_viability = viability(
        nov=expected_nov,
        mech=expected_mech,
        fals=expected_fals,
        dpred=expected_dpred,
        dval=expected_dval,
    )
    expected_decision = card_decision(expected_viability)
    checks: dict[str, object] = {
        "title": candidate.get("title") or "",
        "nov": expected_nov,
        "mech": expected_mech,
        "fals": expected_fals,
        "dpred": expected_dpred,
        "dval": expected_dval,
        "viability": expected_viability,
        "card_decision": expected_decision,
    }
    for field, expected in checks.items():
        if card.get(field) != expected:
            raise ValueError(f"scored card {field} does not match recomputed value")
    missing = missing_card_fields(dict(card))
    if card.get("missing_fields") != missing or missing != []:
        raise ValueError("scored card missing_fields must be empty")


def _require_e_candidate(
    row: Mapping[str, object], *, index: int, ideas_by_id: Mapping[str, Mapping[str, object]]
) -> dict[str, Any]:
    payload = _required_string_keyed_mapping(row, f"operator_e_candidate[{index}]")
    artifact_id = _required_string(payload, "artifact_id")
    source_idea_id = _required_string(payload, "source_idea_id")
    if source_idea_id not in ideas_by_id:
        raise ValueError("source_idea_id must match one of the approved JEPA ideas")
    if payload.get("authorization_state") != "report_only":
        raise ValueError("Operator E artifacts must stay report_only")
    if payload.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if payload.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    if payload.get("human_usefulness_score") is not None:
        raise ValueError("human_usefulness_score must remain null")
    component_ids = _required_string_list(payload.get("component_ids"), "component_ids")
    supporting_fact_ids = _required_string_list(
        payload.get("supporting_fact_ids"), "supporting_fact_ids"
    )
    expected = ideas_by_id[source_idea_id]
    if component_ids != expected["component_record_ids"]:
        raise ValueError("Operator E component_ids must match the source JEPA idea")
    if supporting_fact_ids != expected["supporting_fact_ids"]:
        raise ValueError("Operator E supporting_fact_ids must match the source JEPA idea")
    if payload.get("co_occurrence_snapshot_id") != expected["cooccurrence_snapshot_id"]:
        raise ValueError("Operator E co_occurrence_snapshot_id must match the source JEPA idea")
    if payload.get("source_snapshot_id") != APPROVED_CORPUS_SNAPSHOT_ID:
        raise ValueError("Operator E source_snapshot_id must match the approved corpus snapshot")
    if payload.get("corpus_version") != APPROVED_CORPUS_VERSION:
        raise ValueError("Operator E corpus_version must match the approved corpus snapshot")
    atypicality = _required_string_keyed_mapping(payload.get("atypicality"), "atypicality")
    if atypicality.get("interpretation") != OPERATOR_E_ATYPICALITY_INTERPRETATION:
        raise ValueError("Operator E atypicality_interpretation must stay corpus rarity only")
    nearest_prior = payload.get("nearest_prior_combinations")
    if not isinstance(nearest_prior, list):
        raise ValueError("Operator E nearest_prior_combinations is required")
    declared_hash = _required_sha256(payload, "artifact_hash")
    if report_only_operator_e_candidate_hash(payload) != declared_hash:
        raise ValueError("Operator E artifact_hash does not match canonical candidate content")
    return {
        "artifact_id": artifact_id,
        "artifact_hash": declared_hash,
        "operator": "E",
        "artifact": payload,
    }


def _require_blinded_review_packet(
    packet: Mapping[str, object], *, expected_item_count: int
) -> dict[str, Any]:
    payload = _required_string_keyed_mapping(packet, "blinded_review_packet")
    if payload.get("packet_kind") != "human_usefulness_review_packet":
        raise ValueError("blinded review packet_kind is invalid")
    if payload.get("authorization_state") != "report_only":
        raise ValueError("blinded review packet must be report_only")
    if payload.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if payload.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    status = str(payload.get("human_usefulness_review_status") or "pending").strip()
    reviewer_identity = str(payload.get("reviewer_identity") or "human_required").strip()
    if status not in {"pending", "completed"}:
        raise ValueError("human_usefulness_review_status must stay pending or become completed")
    reviewed_at_utc = _require_reviewed_at_utc(payload, status=status)
    if status == "pending":
        if reviewer_identity != "human_required":
            raise ValueError("blinded review packet must require a human reviewer")
    elif status == "completed":
        if reviewer_identity in PLACEHOLDER_REVIEWER_IDENTITIES:
            raise ValueError(
                "completed review reviewer_identity must be a non-placeholder human label"
            )
    else:
        raise ValueError("human_usefulness_review_status must stay pending or become completed")
    if payload.get("blinding_scope") != "operator_label_blinded":
        raise ValueError("blinded review packet must declare operator-label blinding")
    if payload.get("blinding_limitation") != (
        "proposal content is retained for usefulness scoring and may still permit family inference"
    ):
        raise ValueError("blinded review packet must declare its blinding limitation")
    allowed_abstentions = frozenset(
        _required_string_list(payload.get("abstention_reasons"), "abstention_reasons")
    )
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != expected_item_count:
        raise ValueError("blinded review packet must contain exactly 9 items")
    blind_ids: list[str] = []
    normalized_items: list[dict[str, Any]] = []
    for expected_index, raw_item in enumerate(items, start=1):
        item = _required_string_keyed_mapping(raw_item, "review_item")
        blind_id = _required_string(item, "blind_id")
        if item.get("item_index") != expected_index:
            raise ValueError("blinded review item_index must be sequential")
        review_form = _required_string_keyed_mapping(item.get("review_form"), "review_form")
        normalized_items.append(
            {
                "blind_id": blind_id,
                "item_index": expected_index,
                "review": _require_review_form(
                    review_form,
                    status=status,
                    allowed_abstentions=allowed_abstentions,
                ),
            }
        )
        blinded_text = canonical_json(item).decode("utf-8").lower()
        if any(token in blinded_text for token in BLIND_FORBIDDEN_TOKENS):
            raise ValueError("review packet must stay blinded")
        blind_ids.append(blind_id)
    if len(set(blind_ids)) != len(blind_ids):
        raise ValueError("blinded review blind_id values must be unique")
    _validate_duplicate_groups(normalized_items)
    if blinded_review_packet_digest(payload) != _required_sha256(payload, "packet_digest"):
        raise ValueError("blinded review packet_digest does not match canonical packet content")
    return {
        "items": normalized_items,
        "raw_items": list(items),
        "packet_digest": _required_sha256(payload, "packet_digest"),
        "status": status,
        "reviewer_identity": reviewer_identity,
        "reviewed_at_utc": reviewed_at_utc,
        "allowed_abstentions": allowed_abstentions,
    }


def _require_audit_manifest(
    manifest: Mapping[str, object],
    *,
    review_packet: Mapping[str, object],
    known_hashes: Mapping[str, str],
) -> dict[str, Any]:
    payload = _required_string_keyed_mapping(manifest, "audit_manifest")
    if payload.get("packet_kind") != "human_usefulness_review_audit_manifest":
        raise ValueError("audit manifest packet_kind is invalid")
    if payload.get("authorization_state") != "report_only":
        raise ValueError("audit manifest must be report_only")
    if payload.get("runtime_authorized") is not False:
        raise ValueError("runtime_authorized must be false")
    if payload.get("evidence_sufficient") is not False:
        raise ValueError("evidence_sufficient must be false")
    status = str(payload.get("human_usefulness_review_status") or "pending").strip()
    reviewer_identity = str(payload.get("reviewer_identity") or "human_required").strip()
    if status not in {"pending", "completed"}:
        raise ValueError("human_usefulness_review_status must stay pending or become completed")
    reviewed_at_utc = _require_reviewed_at_utc(payload, status=status)
    duplicate_rationale = payload.get("duplicate_rationale")
    if status == "pending":
        if reviewer_identity != "human_required":
            raise ValueError("audit manifest reviewer_identity must require a human reviewer")
        if payload.get("all_scores_null") is not True:
            raise ValueError("audit manifest must keep all_scores_null true")
    elif status == "completed":
        if reviewer_identity in PLACEHOLDER_REVIEWER_IDENTITIES:
            raise ValueError(
                "completed audit reviewer_identity must be a non-placeholder human label"
            )
        if payload.get("all_scores_null") is not False:
            raise ValueError("completed audit must set all_scores_null false")
        if not isinstance(duplicate_rationale, str) or not duplicate_rationale.strip():
            raise ValueError("completed audit duplicate_rationale is required")
    else:
        raise ValueError("human_usefulness_review_status must stay pending or become completed")
    if payload.get("review_packet_digest") != review_packet["packet_digest"]:
        raise ValueError("audit manifest review_packet_digest must match blinded review packet")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != len(known_hashes):
        raise ValueError("audit manifest must cover each artifact hash exactly once")
    allowed_abstentions = _required_frozenset_of_strings(
        review_packet.get("allowed_abstentions"),
        field="blinded review packet allowed_abstentions",
    )
    previous_sort_key = ""
    blind_ids: list[str] = []
    artifact_hashes: list[str] = []
    normalized_items: list[dict[str, Any]] = []
    for expected_index, raw_item in enumerate(items, start=1):
        item = _required_string_keyed_mapping(raw_item, "audit_item")
        blind_id = _required_string(item, "blind_id")
        if item.get("item_index") != expected_index:
            raise ValueError("audit manifest item_index must be sequential")
        artifact_hash = _required_sha256(item, "artifact_hash")
        if artifact_hash not in known_hashes:
            raise ValueError("audit manifest item does not match known artifact hash")
        _required_sha256(item, "review_content_sha256")
        operator = _required_string(item, "operator")
        if operator != known_hashes[artifact_hash]:
            raise ValueError("audit manifest operator does not match known artifact hash")
        sort_key = _required_sha256(item, "blind_sort_key")
        expected_sort_key = blinded_review_sort_key(artifact_hash=artifact_hash)
        if sort_key != expected_sort_key:
            raise ValueError("audit manifest blind_sort_key does not match deterministic ordering")
        if previous_sort_key and sort_key < previous_sort_key:
            raise ValueError("audit manifest items must be sorted by blind_sort_key")
        previous_sort_key = sort_key
        blind_ids.append(blind_id)
        artifact_hashes.append(artifact_hash)
        normalized_items.append(
            {
                "blind_id": blind_id,
                "item_index": expected_index,
                "operator": operator,
                "artifact_hash": artifact_hash,
                "review": _require_review_fields(
                    item,
                    status=status,
                    allowed_abstentions=allowed_abstentions,
                ),
            }
        )
    if len(set(blind_ids)) != len(blind_ids):
        raise ValueError("audit manifest blind_id values must be unique")
    if sorted(artifact_hashes) != sorted(known_hashes):
        raise ValueError("audit manifest must cover each artifact hash exactly once")
    _validate_duplicate_groups(normalized_items)
    if audit_manifest_digest(payload) != _required_sha256(payload, "manifest_digest"):
        raise ValueError("audit manifest manifest_digest does not match canonical manifest content")
    return {
        "items": normalized_items,
        "raw_items": list(items),
        "status": status,
        "reviewer_identity": reviewer_identity,
        "reviewed_at_utc": reviewed_at_utc,
        "duplicate_rationale": duplicate_rationale,
    }


def _required_frozenset_of_strings(value: object, *, field: str) -> frozenset[str]:
    if not isinstance(value, frozenset):
        raise ValueError(f"{field} is invalid")
    items: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} is invalid")
        items.add(item)
    return frozenset(items)


def _require_reviewed_at_utc(payload: Mapping[str, object], *, status: str) -> str | None:
    value = payload.get("reviewed_at_utc")
    if status == "pending":
        if value not in {None, ""}:
            raise ValueError("pending human review must not set reviewed_at_utc")
        return None
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("completed human review reviewed_at_utc must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("completed human review reviewed_at_utc must be a UTC timestamp") from exc
    if parsed.tzinfo != UTC or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("completed human review reviewed_at_utc must be a UTC timestamp")
    return value


def _require_review_form(
    review_form: Mapping[str, object],
    *,
    status: str,
    allowed_abstentions: frozenset[str],
) -> dict[str, Any]:
    return _require_review_fields(
        review_form, status=status, allowed_abstentions=allowed_abstentions
    )


def _require_review_fields(
    value: Mapping[str, object],
    *,
    status: str,
    allowed_abstentions: frozenset[str],
) -> dict[str, Any]:
    score = value.get("human_usefulness_score")
    abstention = value.get("abstention_reason")
    duplicate_group_id = value.get("duplicate_group_id")
    duplicate_decision = value.get("duplicate_decision")
    reviewer_notes = value.get("reviewer_notes")
    possible_duplicates = value.get("possible_duplicate_of_blind_ids")
    if not isinstance(possible_duplicates, list):
        raise ValueError("possible_duplicate_of_blind_ids must stay empty")
    duplicate_ids: list[str] = []
    for item in possible_duplicates:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("possible_duplicate_of_blind_ids must contain canonical blind ids")
        duplicate_ids.append(item.strip())
    if duplicate_ids != sorted(duplicate_ids) or len(set(duplicate_ids)) != len(duplicate_ids):
        raise ValueError("possible_duplicate_of_blind_ids must use canonical blind-id order")
    if reviewer_notes is not None:
        raise ValueError("reviewer_notes must remain null")
    if status == "pending":
        if score is not None:
            raise ValueError("review_form human_usefulness_score must remain null")
        if abstention is not None:
            raise ValueError("review_form abstention_reason must remain null")
        if duplicate_decision is not None:
            raise ValueError("review_form duplicate_decision must remain null")
        if duplicate_group_id is not None:
            raise ValueError("review_form duplicate_group_id must remain null")
        if duplicate_ids != []:
            raise ValueError("review_form possible_duplicate_of_blind_ids must stay empty")
        return {
            "human_usefulness_score": None,
            "abstention_reason": None,
            "possible_duplicate_of_blind_ids": [],
            "duplicate_group_id": None,
            "duplicate_decision": None,
            "reviewer_notes": None,
        }
    if abstention is None:
        if isinstance(score, bool) or not isinstance(score, int) or score not in {0, 1, 2, 3}:
            raise ValueError("completed human_usefulness_score must be an integer in 0..3")
    else:
        if not isinstance(abstention, str) or abstention not in allowed_abstentions:
            raise ValueError("completed abstention_reason is invalid")
        if score is not None:
            raise ValueError("completed review score and abstention are exclusive")
    if (
        not isinstance(duplicate_decision, str)
        or duplicate_decision not in ALLOWED_DUPLICATE_DECISIONS
    ):
        raise ValueError("completed duplicate_decision is invalid")
    if duplicate_decision == "distinct":
        if duplicate_group_id is not None or duplicate_ids != []:
            raise ValueError(
                "distinct items must not declare duplicate_group_id "
                "or possible_duplicate_of_blind_ids"
            )
    else:
        if not isinstance(duplicate_group_id, str) or not duplicate_group_id.strip():
            raise ValueError("collapse_same_idea_variants requires duplicate_group_id")
        if len(duplicate_ids) < 1:
            raise ValueError("collapse_same_idea_variants requires possible_duplicate_of_blind_ids")
    return {
        "human_usefulness_score": score,
        "abstention_reason": abstention,
        "possible_duplicate_of_blind_ids": duplicate_ids,
        "duplicate_group_id": duplicate_group_id,
        "duplicate_decision": duplicate_decision,
        "reviewer_notes": None,
    }


def _validate_duplicate_groups(items: Sequence[Mapping[str, Any]]) -> None:
    by_id = {str(item["blind_id"]): item for item in items}
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        review = _required_string_keyed_mapping(item["review"], "review")
        decision = review.get("duplicate_decision")
        if decision in {None, "distinct"}:
            continue
        group_id = review.get("duplicate_group_id")
        assert isinstance(group_id, str)
        groups.setdefault(group_id, []).append(item)
    for group_id, members in groups.items():
        if len(members) < 2:
            raise ValueError("collapse_same_idea_variants cannot declare a singleton group")
        member_ids = sorted(str(item["blind_id"]) for item in members)
        for item in members:
            review = _required_string_keyed_mapping(item["review"], "review")
            blind_id = str(item["blind_id"])
            expected_peers = [candidate for candidate in member_ids if candidate != blind_id]
            if review.get("possible_duplicate_of_blind_ids") != expected_peers:
                raise ValueError(
                    "duplicate possible_duplicate_of_blind_ids must be symmetric and canonical"
                )
            for peer in expected_peers:
                peer_review = _required_string_keyed_mapping(by_id[peer]["review"], "review")
                if blind_id not in cast(
                    list[str], peer_review.get("possible_duplicate_of_blind_ids")
                ):
                    raise ValueError(
                        "duplicate possible_duplicate_of_blind_ids must be asymmetric-free"
                    )
                if peer_review.get("duplicate_group_id") != group_id:
                    raise ValueError("duplicate group membership must be asymmetric-free")


def _validate_human_review_consistency(
    *, review_packet: Mapping[str, Any], audit_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    if review_packet["status"] != audit_manifest["status"]:
        raise ValueError("packet/audit human review status must match")
    if review_packet["reviewer_identity"] != audit_manifest["reviewer_identity"]:
        raise ValueError("packet/audit reviewer_identity must match")
    if review_packet["reviewed_at_utc"] != audit_manifest["reviewed_at_utc"]:
        raise ValueError("packet/audit reviewed_at_utc must match")
    packet_items = cast(list[dict[str, Any]], review_packet["items"])
    audit_items = cast(list[dict[str, Any]], audit_manifest["items"])
    for packet_item, audit_item in zip(packet_items, audit_items, strict=True):
        if packet_item["blind_id"] != audit_item["blind_id"]:
            raise ValueError("packet/audit blind_id order must match")
        if packet_item["review"] != audit_item["review"]:
            raise ValueError("packet/audit human review fields must match")
    status = cast(str, review_packet["status"])
    if status == "pending":
        return {
            "usefulness_review_status": "pending_human_review",
            "matched_candidate_metrics": None,
            "summary": {
                "packet_status": "pending",
                "reviewer_identity": "not_requested",
                "all_scores_null": True,
                "blinded_item_count": len(packet_items),
            },
        }
    metrics = _summarize_human_review(
        packet_items,
        audit_items,
        reviewer_identity=cast(str, review_packet["reviewer_identity"]),
        reviewed_at_utc=cast(str, review_packet["reviewed_at_utc"]),
        duplicate_rationale=cast(str, audit_manifest["duplicate_rationale"]),
    )
    return {
        "usefulness_review_status": "completed_human_review",
        "matched_candidate_metrics": {
            "raw_mean": metrics["raw"]["mean_score"],
            "duplicate_collapsed_mean": metrics["duplicate_collapsed"]["mean_score"],
        },
        "summary": metrics,
    }


def _summarize_human_review(
    packet_items: Sequence[Mapping[str, Any]],
    audit_items: Sequence[Mapping[str, Any]],
    *,
    reviewer_identity: str,
    reviewed_at_utc: str,
    duplicate_rationale: str,
) -> dict[str, Any]:
    def _mean_or_none(total: float, count: int) -> float | None:
        if count == 0:
            return None
        return round(total / count, 6)

    raw_scored_values = [
        float(cast(int, item["review"]["human_usefulness_score"]))
        for item in packet_items
        if item["review"]["human_usefulness_score"] is not None
    ]
    raw_total = sum(raw_scored_values)
    raw_scored_count = len(raw_scored_values)
    raw_abstention_count = sum(
        1 for item in packet_items if item["review"]["abstention_reason"] is not None
    )

    by_group: dict[str, list[dict[str, Any]]] = {}
    collapsed_entries: list[dict[str, Any]] = []
    for packet_item, audit_item in zip(packet_items, audit_items, strict=True):
        review = cast(dict[str, Any], packet_item["review"])
        entry = {
            "blind_id": str(packet_item["blind_id"]),
            "score": review["human_usefulness_score"],
            "abstention_reason": review["abstention_reason"],
            "operator": str(audit_item["operator"]),
        }
        if review["duplicate_decision"] == "collapse_same_idea_variants":
            by_group.setdefault(cast(str, review["duplicate_group_id"]), []).append(entry)
        else:
            collapsed_entries.append(entry)

    for members in by_group.values():
        scored = [float(cast(int, item["score"])) for item in members if item["score"] is not None]
        representative = min(members, key=lambda item: item["blind_id"])
        collapsed_entries.append(
            {
                "blind_id": representative["blind_id"],
                "operator": representative["operator"],
                "score": None if not scored else round(sum(scored) / len(scored), 6),
                "abstention_reason": representative["abstention_reason"] if not scored else None,
            }
        )

    collapsed_scored_values = [
        float(cast(int | float, item["score"]))
        for item in collapsed_entries
        if item["score"] is not None
    ]
    collapsed_total = sum(collapsed_scored_values)
    collapsed_scored_count = len(collapsed_scored_values)
    collapsed_abstention_count = sum(
        1
        for item in collapsed_entries
        if item["score"] is None and item["abstention_reason"] is not None
    )

    by_operator: dict[str, dict[str, Any]] = {}
    for operator in ("A", "B", "E"):
        raw_scores = [
            cast(int, item["review"]["human_usefulness_score"])
            for item, audit_item in zip(packet_items, audit_items, strict=True)
            if audit_item["operator"] == operator
            and item["review"]["human_usefulness_score"] is not None
        ]
        collapsed_scores = [
            cast(int | float, item["score"])
            for item in collapsed_entries
            if item["operator"] == operator and item["score"] is not None
        ]
        by_operator[operator] = {
            "raw_scores": raw_scores,
            "collapsed_scores": collapsed_scores,
            "mean_score": _mean_or_none(float(sum(collapsed_scores)), len(collapsed_scores)),
        }

    return {
        "packet_status": "completed",
        "reviewer_identity": reviewer_identity,
        "reviewed_at_utc": reviewed_at_utc,
        "all_scores_null": False,
        "blinded_item_count": len(packet_items),
        "duplicate_rationale": duplicate_rationale,
        "duplicate_group_count": len(by_group),
        "descriptive_only": True,
        "statistical_significance_inference": False,
        "raw": {
            "item_count": len(packet_items),
            "scored_item_count": raw_scored_count,
            "abstention_count": raw_abstention_count,
            "total_score": int(raw_total) if raw_total.is_integer() else round(raw_total, 6),
            "mean_score": _mean_or_none(raw_total, raw_scored_count),
        },
        "duplicate_collapsed": {
            "effective_item_count": len(collapsed_entries),
            "scored_item_count": collapsed_scored_count,
            "abstention_count": collapsed_abstention_count,
            "total_score": (
                int(collapsed_total) if collapsed_total.is_integer() else round(collapsed_total, 6)
            ),
            "mean_score": _mean_or_none(collapsed_total, collapsed_scored_count),
        },
        "by_operator": by_operator,
    }


def _validate_blinded_review_item_content(
    *,
    review_packet: Mapping[str, object],
    audit_manifest: Mapping[str, object],
    known_artifacts: Mapping[str, Mapping[str, Any]],
) -> None:
    packet_items = review_packet.get("items")
    audit_items = audit_manifest.get("items")
    assert isinstance(packet_items, list)
    assert isinstance(audit_items, list)
    raw_packet_items = review_packet.get("raw_items")
    raw_audit_items = audit_manifest.get("raw_items")
    assert isinstance(raw_packet_items, list)
    assert isinstance(raw_audit_items, list)
    for packet_item, audit_item in zip(raw_packet_items, raw_audit_items, strict=True):
        packet_mapping = _required_string_keyed_mapping(packet_item, "review_item")
        audit_mapping = _required_string_keyed_mapping(audit_item, "audit_item")
        artifact_hash = _required_sha256(audit_mapping, "artifact_hash")
        artifact = known_artifacts[artifact_hash]
        expected_content = _blinded_review_item_content_for_artifact(artifact)
        actual_content = {
            field: _required_string(packet_mapping, field) for field in BLIND_REVIEW_CONTENT_FIELDS
        }
        if actual_content != expected_content:
            raise ValueError("blinded review item content does not match the mapped artifact")
        if _required_sha256(
            audit_mapping, "review_content_sha256"
        ) != _blinded_review_item_content_sha256(expected_content):
            raise ValueError(
                "audit manifest review_content_sha256 does not match the mapped artifact"
            )


def _blinded_review_item_content_for_artifact(artifact_row: Mapping[str, Any]) -> dict[str, str]:
    operator = _required_string(artifact_row, "operator")
    if operator in {"A", "B"}:
        artifact = _required_string_keyed_mapping(artifact_row.get("artifact"), "artifact")
        candidate = _required_string_keyed_mapping(artifact.get("candidate"), "candidate")
        return {
            "proposal_title": _required_string(candidate, "title"),
            "proposal_summary": _required_string(candidate, "one_sentence_claim"),
            "mechanistic_rationale": _required_string(candidate, "mechanism"),
            "falsifiable_test": _required_string(candidate, "cheapest_falsifier"),
            "primary_metric": _required_string(candidate, "differential_prediction"),
        }
    if operator == "E":
        artifact = _required_string_keyed_mapping(artifact_row.get("artifact"), "artifact")
        test = _required_string_keyed_mapping(artifact.get("falsifiable_test"), "falsifiable_test")
        return {
            "proposal_title": _required_string(artifact, "title"),
            "proposal_summary": _required_string(artifact, "mechanistic_bridge"),
            "mechanistic_rationale": _required_string(artifact, "mechanistic_bridge"),
            "falsifiable_test": _required_string(test, "design"),
            "primary_metric": _required_string(test, "primary_metric"),
        }
    raise ValueError("unsupported blinded review artifact operator")


def _blinded_review_item_content_sha256(content: Mapping[str, str]) -> str:
    return sha256_hex(canonical_json(dict(content)))


def _allowed_temp_roots() -> tuple[Path, ...]:
    return tuple(
        {
            Path(tempfile.gettempdir()).resolve(strict=False),
            Path(tempfile.gettempdir()),
            Path("/tmp").resolve(strict=False),
            Path("/tmp"),
        }
    )


def _require_confined_scratch_runtime_paths(*, db_path: Path, index_path: Path) -> None:
    if db_path.name != "nsqd.sqlite":
        raise ValueError("scratch runtime db_path must target nsqd.sqlite")
    if index_path.name != "index":
        raise ValueError("scratch runtime index_path must target the index directory")
    if index_path.parent != db_path.parent:
        raise ValueError("scratch runtime db_path and index_path must share one scratch directory")
    scratch_root = db_path.parent
    if not scratch_root.name.startswith(ALLOWED_SCRATCH_PREFIX):
        raise ValueError("scratch runtime must use the dedicated nsqd-jepa-baselines- prefix")
    expanded_root = scratch_root.expanduser()
    resolved_root = expanded_root.resolve(strict=False)
    confined = _matching_allowed_temp_root(expanded_root, resolved_root)
    if confined is None:
        raise ValueError("scratch runtime must stay under an allowlisted system temp root")
    path_to_check, root_to_check = confined
    _require_non_symlink_path_within_root(
        path_to_check,
        root=root_to_check,
        field="scratch_runtime path",
    )


def _is_under_allowed_temp_root(expanded: Path, resolved: Path) -> bool:
    return _matching_allowed_temp_root(expanded, resolved) is not None


def _matching_allowed_temp_root(expanded: Path, resolved: Path) -> tuple[Path, Path] | None:
    expanded_abs = expanded if expanded.is_absolute() else expanded.resolve(strict=False)
    for root in _allowed_temp_roots():
        root_resolved = root.resolve(strict=False)
        if expanded_abs == root or root in expanded_abs.parents:
            return expanded_abs, root
        if resolved == root_resolved or root_resolved in resolved.parents:
            return resolved, root_resolved
    return None


def _read_verified_repo_file(*, relative_path: Path, expected_root: Path, field: str) -> bytes:
    return read_verified_repo_file(
        repo_root=REPO_ROOT,
        relative_path=relative_path,
        expected_root=expected_root,
        field=field,
    )


def _require_non_symlink_path_within_root(path: Path, *, root: Path, field: str) -> None:
    return require_non_symlink_path_within_root(path=path, root=root, field=field)


def _grounding_novelty_inputs(
    grounding: Mapping[str, object],
) -> tuple[float | None, SnapshotState, GroundingClass]:
    evidence = _optional_float(grounding.get("evidence"), field="grounding.evidence")
    snapshot_state = require_snapshot_state(_required_string(grounding, "snapshot_state"))
    grounding_class = _required_grounding_class(grounding.get("grounding_class"))
    return evidence, snapshot_state, grounding_class


def _optional_float(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric or null")
    return float(value)


def _required_grounding_class(value: object) -> GroundingClass:
    if value not in {
        "already_done",
        "renamed",
        "related_partial",
        "orthogonal",
        "clean_gap",
        "unevaluated",
    }:
        raise ValueError("grounding_class is invalid")
    return cast(GroundingClass, value)


def _candidate_artifact_hash(candidate: Mapping[str, object]) -> str:
    body = _mapping_without(candidate, exclude={"expected_outcomes"})
    return sha256_hex(canonical_json(body))


def _mapping_without(value: Mapping[str, object], *, exclude: set[str]) -> dict[str, object]:
    return {str(key): deepcopy(item) for key, item in value.items() if str(key) not in exclude}


def _canonical_payload_sha256(payload: Mapping[str, object]) -> str:
    return sha256_hex(canonical_json(payload))


def _json_mapping(raw_json: object) -> dict[str, Any]:
    loaded = json.loads(str(raw_json))
    if not isinstance(loaded, Mapping):
        raise ValueError("runtime payload must be a JSON object")
    return {str(key): item for key, item in loaded.items()}


def _load_yaml_mapping(path: Path, raw_bytes: bytes | None = None) -> dict[str, Any]:
    import yaml

    loaded = yaml.safe_load((raw_bytes or path.read_bytes()).decode("utf-8"))
    if not isinstance(loaded, Mapping):
        raise ValueError("projection binding must load a YAML mapping")
    return {str(key): item for key, item in loaded.items()}


def sha256_file_digest(path: Path) -> str:
    return _trusted_sha256_file_digest(path, max_bytes=MAX_RECEIPT_SQLITE_BYTES)


def _required_string_keyed_mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} is required")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field} keys must be strings")
        result[key] = item
    return result


def _required_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} is required")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} values must be strings")
        result.append(item.strip())
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _required_string(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_nonnegative_int(payload: Mapping[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _required_sha256(payload: Mapping[str, object], field: str) -> str:
    value = _required_string(payload, field)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value
