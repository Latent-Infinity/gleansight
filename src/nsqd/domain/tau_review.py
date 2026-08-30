from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, TypedDict

from nsqd.domain.novelty import NOVELTY_BIN_EDGES
from nsqd.domain.tau_measurement import (
    TAU_MEASUREMENT_POLICIES,
    qualify_tau_measurement_pair,
)

TAU_LABELS = frozenset({"near_duplicate", "novel", "ambiguous"})
TAU_REVIEW_POLICIES = TAU_MEASUREMENT_POLICIES
TAU_REVIEW_MIN_PER_CLASS_PER_POLICY = 30
TAU_REVIEW_MIN_MEASUREMENTS_PER_POLICY = TAU_REVIEW_MIN_PER_CLASS_PER_POLICY * 2
TAU_REVIEW_PROMPT_VERSION = "tau-label/1"
TAU_REVIEW_WORKFLOW = "one-writer-one-reviewer"
TAU_REVIEW_ROUNDS = 4
AUTONOMOUS_TAU_LOCAL_CALLS = TAU_REVIEW_ROUNDS * 2
AUTONOMOUS_TAU_WRITER_PROMPT_VERSION = "tau-writer/3"
AUTONOMOUS_TAU_REVIEWER_PROMPT_VERSION = "tau-reviewer/3"
AUTONOMOUS_TAU_ADJUDICATOR_PROMPT_VERSION = "tau-adjudicator/3"
AUTONOMOUS_TAU_SUPPORTED_PROMPT_VERSIONS = {
    "writer": frozenset({"tau-writer/2", AUTONOMOUS_TAU_WRITER_PROMPT_VERSION}),
    "reviewer": frozenset({"tau-reviewer/2", AUTONOMOUS_TAU_REVIEWER_PROMPT_VERSION}),
    "adjudicator": frozenset({"tau-adjudicator/2", AUTONOMOUS_TAU_ADJUDICATOR_PROMPT_VERSION}),
}
AUTONOMOUS_TAU_RATIONALE_MAX_CHARS = 320


def autonomous_tau_output_schema(pair_id: str | None = None) -> dict[str, object]:
    pair_id_schema: dict[str, object] = {"type": "string"}
    if pair_id is not None:
        pair_id_schema["enum"] = [pair_id]
    return {
        "type": "object",
        "properties": {
            "pair_id": pair_id_schema,
            "label": {
                "type": "string",
                "enum": ["near_duplicate", "novel", "ambiguous"],
            },
            "rationale": {
                "type": "string",
                "minLength": 1,
                "maxLength": AUTONOMOUS_TAU_RATIONALE_MAX_CHARS,
            },
        },
        "required": ["pair_id", "label", "rationale"],
        "additionalProperties": False,
    }


AUTONOMOUS_TAU_OUTPUT_SCHEMA = autonomous_tau_output_schema()
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


class TauMeasurementInventory(TypedDict):
    qualified_pair_count: int
    counts_by_policy: dict[str, int]
    shortfalls_by_policy: dict[str, int]
    ready_for_label_proposals: bool
    shortfall: str


class AutonomousTauPacketResult(TypedDict):
    selected_tau: None
    approved_pair_count: int
    ambiguous_pair_count: int
    counts_by_policy: dict[str, dict[str, int]]
    pending_autonomous_labels: bool
    audit_policy_revision: str


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
    return _packet_digest(rows)


def autonomous_tau_review_packet_digest(rows: Sequence[Mapping[str, object]]) -> str:
    return _packet_digest(rows)


def should_audit_tau_measurement(
    measurement_artifact_digest: str,
    *,
    audit_policy_revision: str,
    sample_rate: float,
) -> bool:
    digest = _required_sha256_string({"digest": measurement_artifact_digest}, "digest")
    _required_string({"audit_policy_revision": audit_policy_revision}, "audit_policy_revision")
    if not 0.0 <= sample_rate <= 0.10:
        raise ValueError("audit sample_rate must be between 0.0 and 0.10")
    ratio = int.from_bytes(
        hashlib.sha256(f"{audit_policy_revision}:{digest}".encode()).digest()[:8],
        "big",
    ) / float(1 << 64)
    return ratio < sample_rate


