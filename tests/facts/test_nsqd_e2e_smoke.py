from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nsqd.app.use_cases import empty_smoke_snapshot_id
from nsqd.domain.policy import FINANCE_POLICY, archive_cell_key
from nsqd.harvest import run_harvest
from nsqd.infra.piccolo.stores import PiccoloFrontierCardStore, PiccoloNsqdJobQueue
from nsqd.skeleton import run_skeleton
from papers.infra.piccolo.database import PiccoloDatabase

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"
AXIOM = "predictors assume stationary return signal"
AS_OF = datetime(2024, 1, 1, tzinfo=UTC)


def test_smoke_loop_rejects_cards_and_leaves_production_archive_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    index_path = tmp_path / "corpus.lancedb"
    results = []
    for name in ("gamma-flow.yaml", "mechanism-free.yaml"):
        result = run_skeleton(
            fixture_path=FIXTURES / name,
            axiom=AXIOM,
            db_path=db_path,
            index_path=index_path,
            as_of=AS_OF,
        )
        results.append(result)
        assert result["snapshot_id"] == empty_smoke_snapshot_id()
        assert result["snapshot_empty"] is True
        assert result["evidence"] is None
        assert result["nov"] == 0
        assert result["viability"] == 0
        assert result["card"]["card_decision"] == "rejected"
        assert result["card"]["missing_fields"] == []
        assert result["archive"]["inserted"] is False
        assert result["elite"] is None
        assert result["archive_empty"] is True
        assert result["cell_status"] == "Unknown"
        assert result["grounding"]["grounding_class"] == "unevaluated"
        assert [layer["layer"] for layer in result["grounding"]["layers"]] == [1, 2, 3, 4]
        assert result["novelty"]["evidence"] is None
        assert result["novelty"]["term"] == 0
        assert result["novelty"]["measurement_stamp"] == {
            "embedding_model_id": "none",
            "embedding_model_version": "none",
            "normalization_policy": "none",
            "distance_metric": "cosine_distance",
            "algorithm_contract_version": "1.1",
        }
        assert set(result["job_types"]) == {"diverge", "ground", "score"}
        assert result["expected_outcomes"]["archive_eligible"] is False

    assert results[0]["card"]["mech"] == 5
    assert results[1]["card"]["mech"] == 0
    assert results[0]["snapshot_id"] == results[1]["snapshot_id"]


def test_smoke_loop_reports_global_archive_when_unrelated_elite_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    index_path = tmp_path / "corpus.lancedb"
    database = PiccoloDatabase(db_path)
    database.initialize_schema()
    cards = PiccoloFrontierCardStore(database)
    cell_id = sorted(FINANCE_POLICY.universe())[0]
    scoped_cell_id = archive_cell_key(domain_policy_id="finance/1", cell_id=cell_id)
    cards.put_card(
        {
            "card_id": "existing-elite",
            "domain_policy_id": "finance/1",
            "cell_id": cell_id,
            "archive_cell_key": scoped_cell_id,
            "viability": 1,
        }
    )
    cards.set_elite(scoped_cell_id, "existing-elite")

    result = run_skeleton(
        fixture_path=FIXTURES / "gamma-flow.yaml",
        axiom=AXIOM,
        db_path=db_path,
        index_path=index_path,
        as_of=AS_OF,
    )

    assert result["card"]["card_decision"] == "rejected"
    assert result["archive"]["inserted"] is False
    assert result["elite"] is None
    assert result["archive_empty"] is False


def test_smoke_loop_leaves_preseeded_stale_job_queued(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.sqlite"
    index_path = tmp_path / "corpus.lancedb"
    database = PiccoloDatabase(db_path)
    database.initialize_schema()
    queue = PiccoloNsqdJobQueue(database)
    stale_job_id = queue.enqueue("harvest", {"seeded": True})

    result = run_skeleton(
        fixture_path=FIXTURES / "gamma-flow.yaml",
        axiom=AXIOM,
        db_path=db_path,
        index_path=index_path,
        as_of=AS_OF,
    )

    stale_row = database.fetchone(
        "SELECT status, attempts FROM nsqd_jobs WHERE job_id = ?",
        [stale_job_id],
    )
    assert stale_row is not None
    assert stale_row["status"] == "queued"
    assert stale_row["attempts"] == 0
    assert set(result["job_types"]) == {"diverge", "ground", "score"}


def test_smoke_loop_uses_authoritative_snapshot_version_on_reused_database(tmp_path: Path) -> None:
    db_path = tmp_path / "reused.sqlite"
    index_path = tmp_path / "corpus.lancedb"
    harvest_path = tmp_path / "records.yaml"
    harvest_path.write_text(
        "records:\n"
        "  - type: paper\n"
        "    domain_policy_id: finance/1\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n",
        encoding="utf-8",
    )
    harvested = run_harvest(
        file_path=harvest_path,
        db_path=db_path,
        index_path=index_path,
        as_of=AS_OF,
    )
    assert harvested["corpus_version"] == 1

    result = run_skeleton(
        fixture_path=FIXTURES / "gamma-flow.yaml",
        axiom=AXIOM,
        db_path=db_path,
        index_path=index_path,
        as_of=AS_OF,
    )

    assert result["card"]["corpus_version"] == 2
    assert result["grounding"]["corpus_version"] == 2
