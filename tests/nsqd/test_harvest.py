from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

import nsqd.harvest as harvest_module
import nsqd.runner as runner_module
from nsqd.app.use_cases import HarvestUseCase
from nsqd.domain.harvest import (
    HarvestRejected,
    harvest_record_rejection,
    harvest_records_from_payload,
    is_essay_payload,
)
from nsqd.domain.status import record_lifecycle
from nsqd.harvest import parse_harvest_file, run_harvest
from nsqd.infra.piccolo.stores import PiccoloNsqdJobQueue
from nsqd.null_adapters import (
    FixedClock,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullHarvestStore,
)
from papers.infra.piccolo.database import PiccoloDatabase

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
KNOWN = {
    "type": "paper",
    "paraphrase": "Condition allocation trust on dealer-hedging convexity regime.",
    "source": "doi:10.0000/example",
    "domain_policy_id": "finance/1",
}


def test_essay_payloads_are_detected() -> None:
    assert is_essay_payload("In this essay I survey the literature without citations.")
    assert is_essay_payload({"kind": "essay", "body": "prose"})
    assert is_essay_payload({"title": "A think piece", "body": "no sources"})
    assert not is_essay_payload(
        {
            "type": "paper",
            "paraphrase": "Condition allocation trust on dealer-hedging convexity regime.",
            "source": "doi:10.0000/example",
            "domain_policy_id": "finance/1",
        }
    )


def test_sourceless_and_empty_paraphrase_are_rejected() -> None:
    assert (
        harvest_record_rejection(
            {"type": "paper", "paraphrase": "x", "source": "", "domain_policy_id": "finance/1"}
        )
        == "sourceless"
    )
    assert (
        harvest_record_rejection(
            {
                "type": "paper",
                "paraphrase": "  ",
                "source": "doi:1",
                "domain_policy_id": "finance/1",
            }
        )
        == "empty paraphrase"
    )
    assert (
        harvest_record_rejection(
            {
                "kind": "candidate-requirement-card",
                "type": "paper",
                "paraphrase": "x",
                "source": "s",
                "domain_policy_id": "finance/1",
            }
        )
        == "requirement-card is not a corpus record"
    )


def test_enumerated_known_vector_is_accepted() -> None:
    records = harvest_records_from_payload(
        {
            "records": [
                {
                    "type": "paper",
                    "paraphrase": "Condition allocation trust on dealer-hedging convexity regime.",
                    "source": "doi:10.0000/example",
                    "domain_policy_id": "finance/1",
                }
            ]
        }
    )
    assert len(records) == 1


def test_essay_payload_raises() -> None:
    with pytest.raises(HarvestRejected, match="essay-only"):
        harvest_records_from_payload("An essay with no enumerated citations.")


@pytest.mark.parametrize("field", ["type", "paraphrase", "source"])
@pytest.mark.parametrize("value", [1, [], {}])
def test_required_record_fields_must_be_strings(field: str, value: object) -> None:
    record = {**KNOWN, field: value}
    assert harvest_record_rejection(record) == f"{field} must be a string"


def test_toml_harvest_file_parses_enumerated_records(tmp_path: Path) -> None:
    path = tmp_path / "harvest-seed.toml"
    path.write_text(
        "[[records]]\n"
        'type = "paper"\n'
        'paraphrase = "A mechanism"\n'
        'source = "doi:10.1/x"\n'
        'domain_policy_id = "finance/1"\n',
        encoding="utf-8",
    )
    assert parse_harvest_file(path) == {
        "records": [
            {
                "type": "paper",
                "paraphrase": "A mechanism",
                "source": "doi:10.1/x",
                "domain_policy_id": "finance/1",
            }
        ]
    }


def test_harvest_file_size_is_bounded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "records.yaml"
    path.write_text("records: []\n", encoding="utf-8")
    monkeypatch.setattr(harvest_module, "MAX_HARVEST_FILE_BYTES", 1)
    with pytest.raises(ValueError, match="too large"):
        parse_harvest_file(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("coordinates", [], "coordinates must be a mapping"),
        ("provenance", [], "provenance must be a mapping"),
        ("tags", "reviewed", "tags must be a list of strings"),
        ("aliases", [1], "aliases must be a list of strings"),
        ("retracted", "false", "retracted must be a boolean"),
        ("invalid_reason", 1, "invalid_reason must be a string"),
    ],
)
def test_optional_metadata_schema_is_validated(field: str, value: object, message: str) -> None:
    assert harvest_record_rejection({**KNOWN, field: value}) == message


