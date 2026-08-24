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
from papers.infra.embedder_ollama.adapter import build_configured_ollama_embedder
from papers.infra.lancedb.index import LanceDBConfig, LanceDBVectorIndex
from papers.infra.llm_openai_compat.client import build_openai_compat_client
from papers.infra.pdf_resolver import (
    ArxivExportPdfResolver,
    ArxivPdfResolver,
    ChainedPdfResolver,
    MdpiPdfResolver,
    OpenAccessPdfResolver,
    PdfDownloader,
    SemanticScholarPdfResolver,
    UnpaywallPdfResolver,
)
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import (
    PiccoloAnalysisRunStore,
    PiccoloAtomicCandidateImport,
    PiccoloCandidateStore,
    PiccoloExtractionStore,
    PiccoloJobQueue,
    PiccoloPaperExternalIdStore,
    PiccoloPaperProjectStore,
    PiccoloPaperStore,
    PiccoloPaperTagStore,
    PiccoloProfileStore,
    PiccoloProjectStore,
    PiccoloPromptStore,
    PiccoloTagStore,
)
from papers.infra.scholar_s2.adapter import build_s2_client


@dataclass(frozen=True)
class AppContainer:
    settings: Settings
    db: PiccoloDatabase
    candidate_store: PiccoloCandidateStore
    paper_store: PiccoloPaperStore
    job_queue: PiccoloJobQueue
    prompt_store: PiccoloPromptStore
    profile_store: PiccoloProfileStore
    analysis_store: PiccoloAnalysisRunStore
    extraction_store: PiccoloExtractionStore
    external_id_store: PiccoloPaperExternalIdStore
    blob_store: FileSystemBlobStore
    vector_index: LanceDBVectorIndex
    embedder: ports.Embedder
    converter: ports.Converter
    llm_client: ports.LLMClient
    scholar_client: ports.ScholarClient
    pdf_resolver: ports.PdfResolver
    pdf_downloader: ports.PdfDownloader
    handler_context: HandlerContext
    job_runner: JobRunner
    project_store: PiccoloProjectStore
    tag_store: PiccoloTagStore
    paper_project_store: PiccoloPaperProjectStore
    paper_tag_store: PiccoloPaperTagStore
    atomic_candidate_import: PiccoloAtomicCandidateImport


def build_container(
    settings: Settings,
    *,
    llm_base_url: str,
    llm_api_key: str | None = None,
) -> AppContainer:
    validate_startup(settings)
    db = PiccoloDatabase(settings.data.db_path)
    db.initialize_schema()

    candidate_store = PiccoloCandidateStore()
    paper_store = PiccoloPaperStore()
    job_queue = PiccoloJobQueue()
    prompt_store = PiccoloPromptStore()
    profile_store = PiccoloProfileStore()
    analysis_store = PiccoloAnalysisRunStore()
    extraction_store = PiccoloExtractionStore()
    external_id_store = PiccoloPaperExternalIdStore()
    project_store = PiccoloProjectStore()
    tag_store = PiccoloTagStore()
    paper_project_store = PiccoloPaperProjectStore()
    paper_tag_store = PiccoloPaperTagStore()
    atomic_candidate_import = PiccoloAtomicCandidateImport()

    blob_store = FileSystemBlobStore(settings.data.blobs_dir)
    vector_index = LanceDBVectorIndex(
        LanceDBConfig(
            path=settings.data.lancedb_dir,
            embedding_model=settings.embeddings.model,
            embedding_dimension=settings.embeddings.dimension,
        )
    )
    embedder = build_configured_ollama_embedder(settings.embeddings)
    converter = build_docling_converter()
    llm_client = build_openai_compat_client(base_url=llm_base_url, api_key=llm_api_key)
    scholar_client = build_s2_client(
        api_key=settings.scholar.api_key or None,
        rate_limit_per_second=settings.scholar.rate_limit_per_second,
    )

    # Build PDF resolver chain:
    # 1. ArXiv Export (export.arxiv.org, designed for programmatic access)
    # 2. ArXiv (arxiv.org fallback, stricter rate limit)
    # 3. OpenAccess (cached URL from S2 search results)
    # 4. MDPI CDN (bypasses Akamai bot protection on mdpi.com)
    # 5. S2 API lookup (queries S2 by DOI/CorpusId at download time)
    # 6. Unpaywall (queries Unpaywall by DOI, if email configured)
    resolvers: list[ports.PdfResolver] = [
        ArxivExportPdfResolver(),
        ArxivPdfResolver(),
        OpenAccessPdfResolver(),
        MdpiPdfResolver(),
        SemanticScholarPdfResolver(api_key=settings.scholar.api_key or None),
    ]
    unpaywall_email = settings.pdf.unpaywall_email
    if unpaywall_email:
        resolvers.append(UnpaywallPdfResolver(email=unpaywall_email))
    pdf_resolver = ChainedPdfResolver(resolvers=resolvers)
    pdf_downloader = PdfDownloader(
        rate_limit_per_second=settings.pdf.download_rate_limit_per_second,
        max_retries=settings.pdf.download_max_retries,
        timeout_s=settings.pdf.download_timeout_s,
        source_rate_limits={
            "arxiv_export": settings.pdf.arxiv_export_rate_limit_per_second,
            "arxiv": settings.pdf.arxiv_rate_limit_per_second,
        },
    )

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
        extraction_store=extraction_store,
        pdf_resolver=pdf_resolver,
        pdf_downloader=pdf_downloader,
        external_id_store=external_id_store,
        scholar_client=scholar_client,
        candidate_store=candidate_store,
    )
    job_runner = JobRunner(job_queue=job_queue, context=handler_context)

    return AppContainer(
        settings=settings,
        db=db,
        candidate_store=candidate_store,
        paper_store=paper_store,
        job_queue=job_queue,
        prompt_store=prompt_store,
        profile_store=profile_store,
        analysis_store=analysis_store,
        extraction_store=extraction_store,
        external_id_store=external_id_store,
        blob_store=blob_store,
        vector_index=vector_index,
        embedder=embedder,
        converter=converter,
        llm_client=llm_client,
        scholar_client=scholar_client,
        pdf_resolver=pdf_resolver,
        pdf_downloader=pdf_downloader,
        handler_context=handler_context,
        job_runner=job_runner,
        project_store=project_store,
        tag_store=tag_store,
        paper_project_store=paper_project_store,
        paper_tag_store=paper_tag_store,
        atomic_candidate_import=atomic_candidate_import,
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
    _require_dependency("httpx")


def _ensure_dir_exists(path: Path, label: str) -> None:
    if path.exists():
        return
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(f"Unable to create required directory: {label} ({path})") from exc


def _require_dependency(module_name: str) -> None:
    if importlib.util.find_spec(module_name) is None:
        raise ConfigurationError(f"Missing required dependency: {module_name}")
