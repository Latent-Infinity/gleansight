from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import TypedDict

from nsqd.domain.novelty import NOVELTY_BIN_EDGES

TAU_LABELS = frozenset({"near_duplicate", "novel", "ambiguous"})
TAU_REVIEW_POLICIES = ("finance/1", "optimization/1")
TAU_REVIEW_MIN_PER_CLASS_PER_POLICY = 30
TAU_REVIEW_PROMPT_VERSION = "tau-label/1"
TAU_REVIEW_WORKFLOW = "one-writer-one-reviewer"
TAU_REVIEW_ROUNDS = 4
OVERALL_FALSE_KILL_CAP = 0.05
PER_POLICY_FALSE_KILL_CAP = 0.10


class _ReviewedPair(TypedDict):
    pair_id: str
    policy_id: str
    label: str
    evidence: float


class _ThresholdResult(TypedDict):
    tau: float
    admissible: bool
    novel_false_kill_rate: float
    novel_false_kill_rate_by_policy: dict[str, float]
    near_duplicate_false_pass_rate: float


class TauPacketResult(TypedDict):
    selected_tau: float | None
    approved_pair_count: int
    ambiguous_pair_count: int
    counts_by_policy: dict[str, dict[str, int]]
    thresholds: list[_ThresholdResult]
    selection_rule: str
    overall_false_kill_cap: float
    per_policy_false_kill_cap: float


def build_tau_label_prompt(pair: Mapping[str, object]) -> str:
    pair_id = _required_string(pair, "pair_id")
    policy_id = _required_string(pair, "domain_policy_id")
    candidate = _required_mapping(pair, "candidate")
    neighbor = _required_mapping(pair, "neighbor")
    measurement = _required_mapping(pair, "measurement")
    prompt_input = {
        "pair_id": pair_id,
        "domain_policy_id": policy_id,
        "candidate": candidate,
        "neighbor": neighbor,
        "measurement": measurement,
    }
    return (
        f"Prompt version: {TAU_REVIEW_PROMPT_VERSION}\n"
        "Classify this novelty pair as near_duplicate | novel | ambiguous. "
        "Use one writer and one independent reviewer for four refinement rounds. "
        "This is a proposal only: the agent must not approve evidence.\n"
        "Return one JSON object with exactly this shape:\n"
        '{"pair_id": "...", "label": "near_duplicate | novel | ambiguous", '
        '"confidence": 0.0, "rationale": "...", "review_status": "pending", '
        f'"prompt_version_id": "{TAU_REVIEW_PROMPT_VERSION}", "model": "...", '
        '"profile": "...", "review_workflow": "one-writer-one-reviewer", '
        '"review_rounds": 4}\n'
        f"Pair:\n{json.dumps(prompt_input, sort_keys=True, ensure_ascii=False)}"
    )


def parse_tau_label_proposal(proposal: Mapping[str, object]) -> dict[str, object]:
    pair_id = _required_string(proposal, "pair_id")
    label = _required_label(proposal, "label")
    confidence = _required_finite_number(proposal, "confidence")
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be between 0 and 1")
    rationale = _required_string(proposal, "rationale")
    if proposal.get("review_status") != "pending":
        raise ValueError("agent proposals must remain pending")
    prompt_version_id = _required_string(proposal, "prompt_version_id")
    if prompt_version_id != TAU_REVIEW_PROMPT_VERSION:
        raise ValueError("unsupported tau label prompt version")
    model = _required_string(proposal, "model")
    profile = _required_string(proposal, "profile")
    if proposal.get("review_workflow") != TAU_REVIEW_WORKFLOW:
        raise ValueError("tau label proposals require one writer and one reviewer")
    if proposal.get("review_rounds") != TAU_REVIEW_ROUNDS:
        raise ValueError("tau label proposals require four review rounds")
    return {
        "pair_id": pair_id,
        "label": label,
        "confidence": confidence,
        "rationale": rationale,
        "review_status": "pending",
        "prompt_version_id": prompt_version_id,
        "model": model,
        "profile": profile,
        "review_workflow": TAU_REVIEW_WORKFLOW,
        "review_rounds": TAU_REVIEW_ROUNDS,
    }