def evaluate_autonomous_tau_packet(
    rows: Sequence[Mapping[str, object]],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
    audit_policy_revision: str,
    audit_sample_rate: float,
) -> AutonomousTauPacketResult:
    _required_string({"audit_policy_revision": audit_policy_revision}, "audit_policy_revision")
    _require_audit_sample_rate(audit_sample_rate)
    reviewed = [
        _autonomous_reviewed_pair(
            row,
            approved_projection_digests=approved_projection_digests,
            trusted_measurement_digests=trusted_measurement_digests,
            audit_policy_revision=audit_policy_revision,
            audit_sample_rate=audit_sample_rate,
        )
        for row in rows
    ]
    pair_ids = [str(row["pair_id"]) for row in reviewed]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("tau review pair_id values must be unique")
    approved = [row for row in reviewed if row["label"] != "ambiguous"]
    return {
        "selected_tau": None,
        "approved_pair_count": len(approved),
        "ambiguous_pair_count": len(reviewed) - len(approved),
        "counts_by_policy": _counts_by_policy(approved),
        "pending_autonomous_labels": True,
        "audit_policy_revision": audit_policy_revision,
    }


def evaluate_balanced_autonomous_tau_packet(
    rows: Sequence[Mapping[str, object]],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
    audit_policy_revision: str,
    audit_sample_rate: float,
) -> TauPacketResult:
    _required_string({"audit_policy_revision": audit_policy_revision}, "audit_policy_revision")
    _require_audit_sample_rate(audit_sample_rate)
    reviewed = [
        _autonomous_reviewed_pair(
            row,
            approved_projection_digests=approved_projection_digests,
            trusted_measurement_digests=trusted_measurement_digests,
            audit_policy_revision=audit_policy_revision,
            audit_sample_rate=audit_sample_rate,
        )
        for row in rows
    ]
    pair_ids = [row["pair_id"] for row in reviewed]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("tau review pair_id values must be unique")
    approved = [row for row in reviewed if row["label"] != "ambiguous"]
    counts_by_policy = _counts_by_policy(approved)
    _require_balanced_packet(counts_by_policy)
    thresholds = [_threshold_result(approved, float(tau)) for tau in NOVELTY_BIN_EDGES]
    admissible = [row for row in thresholds if row["admissible"] is True]
    return {
        "selected_tau": max((row["tau"] for row in admissible), default=None),
        "approved_pair_count": len(approved),
        "ambiguous_pair_count": len(reviewed) - len(approved),
        "counts_by_policy": counts_by_policy,
        "thresholds": thresholds,
        "selection_rule": "highest admissible tau",
        "overall_false_kill_cap": OVERALL_FALSE_KILL_CAP,
        "per_policy_false_kill_cap": PER_POLICY_FALSE_KILL_CAP,
    }


def _packet_digest(rows: Sequence[Mapping[str, object]]) -> str:
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


