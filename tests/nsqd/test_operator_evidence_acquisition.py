from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

import nsqd.infra.research_runtime as research_runtime
from nsqd.app.use_cases import AcquireCorpusUseCase, ProjectPaperUseCase, PromoteSnapshotUseCase
from nsqd.composition import NsqdContainer, build_container
from nsqd.domain.acquisition import acquisition_route
from nsqd.domain.policy import FINANCE_POLICY
from nsqd.infra.research_runtime import ResearchRuntimePaths
from nsqd.null_adapters import FixedClock
from papers.config.settings import DataPaths
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex
from papers.infra.piccolo.database import PiccoloDatabase
from tests.nsqd.operator_evidence_acquisition_support import (
    RecordingExternalAdapter,
    tree_manifest,
)

AS_OF = datetime(2026, 9, 9, tzinfo=UTC)
WRITABLE_FIELDS = (
    "root",
    "db_path",
    "blobs_dir",
    "blobs_pdf_dir",
    "blobs_md_dir",
    "blobs_analysis_dir",
    "lancedb_dir",
    "nsqd_db_path",
    "nsqd_index_path",
)


def _data_paths(storage_root: Path) -> DataPaths:
    papers_root = storage_root / "papers"
    blobs = papers_root / "blobs"
    return DataPaths(
        root=papers_root,
        db_path=papers_root / "papers.sqlite",
        blobs_dir=blobs,
        blobs_pdf_dir=blobs / "pdf",
        blobs_md_dir=blobs / "md",
        blobs_analysis_dir=blobs / "analysis",
        lancedb_dir=papers_root / "index",
    )


def _runtime_paths(production_root: Path, research_root: Path) -> ResearchRuntimePaths:
    return ResearchRuntimePaths(
        production_root=production_root,
        research_root=research_root,
        papers=_data_paths(research_root),
        nsqd_db_path=research_root / "nsqd" / "nsqd.sqlite",
        nsqd_index_path=research_root / "nsqd" / "index",
    )


def _initialize_production_papers_storage(paths: DataPaths) -> FileSystemBlobStore:
    paths.root.mkdir(parents=True)
    PiccoloDatabase(paths.db_path, bind_on_init=False).initialize_schema()
    blob_store = FileSystemBlobStore(paths.blobs_dir)
    LanceDBVectorIndex(LanceDBConfig(path=paths.lancedb_dir))
    return blob_store


def _real_use_case(container: NsqdContainer) -> AcquireCorpusUseCase:
    ctx = container.ctx
    assert ctx.cycles is not None
    assert ctx.verdicts is not None
    assert ctx.bridge is not None
    return AcquireCorpusUseCase(
        cycles=ctx.cycles,
        promote=PromoteSnapshotUseCase(
            snapshots=ctx.snapshots,
            records=ctx.records,
            verdicts=ctx.verdicts,
            clock=ctx.clock,
            policies=ctx.policies,
            approved_harvest_seed_digests=ctx.approved_projection_digests,
        ),
        bridge=ctx.bridge,
        project=ProjectPaperUseCase(
            harvest=ctx.harvest,
            records=ctx.records,
            snapshots=ctx.snapshots,
            clock=ctx.clock,
            approved_projection_digests=ctx.approved_projection_digests,
            index=ctx.index,
            embedder=ctx.embedder,
        ),
    )


def _create_production_sentinels(root: Path) -> None:
    papers = _data_paths(root)
    blob_store = _initialize_production_papers_storage(papers)
    blob_store.put_markdown("production-paper", "immutable production markdown")
    build_container(
        db_path=root / "nsqd" / "nsqd.sqlite",
        index_path=root / "nsqd" / "index",
        clock=FixedClock(AS_OF),
    )
    (papers.lancedb_dir / "production-index.sentinel").write_bytes(b"papers-index")
    (root / "nsqd" / "index" / "production-index.sentinel").write_bytes(b"nsqd-index")


def _block_research_constructors(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Mock, ...]:
    constructors = tuple(
        Mock(side_effect=AssertionError(f"unexpected construction: {name}"))
        for name in (
            "PiccoloDatabase",
            "FileSystemBlobStore",
            "LanceDBVectorIndex",
            "build_nsqd_container",
        )
    )
    for name, constructor in zip(
        (
            "PiccoloDatabase",
            "FileSystemBlobStore",
            "LanceDBVectorIndex",
            "build_nsqd_container",
        ),
        constructors,
        strict=True,
    ):
        monkeypatch.setattr(research_runtime, name, constructor)
    return constructors


