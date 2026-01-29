from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from papers.app.job_runner import HandlerContext, JobRunner
from papers.app.ports import LLMResponse
from papers.app.use_cases import (
    EnqueueConvertUseCase,
    EnqueueDownloadUseCase,
    EnqueueEmbedUseCase,
    RunAnalysisUseCase,
)
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
        self.last = (paper_id, embedding)

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


def test_pipeline_happy_path(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "app.sqlite")
    db.initialize_schema()

    paper_store = PiccoloPaperStore()
    job_queue = PiccoloJobQueue()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    analysis_store = PiccoloAnalysisRunStore()

    paper_store.create_paper(
        {
            "paper_id": "paper",
            "title": "Title",
            "pipeline_stage": PipelineStage.imported,
            "pipeline_health": PipelineHealth.ok,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )

    prompt_store.create_prompt("prompt", "Prompt")
    prompt_store.create_version("pv1", "prompt", 1, "body", "markdown_only")
    profile_store.create_profile("profile", "Local", "http://localhost")

    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")

    enqueue_download = EnqueueDownloadUseCase(job_queue)
    enqueue_convert = EnqueueConvertUseCase(job_queue)
    enqueue_embed = EnqueueEmbedUseCase(job_queue)
    run_analysis = RunAnalysisUseCase(job_queue, prompt_store, profile_store, analysis_store)

    enqueue_download(paper_id="paper", source_path=str(pdf_path))
    enqueue_convert(paper_id="paper")
    enqueue_embed(paper_id="paper")
    run_analysis(
        paper_id="paper",
        prompt_id="prompt",
        prompt_version_id=None,
        profile_id="profile",
        model_name="model",
        force=True,
    )

    blob_store = FileSystemBlobStore(tmp_path / "blobs")
    ctx = HandlerContext(
        paper_store=paper_store,
        job_queue=job_queue,
        blob_store=blob_store,
        converter=_Converter(),
        embedder=_Embedder(),
        vector_index=_VectorIndex(),
        llm_client=_LLM(),
        prompt_store=prompt_store,
        profile_store=profile_store,
        analysis_store=analysis_store,
    )

    runner = JobRunner(job_queue=job_queue, context=ctx)
    while runner.run_next(datetime.now(UTC)):
        pass

    paper = paper_store.get("paper")
    assert paper is not None
    assert paper["pipeline_stage"] == PipelineStage.analyzed