def tau_measurement_inventory(
    rows: Sequence[Mapping[str, object]],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
) -> TauMeasurementInventory:
    qualified = [
        qualify_tau_measurement_pair(
            row,
            approved_projection_digests=approved_projection_digests,
            trusted_measurement_digests=trusted_measurement_digests,
        )
        for row in rows
    ]
    pair_ids = [str(row["pair_id"]) for row in qualified]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("tau review pair_id values must be unique")
    candidate_keys = [
        (str(row["domain_policy_id"]), str(row["candidate_artifact_hash"])) for row in qualified
    ]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise ValueError("duplicate candidate artifact hash")
    counts = {policy_id: 0 for policy_id in TAU_REVIEW_POLICIES}
    for row in qualified:
        counts[str(row["domain_policy_id"])] += 1
    shortfalls = {
        policy_id: max(0, TAU_REVIEW_MIN_MEASUREMENTS_PER_POLICY - counts[policy_id])
        for policy_id in TAU_REVIEW_POLICIES
    }
    ready = all(count >= TAU_REVIEW_MIN_MEASUREMENTS_PER_POLICY for count in counts.values())
    parts = [
        f"{policy_id} needs {needed} more measured pairs"
        for policy_id, needed in shortfalls.items()
        if needed > 0
    ]
    if not parts:
        shortfall = ""
    else:
        shortfall = "; ".join(parts) + "; do not fabricate or duplicate pairs"
    return {
        "qualified_pair_count": len(qualified),
        "counts_by_policy": counts,
        "shortfalls_by_policy": shortfalls,
        "ready_for_label_proposals": ready,
        "shortfall": shortfall,
    }


def require_tau_measurement_inventory(
    rows: Sequence[Mapping[str, object]],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
) -> TauMeasurementInventory:
    inventory = tau_measurement_inventory(
        rows,
        approved_projection_digests=approved_projection_digests,
        trusted_measurement_digests=trusted_measurement_digests,
    )
    if inventory["ready_for_label_proposals"] is not True:
        message = inventory["shortfall"] or "tau measurement inventory is insufficient"
        raise ValueError(str(message))
    return inventory


