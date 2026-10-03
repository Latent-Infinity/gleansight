"""Local API scenarios using scratch databases and deterministic embeddings."""

from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from gleansight.api.models import OperationError
from gleansight.api.nsqd import operations
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from nsqd.composition import NsqdContainer, build_container
from nsqd.null_adapters import HashParaphraseEmbedder

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/fixtures/approved/nsqd"


class ScratchRuntime(ApiRuntime):
    """Supply deterministic local composition without contacting an embedding provider."""

    def __init__(
        self, root: Path, *, approvals: bool = False, config_path: Path | None = None
    ) -> None:
        super().__init__(
            ApiConfiguration(repo_root=root, allow_approvals=approvals, config_path=config_path)
        )
        self.container = build_container(
            db_path=self.nsqd_db,
            index_path=self.nsqd_index,
            embedder=HashParaphraseEmbedder(),
            enabled_operators=frozenset(self.settings.nsqd.enabled_operators),
        )

    @property
    def nsqd(self) -> NsqdContainer:
        return self.container


def invoke(runtime: ApiRuntime, name: str, payload: dict[str, JsonValue]) -> JsonValue:
    operation = next(operation for operation in operations() if operation.name == name)
    return operation.invoke(runtime, payload)


def mapping(value: JsonValue) -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_python(value)


def test_smoke_lifecycle_and_operational_reads(tmp_path: Path) -> None:
    runtime = ScratchRuntime(tmp_path)
    result = mapping(
        invoke(
            runtime,
            "nsqd.skeleton.run",
            {
                "candidate_fixture": str(FIXTURES / "gamma-flow.yaml"),
                "axiom": "predictors assume stationary return signal",
            },
        )
    )
    assert result["archive_empty"] is True
    assert mapping(result["card"])["card_decision"] == "rejected"
    snapshot = result["snapshot_id"]
    artifact = result["candidate_artifact_hash"]
    assert mapping(invoke(runtime, "nsqd.snapshots.members", {"id": snapshot}))["record_ids"] == []
    assert (
        mapping(invoke(runtime, "nsqd.candidates.get", {"id": artifact}))["artifact_hash"]
        == artifact
    )
    mapped = mapping(
        invoke(
            runtime,
            "nsqd.snapshots.map",
            {
                "snapshot_id": snapshot,
                "domain_policy_id": "finance/1",
                "snapshot_state": "smoke_only",
            },
        )
    )
    assert len(mapping(mapped["cell_statuses"])) > 1
    ranked = mapping(
        invoke(
            runtime,
            "nsqd.archive.rank",
            {
                "snapshot_id": snapshot,
                "domain_policy_id": "finance/1",
                "snapshot_state": "smoke_only",
            },
        )
    )
    assert ranked["elites"] == []
    for resource in (
        "records",
        "snapshots",
        "candidates",
        "cards",
        "cycles",
        "jobs",
        "verdicts",
        "elites",
    ):
        page = mapping(invoke(runtime, f"nsqd.{resource}.list", {"limit": 1, "offset": 0}))
        assert len(TypeAdapter(list[JsonValue]).validate_python(page["items"])) <= 1
    jobs = mapping(invoke(runtime, "nsqd.jobs.list", {}))
    rows = TypeAdapter(list[dict[str, JsonValue]]).validate_python(jobs["items"])
    assert rows and all(row["status"] == "succeeded" for row in rows)
    canceled = mapping(invoke(runtime, "nsqd.jobs.cancel", {"id": rows[0]["job_id"]}))
    assert canceled["status"] == "succeeded"
    for action in ("export", "inventory"):
        with pytest.raises(ValueError):
            invoke(runtime, f"nsqd.tau.{action}", {"candidate_artifact_hashes": [artifact]})


def test_verified_projection_and_tampered_manifest(tmp_path: Path) -> None:
    runtime = ScratchRuntime(tmp_path)
    result = mapping(
        invoke(
            runtime,
            "nsqd.corpus.project",
            {
                "projection": str(FIXTURES / "gamma-fragility.yaml"),
                "manifest": str(FIXTURES / "manifest.toml"),
            },
        )
    )
    assert result["created"] is True
    repeated = mapping(
        invoke(
            runtime,
            "nsqd.corpus.project",
            {
                "projection": str(FIXTURES / "gamma-fragility.yaml"),
                "manifest": str(FIXTURES / "manifest.toml"),
            },
        )
    )
    assert repeated["created"] is False
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("schema_version = 1\n", encoding="utf-8")
    before = invoke(runtime, "nsqd.digests.list", {})
    with pytest.raises(ValueError):
        invoke(
            runtime,
            "nsqd.corpus.project",
            {
                "projection": str(FIXTURES / "paper-a.yaml"),
                "manifest": str(manifest),
            },
        )
    assert invoke(runtime, "nsqd.digests.list", {}) == before


def test_approval_and_input_authority(tmp_path: Path) -> None:
    runtime = ScratchRuntime(tmp_path)
    with pytest.raises(OperationError, match="approval"):
        invoke(runtime, "nsqd.digests.approve", {"digest": "a" * 64})
    assert mapping(invoke(runtime, "nsqd.digests.list", {}))["digests"] == []
    approved = ScratchRuntime(tmp_path / "approved", approvals=True)
    assert (
        mapping(invoke(approved, "nsqd.digests.approve", {"digest": "a" * 64}))["approved"] is True
    )
    base: dict[str, JsonValue] = {
        "candidate_fixture": str(FIXTURES / "gamma-flow.yaml"),
        "axiom": "stationarity",
        "snapshot_id": "absent",
        "domain_policy_id": "finance/1",
    }
    with pytest.raises(OperationError, match="not enabled"):
        invoke(runtime, "nsqd.candidates.diverge", {**base, "operator": "E"})
    for operator in ("C", "D", "F", "G"):
        with pytest.raises(ValidationError):
            invoke(runtime, "nsqd.candidates.diverge", {**base, "operator": operator})
    with pytest.raises(ValidationError):
        invoke(runtime, "nsqd.candidates.diverge", {**base, "operator": "B"})
    for payload in (
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"limit": "5"},
        {"unexpected": True},
    ):
        with pytest.raises(ValidationError):
            invoke(
                runtime,
                "nsqd.records.list",
                TypeAdapter(dict[str, JsonValue]).validate_python(payload),
            )
    with pytest.raises(OperationError, match="No nsqd_corpus_records"):
        invoke(runtime, "nsqd.records.get", {"id": "' OR 1=1 --"})
    with pytest.raises(ValidationError):
        invoke(
            runtime,
            "nsqd.corpus.acquire",
            {
                "snapshot_id": "s",
                "domain_policy_id": "finance/1",
                "approved_projections": ["draft.yaml"],
            },
        )


def test_harvest_and_cancel_queued_job(tmp_path: Path) -> None:
    runtime = ScratchRuntime(tmp_path)
    source = tmp_path / "records.yaml"
    source.write_text(
        "records:\n  - type: paper\n"
        "    paraphrase: Condition allocation trust on dealer-hedging convexity regime.\n"
        "    source: doi:10.0000/example\n    domain_policy_id: finance/1\n",
        encoding="utf-8",
    )
    result = mapping(invoke(runtime, "nsqd.corpus.harvest", {"file": str(source)}))
    assert result["record_ids"]
    queued = runtime.nsqd.queue.enqueue("map", {"snapshot_id": "absent"})
    assert mapping(invoke(runtime, "nsqd.jobs.cancel", {"id": queued}))["status"] == "canceled"
    assert mapping(invoke(runtime, "nsqd.jobs.status", {"id": queued}))["status"] == "canceled"
