from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.ports import LLMResponse
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
        return type(
            "Result",
            (),
            {"ok": True, "markdown": "content", "error_code": None, "error_message": None},
        )()

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
        return LLMResponse(text="analysis", tokens_in=1, tokens_out=1, cost_usd=0.0)


def _context(tmp_path: Path, db: PiccoloDatabase) -> HandlerContext:
    return HandlerContext(
        paper_store=PiccoloPaperStore(),
        job_queue=PiccoloJobQueue(),
        blob_store=FileSystemBlobStore(tmp_path / "blobs"),
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=PiccoloPromptStore(),
        profile_store=PiccoloProfileStore(),
        analysis_store=PiccoloAnalysisRunStore(),
    )


def test_job_logging_includes_context_fields(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = PiccoloDatabase(tmp_path / "db.sqlite")
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
    pdf_path.write_bytes(b"fake pdf")

    queue = PiccoloJobQueue()
    queue.enqueue("download", "paper", None, {"source_path": str(pdf_path)})

    ctx = _context(tmp_path, db)
    runner = JobRunner(job_queue=queue, context=ctx)

    caplog.set_level(logging.INFO, logger="papers.job_runner")
    runner.run_next(datetime.now(UTC))

    records = [record for record in caplog.records if record.name == "papers.job_runner"]
    assert records

    started = next(
        (record for record in records if getattr(record, "status_to", None) == "running"),
        None,
    )
    finished = next(
        (record for record in records if getattr(record, "status_to", None) == "succeeded"),
        None,
    )

    assert started is not None
    assert finished is not None

    first = cast(logging.LogRecord, records[0])
    for record in (started, finished):
        typed = cast(logging.LogRecord, record)
        assert getattr(typed, "job_id") == getattr(first, "job_id")
        assert getattr(typed, "job_type") == "download"
        assert getattr(typed, "paper_id") == "paper"
        assert getattr(typed, "run_id") is None
        assert getattr(typed, "status_from") is not None
        assert getattr(typed, "status_to") is not None
        assert getattr(typed, "timestamp")