def test_harvest_rejects_missing_and_unknown_domain_policy_id() -> None:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    use_case = HarvestUseCase(harvest=NullHarvestStore(records, snapshots), clock=FixedClock(AS_OF))

    with pytest.raises(HarvestRejected, match="domain_policy_id is required"):
        use_case.run(
            {
                "records": [
                    {
                        "type": "paper",
                        "paraphrase": "A mechanism",
                        "source": "doi:10.1/x",
                    }
                ]
            }
        )

    with pytest.raises(HarvestRejected, match="unknown domain_policy_id"):
        use_case.run(
            {
                "records": [
                    {
                        "type": "paper",
                        "paraphrase": "A mechanism",
                        "source": "doi:10.1/x",
                        "domain_policy_id": "missing/1",
                    }
                ]
            }
        )


def test_harvest_commits_versioned_snapshot_and_preserves_metadata() -> None:
    records = NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    use_case = HarvestUseCase(harvest=NullHarvestStore(records, snapshots), clock=FixedClock(AS_OF))
    result = use_case.run(
        {
            "records": [
                {
                    **KNOWN,
                    "coordinates": {"mechanism": "dealer hedging"},
                    "provenance": {"reviewer": "human-1"},
                    "tags": ["reviewed"],
                    "aliases": ["doi:10.0000/EXAMPLE"],
                    "retracted": False,
                    "ignored": "not persisted",
                }
            ]
        }
    )

    record_id = result["record_ids"][0]
    stored = records.get(record_id)
    assert stored is not None
    assert stored["coordinates"] == {"mechanism": "dealer hedging"}
    assert stored["provenance"] == {"reviewer": "human-1"}
    assert stored["tags"] == ["reviewed"]
    assert stored["aliases"] == ["doi:10.0000/EXAMPLE"]
    assert stored["retracted"] is False
    assert stored["domain_policy_id"] == "finance/1"
    assert "ignored" not in stored
    assert record_lifecycle(stored, as_of=AS_OF) == "current"
    assert result["corpus_version"] == 1
    assert snapshots.record_ids(result["snapshot_id"]) == [record_id]

    repeated = use_case.run({"records": [KNOWN]})
    assert repeated["snapshot_id"] == result["snapshot_id"]
    assert repeated["corpus_version"] == 1

    advanced = use_case.run(
        {
            "records": [
                {
                    "type": "code",
                    "paraphrase": "A second mechanism",
                    "source": "https://example.com/code",
                    "domain_policy_id": "finance/1",
                }
            ]
        }
    )
    assert advanced["snapshot_id"] != result["snapshot_id"]
    assert advanced["corpus_version"] == 2


def test_reharvest_preserves_omitted_metadata_and_rejects_conflicts(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    first = tmp_path / "first.yaml"
    first.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: finance/1\n"
        "    tags: [reviewed]\n",
        encoding="utf-8",
    )
    omitted = tmp_path / "omitted.yaml"
    omitted.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: finance/1\n",
        encoding="utf-8",
    )
    conflicting = tmp_path / "conflicting.yaml"
    conflicting.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: finance/1\n"
        "    tags: [unreviewed]\n",
        encoding="utf-8",
    )

    initial = run_harvest(
        file_path=first, db_path=db_path, index_path=tmp_path / "idx", as_of=AS_OF
    )
    repeated = run_harvest(
        file_path=omitted,
        db_path=db_path,
        index_path=tmp_path / "idx",
        as_of=AS_OF,
    )
    with pytest.raises(HarvestRejected, match="immutable metadata"):
        run_harvest(
            file_path=conflicting,
            db_path=db_path,
            index_path=tmp_path / "idx",
            as_of=AS_OF,
        )

    assert repeated["snapshot_id"] == initial["snapshot_id"]
    assert repeated["corpus_version"] == initial["corpus_version"]
    database = PiccoloDatabase(db_path)
    row = database.fetchone("SELECT payload_json FROM nsqd_corpus_records")
    assert row is not None
    payload = json.loads(str(row["payload_json"]))
    assert payload["tags"] == ["reviewed"]
    assert payload["domain_policy_id"] == "finance/1"


