from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from nsqd.composition import NsqdContainer
from nsqd.composition import build_container as build_nsqd_container
from nsqd.ports import Clock, PaperAcquisitionBridge
from papers.config.settings import DataPaths
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex
from papers.infra.piccolo.database import PiccoloDatabase


@dataclass(frozen=True, slots=True)
class ResearchStorageError(ValueError):
    reason: str
    path: Path | None = None

    def __str__(self) -> str:
        return self.reason if self.path is None else f"{self.reason}: {self.path}"


class ResearchRuntimePaths(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    production_root: Path
    research_root: Path
    papers: DataPaths
    nsqd_db_path: Path
    nsqd_index_path: Path

    @property
    def writable_paths(self) -> tuple[Path, ...]:
        return (
            self.papers.root,
            self.papers.db_path,
            self.papers.blobs_dir,
            self.papers.blobs_pdf_dir,
            self.papers.blobs_md_dir,
            self.papers.blobs_analysis_dir,
            self.papers.lancedb_dir,
            self.nsqd_db_path,
            self.nsqd_index_path,
        )

    @model_validator(mode="after")
    def require_isolated_storage(self) -> Self:
        production_root = self.production_root.resolve()
        research_root = self.research_root.resolve()
        if _paths_overlap(production_root, research_root):
            raise ResearchStorageError("research root overlaps the production root")
        for path in self.writable_paths:
            resolved = path.resolve()
            if not resolved.is_relative_to(research_root):
                raise ResearchStorageError(
                    "research writable path is outside the research root", resolved
                )
        return self


@dataclass(frozen=True, slots=True)
class ResearchPaperPaths:
    root: Path
    db_path: Path
    blobs_dir: Path
    blobs_pdf_dir: Path
    blobs_md_dir: Path
    blobs_analysis_dir: Path
    lancedb_dir: Path


@dataclass(frozen=True, slots=True)
class ResearchRuntimeSnapshot:
    production_root: Path
    research_root: Path
    papers: ResearchPaperPaths
    nsqd_db_path: Path
    nsqd_index_path: Path

    @classmethod
    def capture(cls, source: ResearchRuntimePaths) -> Self:
        papers = source.papers
        validated = ResearchRuntimePaths.model_validate(
            {
                "production_root": source.production_root.resolve(),
                "research_root": source.research_root.resolve(),
                "papers": {
                    "root": papers.root.resolve(),
                    "db_path": papers.db_path.resolve(),
                    "blobs_dir": papers.blobs_dir.resolve(),
                    "blobs_pdf_dir": papers.blobs_pdf_dir.resolve(),
                    "blobs_md_dir": papers.blobs_md_dir.resolve(),
                    "blobs_analysis_dir": papers.blobs_analysis_dir.resolve(),
                    "lancedb_dir": papers.lancedb_dir.resolve(),
                },
                "nsqd_db_path": source.nsqd_db_path.resolve(),
                "nsqd_index_path": source.nsqd_index_path.resolve(),
            }
        )
        canonical = validated.papers
        return cls(
            production_root=validated.production_root,
            research_root=validated.research_root,
            papers=ResearchPaperPaths(
                root=canonical.root,
                db_path=canonical.db_path,
                blobs_dir=canonical.blobs_dir,
                blobs_pdf_dir=canonical.blobs_pdf_dir,
                blobs_md_dir=canonical.blobs_md_dir,
                blobs_analysis_dir=canonical.blobs_analysis_dir,
                lancedb_dir=canonical.lancedb_dir,
            ),
            nsqd_db_path=validated.nsqd_db_path,
            nsqd_index_path=validated.nsqd_index_path,
        )

    @property
    def writable_paths(self) -> tuple[Path, ...]:
        return (
            self.papers.root,
            self.papers.db_path,
            self.papers.blobs_dir,
            self.papers.blobs_pdf_dir,
            self.papers.blobs_md_dir,
            self.papers.blobs_analysis_dir,
            self.papers.lancedb_dir,
            self.nsqd_db_path,
            self.nsqd_index_path,
        )


@dataclass(frozen=True, slots=True)
class ResearchRuntime:
    paths: ResearchRuntimeSnapshot
    papers_database: PiccoloDatabase
    paper_blobs: FileSystemBlobStore
    paper_index: LanceDBVectorIndex
    paper_bridge: PaperAcquisitionBridge
    nsqd: NsqdContainer


def compose_research_runtime(
    paths: ResearchRuntimePaths,
    paper_bridge_factory: Callable[[FileSystemBlobStore], PaperAcquisitionBridge],
    clock: Clock,
) -> ResearchRuntime:
    snapshot = ResearchRuntimeSnapshot.capture(paths)
    papers_root = snapshot.papers.root
    papers_db_path = snapshot.papers.db_path
    blobs_dir = snapshot.papers.blobs_dir
    paper_index_path = snapshot.papers.lancedb_dir
    nsqd_db_path = snapshot.nsqd_db_path
    nsqd_index_path = snapshot.nsqd_index_path

    papers_root.mkdir(parents=True, exist_ok=True)
    papers_database = PiccoloDatabase(papers_db_path, bind_on_init=False)
    papers_database.initialize_schema()
    paper_blobs = FileSystemBlobStore(blobs_dir)
    paper_index = LanceDBVectorIndex(LanceDBConfig(path=paper_index_path))
    paper_bridge = paper_bridge_factory(paper_blobs)
    nsqd = build_nsqd_container(
        db_path=nsqd_db_path,
        index_path=nsqd_index_path,
        clock=clock,
        paper_bridge=paper_bridge,
    )
    return ResearchRuntime(
        paths=snapshot,
        papers_database=papers_database,
        paper_blobs=paper_blobs,
        paper_index=paper_index,
        paper_bridge=paper_bridge,
        nsqd=nsqd,
    )


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)
