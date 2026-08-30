from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from nsqd.app.use_cases import (
    DivergeUseCase,
    GroundUseCase,
    HarvestUseCase,
    ProjectPaperUseCase,
    PromoteSnapshotUseCase,
    ScoreUseCase,
    _index_paraphrases,
)
from nsqd.domain.novelty import apply_novelty_threshold, novelty_term
from nsqd.domain.policy import POLICIES
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.domain.viability import score_mech
from nsqd.null_adapters import (
    FixedClock,
    HashParaphraseEmbedder,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullFrontierCardStore,
    NullHarvestStore,
    NullNsqdCandidateStore,
    NullPolicyVerdictStore,
)

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
NSQD = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"
EMBEDDER = HashParaphraseEmbedder()


def _load_yaml(name: str) -> dict[str, object]:
    payload = yaml.safe_load((NSQD / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_harvest_upserts_paraphrase_vector() -> None:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    index = NullCorpusIndex()
    result = HarvestUseCase(
        harvest=NullHarvestStore(records, snapshots),
        clock=FixedClock(AS_OF),
        index=index,
        embedder=EMBEDDER,
    ).run(
        {
            "records": [
                {
                    "type": "paper",
                    "paraphrase": "Dealer gamma imbalance under illiquidity.",
                    "source": "doi:10.1/indexed",
                    "domain_policy_id": "finance/1",
                }
            ]
        }
    )
    record_id = result["record_ids"][0]
    hits = index.query(
        result["snapshot_id"],
        EMBEDDER.embed("Dealer gamma imbalance under illiquidity."),
        k=1,
        allowed_record_ids=frozenset({record_id}),
    )
    assert hits
    assert hits[0].record_id == record_id
    assert hits[0].distance == 0.0


def test_project_indexes_gamma_fragility_and_scores_gamma_flow() -> None:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    index = NullCorpusIndex()
    candidates = NullNsqdCandidateStore()
    cards = NullFrontierCardStore()
    projection = _load_yaml("gamma-fragility.yaml")
    digest = canonical_reviewed_projection_digest(projection)
    projected = ProjectPaperUseCase(
        harvest=NullHarvestStore(records, snapshots),
        records=records,
        snapshots=snapshots,
        clock=FixedClock(AS_OF),
        approved_projection_digests=frozenset({digest}),
        index=index,
        embedder=EMBEDDER,
    ).run(domain_policy_id="finance/1", projection=projection)
    promoted = PromoteSnapshotUseCase(
        snapshots=snapshots,
        records=records,
        verdicts=NullPolicyVerdictStore(),
        clock=FixedClock(AS_OF),
        policies=POLICIES,
        approved_harvest_seed_digests=frozenset({digest}),
    ).run(
        snapshot_id=str(projected["snapshot_id"]),
        domain_policy_id="finance/1",
        target="production_valid",
    )
    assert promoted["state"] == "production_valid"
    gamma_flow = _load_yaml("gamma-flow.yaml")
    artifact_hash = DivergeUseCase(
        candidates=candidates,
        cards=cards,
        clock=FixedClock(AS_OF),
    ).run(candidate=gamma_flow, axiom="x", generator_run_id="gen-1")
    grounding = GroundUseCase(
        snapshots=snapshots,
        records=records,
        index=index,
        candidates=candidates,
        embedder=EMBEDDER,
    ).run(
        candidate_artifact_hash=artifact_hash,
        snapshot_id=str(projected["snapshot_id"]),
        corpus_version=int(projected["corpus_version"]),
        snapshot_state="production_valid",
    )
    evidence = grounding["evidence"]
    assert evidence is not None
    assert grounding["measurement_stamp"] == {
        "embedding_model_id": "test-only-sha256",
        "embedding_model_version": "v1",
        "embedding_dimension": 8,
        "normalization_policy": "l2",
        "distance_metric": "cosine_distance",
        "algorithm_contract_version": "1.1",
    }
    nov = novelty_term(
        evidence=float(evidence),
        snapshot_state="production_valid",
        grounding_class=grounding["grounding_class"],
    )
    assert nov >= 1
    scored = ScoreUseCase(
        candidates=candidates,
        cards=cards,
        snapshots=snapshots,
        records=records,
    ).run(
        candidate_artifact_hash=artifact_hash,
        evaluator_run_id="eval-1",
        snapshot_id=str(projected["snapshot_id"]),
        corpus_version=int(projected["corpus_version"]),
        snapshot_state="production_valid",
    )
    assert scored["nov"] == apply_novelty_threshold(nov, evidence=float(evidence))
    stored_artifact = candidates.get_artifact(artifact_hash)
    assert stored_artifact is not None
    assert stored_artifact["novelty"]["measurement_stamp"] == grounding["measurement_stamp"]
    assert stored_artifact["novelty"]["tau"] == 0.45
    assert stored_artifact["novelty"]["tau_semantics"] == "approved_default_tunable"
    assert scored["tau"] == 0.45
    mechanism_free = _load_yaml("mechanism-free.yaml")
    assert score_mech(mechanism_free, domain_pack="finance/1") == 0


def test_project_indexes_every_record_in_latest_snapshot() -> None:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    index = NullCorpusIndex()
    projections = [_load_yaml("paper-a.yaml"), _load_yaml("gamma-fragility.yaml")]
    digests = frozenset(canonical_reviewed_projection_digest(row) for row in projections)
    project = ProjectPaperUseCase(
        harvest=NullHarvestStore(records, snapshots),
        records=records,
        snapshots=snapshots,
        clock=FixedClock(AS_OF),
        approved_projection_digests=digests,
        index=index,
        embedder=EMBEDDER,
    )

    first = project.run(domain_policy_id="optimization/1", projection=projections[0])
    second = project.run(domain_policy_id="finance/1", projection=projections[1])

    hits = index.query(
        str(second["snapshot_id"]),
        EMBEDDER.embed("stochastic optimization and dealer gamma"),
        k=5,
    )
    assert {hit.record_id for hit in hits} == {
        str(first["record_id"]),
        str(second["record_id"]),
    }


def test_index_paraphrases_skips_incomplete_rows() -> None:
    index = NullCorpusIndex()
    _index_paraphrases(
        index,
        EMBEDDER,
        snapshot_id="snap",
        records=[{}, {"record_id": "r1", "paraphrase": "  "}],
    )
    assert index.query("snap", EMBEDDER.embed("anything"), k=1) == []