def test_reharvest_rejects_cross_policy_conflicts(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    first = tmp_path / "first.yaml"
    first.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: finance/1\n",
        encoding="utf-8",
    )
    conflicting = tmp_path / "conflicting.yaml"
    conflicting.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: optimization/1\n",
        encoding="utf-8",
    )

    run_harvest(file_path=first, db_path=db_path, index_path=tmp_path / "idx", as_of=AS_OF)
    with pytest.raises(HarvestRejected, match="immutable metadata conflict: domain_policy_id"):
        run_harvest(
            file_path=conflicting,
            db_path=db_path,
            index_path=tmp_path / "idx",
            as_of=AS_OF,
        )


def test_concurrent_identical_harvests_share_one_snapshot_version(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    PiccoloDatabase(db_path).initialize_schema()
    path = tmp_path / "records.yaml"
    path.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: finance/1\n",
        encoding="utf-8",
    )

    def harvest(index: int) -> dict[str, object]:
        return run_harvest(
            file_path=path,
            db_path=db_path,
            index_path=tmp_path / f"idx-{index}",
            as_of=AS_OF,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(harvest, range(2)))

    assert {result["snapshot_id"] for result in results} == {results[0]["snapshot_id"]}
    assert {result["corpus_version"] for result in results} == {1}


def test_concurrent_distinct_harvests_commit_serial_versions(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    PiccoloDatabase(db_path).initialize_schema()
    paths = []
    for index in range(2):
        path = tmp_path / f"records-{index}.yaml"
        path.write_text(
            "records:\n"
            f"  - type: paper\n    paraphrase: Mechanism {index}\n"
            f"    source: doi:10.1/{index}\n"
            "    domain_policy_id: finance/1\n",
            encoding="utf-8",
        )
        paths.append(path)

    def harvest(index: int) -> dict[str, object]:
        return run_harvest(
            file_path=paths[index],
            db_path=db_path,
            index_path=tmp_path / f"idx-{index}",
            as_of=AS_OF,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(harvest, range(2)))

    assert {result["corpus_version"] for result in results} == {1, 2}
    database = PiccoloDatabase(db_path)
    assert database.fetchone("SELECT COUNT(*) AS count FROM nsqd_corpus_records") == {"count": 2}
    assert database.fetchone("SELECT COUNT(*) AS count FROM nsqd_corpus_snapshots") == {"count": 2}


def test_run_harvest_claims_its_job_without_touching_older_work(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    database = PiccoloDatabase(db_path)
    database.initialize_schema()
    queue = PiccoloNsqdJobQueue(database)
    older_job_id = queue.enqueue("diverge", {"axiom": "older"})
    path = tmp_path / "records.yaml"
    path.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: finance/1\n",
        encoding="utf-8",
    )

    run_harvest(file_path=path, db_path=db_path, index_path=tmp_path / "idx", as_of=AS_OF)

    older = database.fetchone(
        "SELECT status, attempts FROM nsqd_jobs WHERE job_id = ?", [older_job_id]
    )
    assert older is not None
    assert older["status"] == "queued"
    assert older["attempts"] == 0


def test_run_harvest_marks_claimed_job_failed_on_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "records.yaml"
    path.write_text(
        "records:\n"
        "  - type: paper\n"
        "    paraphrase: A mechanism\n"
        "    source: doi:10.1/x\n"
        "    domain_policy_id: finance/1\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "nsqd.sqlite"

    def fail(*_: object, **__: object) -> dict[str, object]:
        raise RuntimeError("adapter failed")

    monkeypatch.setitem(runner_module._HANDLER_BY_JOB_TYPE, "harvest", fail)
    with pytest.raises(RuntimeError, match="adapter failed"):
        run_harvest(file_path=path, db_path=db_path, index_path=tmp_path / "idx", as_of=AS_OF)

    database = PiccoloDatabase(db_path)
    row = database.fetchone(
        "SELECT status, last_error FROM nsqd_jobs ORDER BY created_at DESC LIMIT 1"
    )
    assert row is not None
    assert row["status"] == "failed"
    assert row["last_error"] == "adapter failed"
