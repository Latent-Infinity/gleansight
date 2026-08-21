from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from papers.app.job_runner import HandlerContext, JobRunner
from papers.domain.models import PipelineHealth, PipelineStage
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloJobQueue,
    PiccoloPaperStore,
    PiccoloProfileStore,
    PiccoloPromptStore,
)


class _VectorIndex:
    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        return None

    def query(self, embedding: list[float], limit: int):
        return []


class _Converter:
    def pdf_to_markdown(self, pdf_path: Path):
        raise AssertionError("download job must not convert")

    def version(self) -> str:
        return "1.0"


class _Embedder:
    def model_name(self) -> str:
        return "model"

    def dimension(self) -> int:
        return 3

    def embed(self, text: str) -> list[float]:
        return [1.0, 2.0, 3.0]


class _LLM:
    def complete(self, *, prompt: str, profile: dict, model: str, timeout_s: int | None = None):
        raise AssertionError("should not be called")


def test_job_transition_log_includes_required_fields(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = PiccoloDatabase(tmp_path / "log.sqlite")
    db.initialize_schema()
    paper_store = PiccoloPaperStore()
    now = datetime.now(UTC).isoformat()
    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": now,
            "updated_at": now,
        }
    )
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    queue = PiccoloJobQueue()
    queue.enqueue("download", "paper", None, {"source_path": str(pdf_path)})
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=queue,
        blob_store=FileSystemBlobStore(tmp_path / "blobs"),
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=PiccoloPromptStore(),
        profile_store=PiccoloProfileStore(),
        analysis_store=PiccoloAnalysisRunStore(),
    )
    runner = JobRunner(job_queue=queue, context=ctx)
    caplog.set_level(logging.INFO, logger="papers.job_runner")
    runner.run_next(datetime.now(UTC))

    records = [record for record in caplog.records if record.name == "papers.job_runner"]
    assert records
    required = ("timestamp", "job_id", "job_type", "status_from", "status_to", "paper_id", "run_id")
    for record in records:
        typed = cast(logging.LogRecord, record)
        for field_name in required:
            assert hasattr(typed, field_name), field_name
            assert getattr(typed, field_name) is not None or field_name == "run_id"
    started = next(
        record
        for record in records
        if getattr(record, "job_type", None) == "download"
        and getattr(record, "status_from", None) == "queued"
        and getattr(record, "status_to", None) == "running"
    )
    typed_started = cast(logging.LogRecord, started)
    assert getattr(typed_started, "paper_id") == "paper"
    assert getattr(typed_started, "run_id") is None
