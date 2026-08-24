from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nsqd.cli import app
from nsqd.domain.harvest import HarvestRejected
from nsqd.domain.snapshot import record_content_hash
from nsqd.harvest import run_harvest
from nsqd.null_adapters import HashParaphraseEmbedder
from papers.infra.piccolo.database import PiccoloDatabase

KNOWN = {
    "type": "paper",
    "paraphrase": "Condition allocation trust on dealer-hedging convexity regime.",
    "source": "doi:10.0000/example",
    "domain_policy_id": "finance/1",
}
HASH_EMBEDDER = HashParaphraseEmbedder()


def test_essay_file_is_rejected_and_writes_no_corpus_rows(tmp_path: Path) -> None:
    essay = tmp_path / "survey.md"
    essay.write_text(
        "This essay reviews convexity without listing a source, paraphrase, or record type.\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "nsqd.sqlite"
    with pytest.raises(HarvestRejected, match="essay-only"):
        run_harvest(
            file_path=essay,
            db_path=db_path,
            index_path=tmp_path / "idx",
            embedder=HASH_EMBEDDER,
        )
    db = PiccoloDatabase(db_path)
    db.initialize_schema()
    rows = db.fetchall("SELECT record_id FROM nsqd_corpus_records")
    assert rows == []


def test_sourceless_enumerated_record_is_rejected_and_writes_no_rows(tmp_path: Path) -> None:
    path = tmp_path / "records.yaml"
    path.write_text(
        "records:\n"
        "  - type: paper\n"
        "    domain_policy_id: finance/1\n"
        "    paraphrase: A mechanism without a source\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "nsqd.sqlite"
    with pytest.raises(HarvestRejected, match="sourceless"):
        run_harvest(
            file_path=path,
            db_path=db_path,
            index_path=tmp_path / "idx",
            embedder=HASH_EMBEDDER,
        )
    db = PiccoloDatabase(db_path)
    db.initialize_schema()
    assert db.fetchall("SELECT record_id FROM nsqd_corpus_records") == []


def test_requirement_card_file_is_rejected_as_corpus(tmp_path: Path) -> None:
    fixture = (
        Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd" / "gamma-flow.yaml"
    )
    with pytest.raises(HarvestRejected, match="requirement-card"):
        run_harvest(
            file_path=fixture,
            db_path=tmp_path / "nsqd.sqlite",
            index_path=tmp_path / "idx",
            embedder=HASH_EMBEDDER,
        )


def test_enumerated_known_vector_is_harvested(tmp_path: Path) -> None:
    path = tmp_path / "records.yaml"
    path.write_text(
        "records:\n"
        "  - type: paper\n"
        "    domain_policy_id: finance/1\n"
        "    paraphrase: Condition allocation trust on dealer-hedging convexity regime.\n"
        "    source: doi:10.0000/example\n",
        encoding="utf-8",
    )
    result = run_harvest(
        file_path=path,
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "idx",
        embedder=HASH_EMBEDDER,
    )
    expected = record_content_hash(
        type=KNOWN["type"],
        paraphrase=KNOWN["paraphrase"],
        source=KNOWN["source"],
    )
    assert result["record_ids"] == [expected]
    db = PiccoloDatabase(tmp_path / "nsqd.sqlite")
    row = db.fetchone(
        "SELECT record_id FROM nsqd_corpus_records WHERE record_id = ?",
        [expected],
    )
    assert row is not None


def test_harvest_cli_rejects_essay_file(tmp_path: Path) -> None:
    essay = tmp_path / "essay.md"
    essay.write_text("Sourceless prose is not a citation list.\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "harvest",
            "--file",
            str(essay),
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "idx"),
        ],
    )
    assert result.exit_code == 1
    assert "rejected" in result.output.lower() or "rejected" in (result.stderr or "").lower()
