from __future__ import annotations

import argparse
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

import yaml

from nsqd.app.use_cases import artifact_hash_for
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.domain.snapshot import canonical_json, sha256_hex


@dataclass(frozen=True)
class SourceProjection:
    path: Path
    variants: int
    descriptor: dict[str, str]


FRAMINGS = (
    "A direct replication candidate restates the finding as follows: {paraphrase}",
    "For an independently rerun test, the claim is: {paraphrase}",
    "The replication hypothesis preserves the reported scope: {paraphrase}",
    "A follow-up test uses this formulation: {paraphrase}",
    "The candidate checks the reported relationship in this form: {paraphrase}",
    "An independent reproduction evaluates the following claim: {paraphrase}",
)


def _sources(root: Path) -> tuple[SourceProjection, ...]:
    projection_dir = root / "docs/reviews/nsqd-projection-review-2026-08-28/final"
    fixture_dir = root / "tests/fixtures/approved/nsqd"
    return (
        SourceProjection(
            projection_dir / "N11-FIN-01.yaml",
            5,
            {"mechanism": "institutional", "target": "returns", "horizon": "daily"},
        ),
        SourceProjection(
            projection_dir / "N11-FIN-02.yaml",
            5,
            {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
        ),
        SourceProjection(
            projection_dir / "N11-FIN-03.yaml",
            5,
            {"mechanism": "shock-propagation", "target": "returns", "horizon": "daily"},
        ),
        SourceProjection(
            projection_dir / "N11-FIN-04.yaml",
            5,
            {"mechanism": "institutional", "target": "returns", "horizon": "daily"},
        ),
        SourceProjection(
            projection_dir / "N11-FIN-05.yaml",
            5,
            {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
        ),
        SourceProjection(
            fixture_dir / "gamma-fragility.yaml",
            5,
            {"mechanism": "flow-driven", "target": "drawdown", "horizon": "intraday"},
        ),
        SourceProjection(
            projection_dir / "N11-OPT-01.yaml",
            6,
            {"problem": "unconstrained", "method": "first-order", "setting": "full-rank"},
        ),
        SourceProjection(
            projection_dir / "N11-OPT-02.yaml",
            6,
            {"problem": "unconstrained", "method": "first-order", "setting": "full-rank"},
        ),
        SourceProjection(
            projection_dir / "N11-OPT-03.yaml",
            6,
            {
                "problem": "constrained-expectation",
                "method": "first-order",
                "setting": "full-rank",
            },
        ),
        SourceProjection(
            projection_dir / "N11-OPT-04.yaml",
            6,
            {
                "problem": "constrained-expectation",
                "method": "sequential-quadratic",
                "setting": "rank-deficient",
            },
        ),
        SourceProjection(
            projection_dir / "N11-OPT-05.yaml",
            6,
            {"problem": "unconstrained", "method": "first-order", "setting": "full-rank"},
        ),
    )


def _reviewed_projection_digests(root: Path) -> dict[str, str]:
    manifest_path = root / "docs/reviews/nsqd-projection-review-2026-08-28/final/manifest.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        str(row["id"]): str(row["reviewed_projection_sha256"])
        for row in manifest["fixture"].values()
    }


def _candidate_fixture(
    projection: dict[str, object],
    *,
    candidate_id: str,
    descriptor: dict[str, str],
    variant: int,
) -> dict[str, object]:
    paraphrase = str(projection["paraphrase"]).strip()
    framed = FRAMINGS[variant - 1].format(paraphrase=paraphrase)
    policy_id = str(projection["domain_policy_id"])
    source_id = str(projection["id"])
    fixture: dict[str, object] = {
        "schema_version": 1,
        "kind": "candidate-requirement-card",
        "id": candidate_id,
        "domain_policy_id": policy_id,
        "title": f"Replication candidate for {source_id}, variant {variant}",
        "one_sentence_claim": framed,
        "mechanism": f"Re-evaluate the mechanism reported by approved projection {source_id}.",
        "differential_prediction": (
            "The reproduced test should preserve the approved claim's direction and scope."
        ),
        "cheapest_falsifier": (
            "Repeat the source paper's reported comparison on an independent held-out sample."
        ),
        "kill_criteria": (
            "Reject the replication candidate if the reported relationship does not reproduce."
        ),
        "research_descriptor": descriptor,
        "paraphrase": framed,
    }
    if policy_id == "finance/1":
        fixture.update(
            {
                "inefficiency": "Use the same market friction identified by the approved source.",
                "counterparty": "Retain the source paper's stated counterparties.",
                "persistence": "Test persistence only over the source paper's stated horizon.",
                "capacity": "Estimate capacity under the same liquidity assumptions.",
                "regime_dependence": "Preserve the source paper's stated regime conditions.",
            }
        )
    return fixture


def build_packet(root: Path, output_dir: Path) -> dict[str, object]:
    approved_digests = _reviewed_projection_digests(root)
    rows: list[dict[str, object]] = []
    policy_counts = {"finance/1": 0, "optimization/1": 0}
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in _sources(root):
        source_bytes = source.path.read_bytes()
        projection = yaml.safe_load(source_bytes)
        if not isinstance(projection, dict):
            raise ValueError(f"projection must be a mapping: {source.path}")
        policy_id = str(projection["domain_policy_id"])
        source_id = str(projection["id"])
        reviewed_digest = approved_digests.get(source_id)
        if reviewed_digest is None:
            reviewed_digest = canonical_reviewed_projection_digest(projection)
        prefix = "fin" if policy_id == "finance/1" else "opt"
        for variant in range(1, source.variants + 1):
            policy_counts[policy_id] += 1
            candidate_id = f"nsqd-{prefix}-nd-{policy_counts[policy_id]:03d}"
            fixture = _candidate_fixture(
                projection,
                candidate_id=candidate_id,
                descriptor=source.descriptor,
                variant=variant,
            )
            fixture_path = output_dir / f"{candidate_id}.yaml"
            fixture_path.write_text(
                yaml.safe_dump(fixture, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_fixture": fixture_path.name,
                    "candidate_artifact_hash": artifact_hash_for(fixture),
                    "domain_policy_id": policy_id,
                    "source_projection_id": source_id,
                    "source_projection_path": str(source.path.relative_to(root)),
                    "source_projection_file_sha256": sha256_hex(source_bytes),
                    "reviewed_projection_digest": reviewed_digest,
                    "axiom": (
                        "Bounded real replication candidate derived from an approved projection."
                    ),
                }
            )
    if policy_counts != {"finance/1": 30, "optimization/1": 30}:
        raise ValueError(f"unexpected policy counts: {policy_counts}")
    if len({row["candidate_artifact_hash"] for row in rows}) != len(rows):
        raise ValueError("candidate artifact hashes must be unique")
    packet: dict[str, object] = {
        "schema_version": 1,
        "snapshot_id": "bb63826c4c648027fdae12c92b714e2be12b434c5530af211718c491a1afe8a5",
        "corpus_version": 11,
        "class_intent": "semantic-replication-reserve-without-labels",
        "counts_by_policy": policy_counts,
        "candidates": rows,
    }
    packet["candidate_rows_sha256"] = sha256_hex(canonical_json(rows))
    return packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    packet = build_packet(root, args.output_dir)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"counts_by_policy": packet["counts_by_policy"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
