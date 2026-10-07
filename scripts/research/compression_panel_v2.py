from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

LABELS = {"supported", "contradicted", "insufficient_evidence"}
PROTOCOL_VERSION = "compression-evidence-review-v1"


def allowed_refs(claim: dict[str, Any]) -> set[str]:
    return {
        f"{claim['source_id']}:{item['locator']}:[{item['byte_start']},{item['byte_end']})"
        for item in claim["evidence"]
    }


def parse_primary_outputs(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    claude_outer = json.loads((run_dir / "claude.stdout.raw").read_text(encoding="utf-8"))
    claude = json.loads(claude_outer["result"])
    codex_events = [
        json.loads(line)
        for line in (run_dir / "codex.stdout.raw").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    codex_text = "\n".join(
        event["item"]["text"]
        for event in codex_events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "agent_message"
    )
    codex = json.loads(codex_text)
    return {"claude": claude["votes"], "codex": codex["votes"]}


def primary_disagreements(
    claims: list[dict[str, Any]],
    votes: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if set(votes) != {"claude", "codex"}:
        raise ValueError("exactly the two primary reviewers are required")
    if len(votes["claude"]) != len(claims) or len(votes["codex"]) != len(claims):
        raise ValueError("primary vote count does not match the evidence claims")

    selected: list[dict[str, Any]] = []
    for claim, claude_vote, codex_vote in zip(
        claims, votes["claude"], votes["codex"], strict=True
    ):
        expected_id = claim["claim_id"]
        for reviewer, vote in (("claude", claude_vote), ("codex", codex_vote)):
            if vote.get("claim_id") != expected_id or vote.get("label") not in LABELS:
                raise ValueError(f"invalid {reviewer} primary vote for {expected_id}")
            refs = vote.get("evidence_refs")
            if (
                not isinstance(refs, list)
                or not refs
                or not all(isinstance(ref, str) for ref in refs)
                or not set(refs) <= allowed_refs(claim)
            ):
                raise ValueError(f"invalid {reviewer} evidence references for {expected_id}")
        if claude_vote["label"] == codex_vote["label"]:
            continue
        selected.append(
            {
                "claim_id": expected_id,
                "claim": claim["claim"],
                "condition_caveat": claim.get("condition_caveat", ""),
                "source_id": claim["source_id"],
                "evidence": claim["evidence"],
                "primary_votes": [
                    {"label": claude_vote["label"], "rationale": claude_vote["rationale"]},
                    {"label": codex_vote["label"], "rationale": codex_vote["rationale"]},
                ],
            }
        )
    return selected


def make_tiebreak_packet(
    protocol_version: str,
    disagreements: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "protocol_version": protocol_version,
        "task": (
            "Independently decide each claim using only its supplied evidence and rubric. "
            "The two anonymous primary votes and rationales are context, not authority. "
            "Do not use tools, web search, files, subagents, or outside context. "
            "Return exactly one JSON object with protocol_version and votes, in input order. "
            "Each vote must contain claim_id, label, rationale, and evidence_refs. "
            "Use only supplied source_id:locator:[byte_start,byte_end) evidence references."
        ),
        "rubric": {
            "supported": (
                "The supplied excerpt supports the claim as written, including scope qualifiers."
            ),
            "contradicted": "The supplied excerpt conflicts with the claim as written.",
            "insufficient_evidence": (
                "The excerpts establish neither outcome or omit a necessary condition."
            ),
        },
        "claims": disagreements,
    }


def validate_tiebreak_votes(
    packet: dict[str, Any], result: dict[str, Any]
) -> tuple[dict[str, str | None], list[dict[str, str]]]:
    claims = packet["claims"]
    expected_ids = [claim["claim_id"] for claim in claims]
    effective: dict[str, str | None] = {claim_id: None for claim_id in expected_ids}
    invalid: list[dict[str, str]] = []
    if set(result) != {"protocol_version", "votes"}:
        return effective, [{"claim_id": "*", "reason": "unexpected_top_level_shape"}]
    if result["protocol_version"] != packet["protocol_version"]:
        return effective, [{"claim_id": "*", "reason": "protocol_version_mismatch"}]
    votes = result["votes"]
    if not isinstance(votes, list) or len(votes) != len(claims):
        return effective, [{"claim_id": "*", "reason": "wrong_vote_count"}]

    for claim, vote, expected_id in zip(claims, votes, expected_ids, strict=True):
        reason: str | None = None
        if not isinstance(vote, dict) or set(vote) != {
            "claim_id",
            "label",
            "rationale",
            "evidence_refs",
        }:
            reason = "unexpected_vote_shape"
        elif vote["claim_id"] != expected_id:
            reason = "wrong_or_out_of_order_claim_id"
        elif vote["label"] not in LABELS:
            reason = "invalid_label"
        elif not isinstance(vote["rationale"], str) or not vote["rationale"].strip():
            reason = "missing_rationale"
        elif (
            not isinstance(vote["evidence_refs"], list)
            or not vote["evidence_refs"]
            or not all(isinstance(ref, str) for ref in vote["evidence_refs"])
            or not set(vote["evidence_refs"]) <= allowed_refs(claim)
        ):
            reason = "invalid_or_unbound_evidence_reference"
        if reason:
            invalid.append({"claim_id": expected_id, "reason": reason})
        else:
            effective[expected_id] = vote["label"]
    return effective, invalid


def cohen_kappa(left: list[str], right: list[str]) -> float | None:
    if not left or len(left) != len(right):
        return None
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_counts, right_counts = Counter(left), Counter(right)
    expected = sum(
        (left_counts[label] / len(left)) * (right_counts[label] / len(right))
        for label in LABELS
    )
    return None if expected == 1 else (observed - expected) / (1 - expected)


def cluster_bootstrap_kappa(
    rows: list[tuple[str, str, str]], *, replicates: int = 2000, seed: int = 17
) -> dict[str, Any]:
    clusters = sorted({cluster for cluster, _, _ in rows})
    if not clusters:
        return {"finite_replicates": 0, "interval_95": None}
    by_cluster = {
        cluster: [(left, right) for row_cluster, left, right in rows if row_cluster == cluster]
        for cluster in clusters
    }
    point = cohen_kappa([left for _, left, _ in rows], [right for _, _, right in rows])
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        sampled_clusters = [rng.choice(clusters) for _ in clusters]
        sample = [pair for cluster in sampled_clusters for pair in by_cluster[cluster]]
        estimate = cohen_kappa(
            [left for left, _ in sample], [right for _, right in sample]
        )
        if estimate is not None:
            estimates.append(estimate)
    estimates.sort()

    def percentile(probability: float) -> float:
        position = (len(estimates) - 1) * probability
        low = int(position)
        high = min(low + 1, len(estimates) - 1)
        return estimates[low] * (high - position) + estimates[high] * (position - low)

    return {
        "point_kappa": point,
        "clusters": len(clusters),
        "replicates": replicates,
        "finite_replicates": len(estimates),
        "interval_95": [percentile(0.025), percentile(0.975)] if estimates else None,
        "seed": seed,
    }


def resolve_disagreement(primary_labels: list[str], tiebreak_label: str | None) -> str | None:
    if len(primary_labels) != 2 or any(label not in LABELS for label in primary_labels):
        raise ValueError("a valid two-label primary disagreement is required")
    if primary_labels[0] == primary_labels[1]:
        raise ValueError("resolution is only defined for primary disagreements")
    if tiebreak_label not in LABELS:
        return None
    return tiebreak_label if tiebreak_label in primary_labels else None