def test_real_use_case_owns_bounds_deduplication_and_storage_isolation(tmp_path: Path) -> None:
    production_root = tmp_path / "production"
    research_root = tmp_path / "research"
    _create_production_sentinels(production_root)
    production_before = tree_manifest(production_root)
    paths = _runtime_paths(production_root, research_root)
    bridges: list[RecordingExternalAdapter] = []

    def make_bridge(blob_store: FileSystemBlobStore) -> RecordingExternalAdapter:
        bridge = RecordingExternalAdapter(blob_store)
        bridges.append(bridge)
        return bridge

    runtime = research_runtime.compose_research_runtime(
        paths,
        make_bridge,
        FixedClock(AS_OF),
    )
    (bridge,) = bridges
    container = runtime.nsqd
    policy = replace(
        FINANCE_POLICY,
        expected_cells=frozenset({"mechanism=flow-driven|target=drawdown|horizon=intraday"}),
        recall_probes=(("missing", "doi:10.1/missing", "paper"),),
    )
    container.ctx.policies = {policy.policy_id: policy}
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1

    result = _real_use_case(container).run(
        snapshot_id="snap", domain_policy_id="finance/1", target="calibration"
    )

    assert bridge.discover_calls == 3
    assert bridge.discovered_batch_sizes == [25, 25, 25]
    assert bridge.shortlist_candidate_counts == [25, 1, 1]
    assert max(bridge.shortlist_limits) <= 3
    assert bridge.staged_source_ids == ["work-00", "work-25", "work-26"]
    assert len(bridge.staged_source_ids) == 3
    assert result["batches"] == 3
    assert result["staged_identities"] == [
        "source_paper_id:work-00",
        "source_paper_id:work-25",
        "source_paper_id:work-26",
    ]
    assert result["stopped"] == "pending_human_approval"
    assert result["projected"] is False
    assert all(draft["review_status"] == "pending" for draft in result["drafts"])
    assert container.ctx.records.list_ids() == []
    assert all(path.exists() for path in runtime.paths.writable_paths)
    assert tree_manifest(production_root) == production_before


@pytest.mark.parametrize("relationship", ["equal", "beneath", "ancestor"])
def test_research_boundary_rejects_root_overlap_before_store_creation(
    tmp_path: Path, relationship: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    production_root = tmp_path / "production"
    production_root.mkdir()
    (production_root / "sentinel").write_bytes(b"production")
    research_root = {
        "equal": production_root,
        "beneath": production_root / "research",
        "ancestor": tmp_path,
    }[relationship]
    paths = ResearchRuntimePaths.model_construct(
        production_root=production_root,
        research_root=research_root,
        papers=_data_paths(research_root),
        nsqd_db_path=research_root / "nsqd" / "nsqd.sqlite",
        nsqd_index_path=research_root / "nsqd" / "index",
    )
    constructors = _block_research_constructors(monkeypatch)

    with pytest.raises(ValidationError, match="overlaps the production root"):
        research_runtime.compose_research_runtime(paths, Mock(), FixedClock(AS_OF))

    for constructor in constructors:
        constructor.assert_not_called()


@pytest.mark.parametrize("field", WRITABLE_FIELDS)
def test_research_boundary_validates_every_writable_path(tmp_path: Path, field: str) -> None:
    production_root = tmp_path / "production"
    research_root = tmp_path / "research"
    papers = _data_paths(research_root)
    values = {
        "production_root": production_root,
        "research_root": research_root,
        "papers": papers,
        "nsqd_db_path": research_root / "nsqd" / "nsqd.sqlite",
        "nsqd_index_path": research_root / "nsqd" / "index",
    }
    if field in DataPaths.model_fields:
        values["papers"] = papers.model_copy(update={field: production_root / field})
    else:
        values[field] = production_root / field

    with pytest.raises(ValidationError, match="research writable path"):
        ResearchRuntimePaths.model_validate(values)

    assert not production_root.exists()


def test_research_composer_revalidates_mutated_nested_paths_before_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    production_root = tmp_path / "production"
    paths = _runtime_paths(production_root, tmp_path / "research")
    paths.papers.db_path = production_root / "papers.sqlite"
    constructors = _block_research_constructors(monkeypatch)

    with pytest.raises(ValidationError, match="research writable path"):
        research_runtime.compose_research_runtime(paths, Mock(), FixedClock(AS_OF))

    for constructor in constructors:
        constructor.assert_not_called()


def test_recording_adapter_does_not_enforce_production_limits(tmp_path: Path) -> None:
    bridge = RecordingExternalAdapter(FileSystemBlobStore(tmp_path / "blobs"))
    for _ in range(4):
        bridge.discover("query", {"type": "paper"})
    for version in ("v1", "v2", "v3", "v4"):
        bridge.stage_import(bridge.pages[0][0] | {"version_id": version})
    assert bridge.discover_calls == 4
    assert len(bridge.staged_source_ids) == 4
    assert len(set(bridge.staged_source_ids)) == 1


def test_f_evaluation_insufficiency_is_not_an_alg_suf_acquisition_failure() -> None:
    assert acquisition_route(("fewer_than_five_eligible_source_groups",)) == "stop"
