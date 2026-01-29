from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from papers.app import ports
from papers.app.job_runner import HandlerContext, JobRunner
from papers.config.settings import Settings
from papers.domain.errors import ConfigurationError
from papers.infra.blobs_fs.store import FileSystemBlobStore
from papers.infra.converter_docling.adapter import build_docling_converter
from papers.infra.embedder_st.adapter import build_sentence_transformer_embedder
from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex
from papers.infra.llm_openai_compat.client import build_openai_compat_client
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloJobQueue,
    PiccoloPaperStore,
    PiccoloProfileStore,
    PiccoloPromptStore,
)


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    db: PiccoloDatabase
    paper_store: PiccoloPaperStore
    job_queue: PiccoloJobQueue
    prompt_store: PiccoloPromptStore
    profile_store: PiccoloProfileStore
    analysis_store: PiccoloAnalysisRunStore
    blob_store: FileSystemBlobStore
    vector_index: LanceDBVectorIndex
    embedder: ports.Embedder
    converter: ports.Converter
    llm_client: ports.LLMClient
    handler_context: HandlerContext
    job_runner: JobRunner


def build_container(
    settings: Settings,
    *,
    llm_base_url: str,
    llm_api_key: str | None = None,
) -> AppContainer:
    validate_startup(settings)
    db = PiccoloDatabase(settings.data.db_path)
    db.initialize_schema()

    paper_store = PiccoloPaperStore()
    job_queue = PiccoloJobQueue()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    analysis_store = PiccoloAnalysisRunStore()

    blob_store = FileSystemBlobStore(settings.data.blobs_dir)
    vector_index = LanceDBVectorIndex(LanceDBConfig(path=settings.data.lancedb_dir))
    embedder = build_sentence_transformer_embedder(settings.embeddings.model)
    converter = build_docling_converter()
    llm_client = build_openai_compat_client(base_url=llm_base_url, api_key=llm_api_key)

    handler_context = HandlerContext(
        paper_store=paper_store,
        job_queue=job_queue,
        blob_store=blob_store,
        converter=converter,
        embedder=embedder,
        vector_index=vector_index,
        llm_client=llm_client,
        prompt_store=prompt_store,
        profile_store=profile_store,
        analysis_store=analysis_store,
    )
    job_runner = JobRunner(job_queue=job_queue, context=handler_context)

    return AppContainer(
        settings=settings,
        db=db,
        paper_store=paper_store,
        job_queue=job_queue,
        prompt_store=prompt_store,
        profile_store=profile_store,
        analysis_store=analysis_store,
        blob_store=blob_store,
        vector_index=vector_index,
        embedder=embedder,
        converter=converter,
        llm_client=llm_client,
        handler_context=handler_context,
        job_runner=job_runner,
    )


def validate_startup(settings: Settings) -> None:
    _ensure_dir_exists(settings.data.root, "data.root")
    _ensure_dir_exists(settings.data.db_path.parent, "data.db_path parent")
    _ensure_dir_exists(settings.data.blobs_dir, "data.blobs_dir")
    _ensure_dir_exists(settings.data.blobs_pdf_dir, "data.blobs_pdf_dir")
    _ensure_dir_exists(settings.data.blobs_md_dir, "data.blobs_md_dir")
    _ensure_dir_exists(settings.data.blobs_analysis_dir, "data.blobs_analysis_dir")
    _ensure_dir_exists(settings.data.lancedb_dir, "data.lancedb_dir")
    _require_dependency("docling")
    _require_dependency("lancedb")
    _require_dependency("sentence_transformers")
    _require_dependency("httpx")


def _ensure_dir_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise ConfigurationError(f"Missing required directory: {label} ({path})")


def _require_dependency(module_name: str) -> None:
    if importlib.util.find_spec(module_name) is None:
        raise ConfigurationError(f"Missing required dependency: {module_name}")