def _autonomous_reviewed_pair(
    row: Mapping[str, object],
    *,
    approved_projection_digests: frozenset[str],
    trusted_measurement_digests: frozenset[str],
    audit_policy_revision: str,
    audit_sample_rate: float,
) -> _ReviewedPair:
    qualified = qualify_tau_measurement_pair(
        row,
        approved_projection_digests=approved_projection_digests,
        trusted_measurement_digests=trusted_measurement_digests,
    )
    pair_id = _required_string(qualified, "pair_id")
    policy_id = _required_string(qualified, "domain_policy_id")
    measurement_artifact_digest = _required_sha256_string(qualified, "measurement_artifact_digest")
    rounds_value = row.get("rounds")
    if not isinstance(rounds_value, Sequence) or isinstance(rounds_value, (str, bytes)):
        raise ValueError("rounds are required")
    round_mappings = [_mapping_to_dict(item) for item in rounds_value if isinstance(item, Mapping)]
    rounds = [_validated_call(item, pair_id=pair_id) for item in round_mappings]
    local_rounds = [call for call in rounds if call["role"] in {"writer", "reviewer"}]
    if len(local_rounds) < AUTONOMOUS_TAU_LOCAL_CALLS:
        raise ValueError("at least 8 local round calls are required")
    if len(local_rounds) != AUTONOMOUS_TAU_LOCAL_CALLS:
        raise ValueError("exactly 8 local round calls are required")
    for index, expected_role in enumerate(
        [role for _ in range(TAU_REVIEW_ROUNDS) for role in ("writer", "reviewer")],
        start=1,
    ):
        call = local_rounds[index - 1]
        expected_round = ((index - 1) // 2) + 1
        if call["round"] != expected_round or call["role"] != expected_role:
            raise ValueError("rounds must contain writer then reviewer for each of 4 rounds")
        if call["prompt_version_id"] not in AUTONOMOUS_TAU_SUPPORTED_PROMPT_VERSIONS[expected_role]:
            raise ValueError(f"unsupported {expected_role} prompt version")
    writer_ids = {call["agent_id"] for call in local_rounds if call["role"] == "writer"}
    reviewer_ids = {call["agent_id"] for call in local_rounds if call["role"] == "reviewer"}
    writer_profiles = {call["profile"] for call in local_rounds if call["role"] == "writer"}
    reviewer_profiles = {call["profile"] for call in local_rounds if call["role"] == "reviewer"}
    if len(writer_ids) != 1 or len(reviewer_ids) != 1 or writer_ids == reviewer_ids:
        raise ValueError("writer and reviewer identities must differ")
    if (
        len(writer_profiles) != 1
        or len(reviewer_profiles) != 1
        or writer_profiles == reviewer_profiles
    ):
        raise ValueError("writer and reviewer identities must differ")
    writer_final = local_rounds[-2]
    reviewer_final = local_rounds[-1]
    escalation_reason: str | None = None
    if any(bool(call["schema_rationale_inconsistent"]) for call in local_rounds):
        escalation_reason = "schema_rationale_inconsistency"
    elif writer_final["label"] != reviewer_final["label"]:
        escalation_reason = "final_disagreement"
    elif writer_final["label"] == "ambiguous":
        escalation_reason = "final_ambiguity"
    elif should_audit_tau_measurement(
        measurement_artifact_digest,
        audit_policy_revision=audit_policy_revision,
        sample_rate=audit_sample_rate,
    ):
        escalation_reason = "deterministic_audit"

    adjudication_value = row.get("adjudication")
    final_label = str(reviewer_final["label"])
    final_rationale = str(reviewer_final["rationale"])
    if escalation_reason is not None:
        if not isinstance(adjudication_value, Mapping):
            raise ValueError("adjudication is required for escalated tau rows")
        adjudication = _validated_call(_mapping_to_dict(adjudication_value), pair_id=pair_id)
        if adjudication["role"] != "adjudicator":
            raise ValueError("adjudication role must be adjudicator")
        if (
            adjudication["prompt_version_id"]
            not in AUTONOMOUS_TAU_SUPPORTED_PROMPT_VERSIONS["adjudicator"]
        ):
            raise ValueError("unsupported adjudicator prompt version")
        if (
            adjudication["agent_id"] in writer_ids | reviewer_ids
            or adjudication["profile"] in writer_profiles | reviewer_profiles
        ):
            raise ValueError("adjudicator identity must differ from writer and reviewer")
        final_label = str(adjudication["label"])
        final_rationale = str(adjudication["rationale"])
        escalation = _required_mapping(row, "escalation")
        if _required_string(escalation, "reason") != escalation_reason:
            raise ValueError("escalation reason does not match row state")
        if escalation_reason == "deterministic_audit":
            if _required_string(escalation, "audit_policy_revision") != audit_policy_revision:
                raise ValueError("audit policy revision does not match packet")
    else:
        if adjudication_value is not None:
            raise ValueError("adjudication must be absent when no escalation is required")
        if row.get("escalation") is not None:
            raise ValueError("escalation must be absent when no escalation is required")

    if _required_label(row, "final_label") != final_label:
        raise ValueError("final_label does not match resolved row label")
    if _required_string(row, "final_rationale") != final_rationale:
        raise ValueError("final_rationale does not match resolved row rationale")
    evidence = _required_finite_number(qualified["measurement"], "evidence_mean_distance")
    return {
        "pair_id": pair_id,
        "policy_id": policy_id,
        "label": final_label,
        "evidence": evidence,
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


def _validated_call(value: Mapping[str, object], *, pair_id: str) -> dict[str, object]:
    round_number = value.get("round")
    if isinstance(round_number, bool) or not isinstance(round_number, int) or round_number < 1:
        raise ValueError("round must be a positive integer")
    role = _required_string(value, "role")
    if role not in {"writer", "reviewer", "adjudicator"}:
        raise ValueError("role must be writer, reviewer, or adjudicator")
    prompt = _required_string(value, "prompt")
    if _required_sha256_string(value, "prompt_sha256") != _text_digest(prompt):
        raise ValueError("prompt digest drift")
    input_payload = _required_mapping(value, "input_payload")
    if _required_sha256_string(value, "input_sha256") != _json_digest(input_payload):
        raise ValueError("input digest drift")
    output_text = _required_string(value, "output_text")
    if _required_sha256_string(value, "output_sha256") != _text_digest(output_text):
        raise ValueError("output digest drift")
    output = _parse_json_mapping(output_text, key="output_text")
    if _required_string(output, "pair_id") != pair_id:
        raise ValueError("output pair_id does not match row")
    label = _required_label(output, "label")
    rationale = _required_string(output, "rationale")
    if _required_label(value, "label") != label:
        raise ValueError("recorded label does not match output payload")
    if _required_string(value, "rationale") != rationale:
        raise ValueError("recorded rationale does not match output payload")
    _required_utc_timestamp(value, "called_at")
    return {
        "round": round_number,
        "role": role,
        "agent_id": _required_string(value, "agent_id"),
        "provider": _required_string(value, "provider"),
        "model": _required_string(value, "model"),
        "version": _required_string(value, "version"),
        "profile": _required_string(value, "profile"),
        "prompt_version_id": _required_string(value, "prompt_version_id"),
        "label": label,
        "rationale": rationale,
        "response_metadata": _validated_response_metadata(value),
        "schema_rationale_inconsistent": _schema_rationale_inconsistent(
            label=label,
            rationale=rationale,
        ),
    }


def _mapping_to_dict(value: Mapping[Any, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def _validated_response_metadata(value: Mapping[str, object]) -> dict[str, object]:
    metadata = _required_mapping(value, "response_metadata")
    provider = _required_string(value, "provider")
    if metadata.get("identity_source") == "requested_and_reroute_checked":
        if provider != "codex_subscription":
            raise ValueError("codex identity source requires codex_subscription provider")
        requested_model = _required_string(metadata, "requested_model")
        if requested_model != _required_string(value, "model"):
            raise ValueError("returned model does not match configured route model")
        if _required_string(metadata, "provider") != "codex_subscription":
            raise ValueError("codex provider metadata is invalid")
        if _required_string(metadata, "auth_mode") != "chatgpt":
            raise ValueError("codex auth mode must be chatgpt")
        _required_string(metadata, "codex_cli_version")
        _required_string(metadata, "reasoning_effort")
        return metadata
    returned_model = _required_string(metadata, "model")
    if returned_model != _required_string(value, "model"):
        raise ValueError("returned model does not match configured route model")
    system_fingerprint = metadata.get("system_fingerprint")
    if system_fingerprint is not None and not isinstance(system_fingerprint, str):
        raise ValueError("system_fingerprint must be a string")
    created = metadata.get("created")
    if created is not None and (isinstance(created, bool) or not isinstance(created, int)):
        raise ValueError("created must be an integer timestamp")
    result: dict[str, object] = {"model": returned_model}
    if isinstance(system_fingerprint, str):
        result["system_fingerprint"] = system_fingerprint
    if isinstance(created, int):
        result["created"] = created
    return result


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} is required")
    return item.strip()


def _required_sha256_string(value: Mapping[str, object], key: str) -> str:
    digest = _required_string(value, key)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{key} must be a lowercase SHA-256 hex digest")
    return digest


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


def _require_audit_sample_rate(sample_rate: float) -> None:
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, (int, float)):
        raise ValueError("audit sample_rate must be between 0.0 and 0.10")
    if not math.isfinite(float(sample_rate)) or not 0.0 <= sample_rate <= 0.10:
        raise ValueError("audit sample_rate must be between 0.0 and 0.10")


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _json_digest(value: Mapping[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _parse_json_mapping(value: str, *, key: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} must be valid JSON") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError(f"{key} must be a JSON object")
    result: dict[str, object] = {}
    for item_key, item_value in parsed.items():
        if isinstance(item_key, str):
            result[item_key] = item_value
    return result


def _schema_rationale_inconsistent(*, label: str, rationale: str) -> bool:
    lower = rationale.lower()
    mentioned = {candidate for candidate in TAU_LABELS if candidate in lower}
    return bool(mentioned) and (label not in mentioned or len(mentioned) > 1)