def tau_review_packet_digest(rows: Sequence[Mapping[str, object]]) -> str:
    try:
        payload = json.dumps(
            list(rows),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("tau review packet must be JSON serializable") from exc
    return hashlib.sha256(payload).hexdigest()


def evaluate_tau_packet(
    rows: Sequence[Mapping[str, object]],
    *,
    manifest: Mapping[str, object],
    trusted_reviewers: frozenset[str],
) -> TauPacketResult:
    _validate_manifest(rows, manifest, trusted_reviewers=trusted_reviewers)
    reviewed = [_reviewed_pair(row, manifest=manifest) for row in rows]
    pair_ids = [str(row["pair_id"]) for row in reviewed]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("tau review pair_id values must be unique")

    approved = [row for row in reviewed if row["label"] != "ambiguous"]
    counts_by_policy = _counts_by_policy(approved)
    _require_balanced_packet(counts_by_policy)

    thresholds = [_threshold_result(approved, float(tau)) for tau in NOVELTY_BIN_EDGES]
    admissible = [row for row in thresholds if row["admissible"] is True]
    selected_tau = max((row["tau"] for row in admissible), default=None)
    return {
        "selected_tau": selected_tau,
        "approved_pair_count": len(approved),
        "ambiguous_pair_count": len(reviewed) - len(approved),
        "counts_by_policy": counts_by_policy,
        "thresholds": thresholds,
        "selection_rule": "highest admissible tau",
        "overall_false_kill_cap": OVERALL_FALSE_KILL_CAP,
        "per_policy_false_kill_cap": PER_POLICY_FALSE_KILL_CAP,
    }


def _validate_manifest(
    rows: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    *,
    trusted_reviewers: frozenset[str],
) -> None:
    expected_digest = _required_string(manifest, "content_sha256")
    if expected_digest != tau_review_packet_digest(rows):
        raise ValueError("tau review manifest content hash does not match packet")
    reviewer = _required_string(manifest, "reviewer")
    if reviewer not in trusted_reviewers:
        raise ValueError("tau review manifest reviewer is not trusted")
    _required_utc_timestamp(manifest, "approved_at")
    _required_string(manifest, "approval_revision")


def _reviewed_pair(
    row: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
) -> _ReviewedPair:
    pair_id = _required_string(row, "pair_id")
    policy_id = _required_string(row, "domain_policy_id")
    if policy_id not in TAU_REVIEW_POLICIES:
        raise ValueError("tau review uses finance/1 and optimization/1 policies")
    if row.get("snapshot_state") not in {"calibration", "production_valid"}:
        raise ValueError("tau review requires calibration or production_valid snapshots")
    _required_string(row, "snapshot_id")
    _required_mapping(row, "candidate")
    _required_mapping(row, "neighbor")

    proposal = parse_tau_label_proposal(_required_mapping(row, "agent_proposal"))
    if proposal["pair_id"] != pair_id:
        raise ValueError("agent proposal pair_id does not match review pair")

    review = _required_mapping(row, "human_review")
    label = _required_label(review, "label")
    reviewer = _required_string(review, "reviewer")
    approved_at = _required_utc_timestamp(review, "approved_at")
    approval_revision = _required_string(review, "approval_revision")
    if reviewer != manifest["reviewer"]:
        raise ValueError("human reviewer does not match packet manifest")
    if reviewer in {proposal["model"], proposal["profile"]}:
        raise ValueError("human reviewer cannot be the proposing model or profile")
    if approved_at != manifest["approved_at"]:
        raise ValueError("human approval timestamp does not match packet manifest")
    if approval_revision != manifest["approval_revision"]:
        raise ValueError("human approval revision does not match packet manifest")

    measurement = _required_mapping(row, "measurement")
    evidence = _required_finite_number(measurement, "evidence_mean_distance")
    if evidence < 0:
        raise ValueError("evidence_mean_distance must be a finite non-negative number")
    k = measurement.get("k")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("measurement k must be a positive integer")
    return {
        "pair_id": pair_id,
        "policy_id": policy_id,
        "label": label,
        "evidence": evidence,
    }


def _counts_by_policy(rows: Sequence[_ReviewedPair]) -> dict[str, dict[str, int]]:
    counts = {policy_id: {"near_duplicate": 0, "novel": 0} for policy_id in TAU_REVIEW_POLICIES}
    for row in rows:
        policy_id = row["policy_id"]
        label = row["label"]
        counts[policy_id][label] += 1
    return counts


def _require_balanced_packet(counts: Mapping[str, Mapping[str, int]]) -> None:
    for policy_id in TAU_REVIEW_POLICIES:
        policy_counts = counts[policy_id]
        for label in ("near_duplicate", "novel"):
            if policy_counts[label] < TAU_REVIEW_MIN_PER_CLASS_PER_POLICY:
                raise ValueError(f"{policy_id} requires at least 30 approved {label} pairs")


def _threshold_result(rows: Sequence[_ReviewedPair], tau: float) -> _ThresholdResult:
    novel = [row for row in rows if row["label"] == "novel"]
    near = [row for row in rows if row["label"] == "near_duplicate"]
    novel_killed = [row for row in novel if row["evidence"] < tau]
    near_passed = [row for row in near if row["evidence"] >= tau]
    overall_false_kill = len(novel_killed) / len(novel)
    per_policy_false_kill: dict[str, float] = {}
    for policy_id in TAU_REVIEW_POLICIES:
        policy_novel = [row for row in novel if row["policy_id"] == policy_id]
        killed = [row for row in policy_novel if row["evidence"] < tau]
        per_policy_false_kill[policy_id] = len(killed) / len(policy_novel)
    admissible = overall_false_kill <= OVERALL_FALSE_KILL_CAP and all(
        rate <= PER_POLICY_FALSE_KILL_CAP for rate in per_policy_false_kill.values()
    )
    return {
        "tau": tau,
        "admissible": admissible,
        "novel_false_kill_rate": overall_false_kill,
        "novel_false_kill_rate_by_policy": per_policy_false_kill,
        "near_duplicate_false_pass_rate": len(near_passed) / len(near),
    }


def _required_mapping(value: Mapping[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"{key} is required")
    result: dict[str, object] = {}
    for item_key, item_value in item.items():
        if not isinstance(item_key, str):
            raise ValueError(f"{key} keys must be strings")
        result[item_key] = item_value
    return result


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} is required")
    return item.strip()


def _required_label(value: Mapping[str, object], key: str) -> str:
    label = _required_string(value, key)
    if label not in TAU_LABELS:
        raise ValueError("tau review label must be near_duplicate, novel, or ambiguous")
    return label


def _required_finite_number(value: Mapping[str, object], key: str) -> float:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise ValueError(f"{key} must be a finite non-negative number")
    result = float(item)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be a finite non-negative number")
    return result


def _required_utc_timestamp(value: Mapping[str, object], key: str) -> str:
    timestamp = _required_string(value, key)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{key} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{key} must be a UTC timestamp")
    return parsed.isoformat()
