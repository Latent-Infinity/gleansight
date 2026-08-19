from __future__ import annotations

from papers.app.use_cases.admin import RebuildVectorIndexUseCase, RecoverStuckJobsUseCase
from papers.app.use_cases.analysis import AnalyzeProjectUseCase, ReanalyzeWithPromptVersionUseCase
from papers.app.use_cases.discovery import (
    DiscoverCandidatesUseCase,
    ImportCandidateUseCase,
    RejectCandidateUseCase,
)
from papers.app.use_cases.pipeline import (
    EnqueueConvertUseCase,
    EnqueueDownloadUseCase,
    EnqueueEmbedUseCase,
    RunAnalysisUseCase,
)
from papers.app.use_cases.prompts import CreatePromptUseCase, CreatePromptVersionUseCase
from papers.app.use_cases.search import (
    AggregateExtractionsUseCase,
    FilterByExtractionsUseCase,
    SearchPapersUseCase,
)
from papers.app.use_cases.synthesis import SynthesizeFromCorpusUseCase
from papers.app.use_cases.taxonomy import (
    AttachPaperToProjectUseCase,
    AttachTagToPaperUseCase,
    CreateProjectUseCase,
    CreateTagUseCase,
)

__all__ = [
    "EnqueueConvertUseCase",
    "EnqueueDownloadUseCase",
    "EnqueueEmbedUseCase",
    "RunAnalysisUseCase",
    "DiscoverCandidatesUseCase",
    "ImportCandidateUseCase",
    "RejectCandidateUseCase",
    "ReanalyzeWithPromptVersionUseCase",
    "AnalyzeProjectUseCase",
    "CreatePromptUseCase",
    "CreatePromptVersionUseCase",
    "SearchPapersUseCase",
    "FilterByExtractionsUseCase",
    "AggregateExtractionsUseCase",
    "CreateTagUseCase",
    "AttachTagToPaperUseCase",
    "CreateProjectUseCase",
    "AttachPaperToProjectUseCase",
    "RecoverStuckJobsUseCase",
    "RebuildVectorIndexUseCase",
    "SynthesizeFromCorpusUseCase",
]
