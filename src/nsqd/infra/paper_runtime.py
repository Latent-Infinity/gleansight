from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nsqd.composition import NsqdContainer, build_container
from nsqd.domain.diverge import enabled_operators_from_settings
from nsqd.infra.papers_bridge import (
    DRAFT_PARAPHRASE_PROMPT,
    AnalysisDefaults,
    PapersAcquisitionBridge,
)
from nsqd.ports import Clock
from papers.app.use_cases.discovery import DiscoverCandidatesUseCase, ImportCandidateUseCase
from papers.app.use_cases.pipeline import RunAnalysisUseCase

ACQUISITION_PROMPT_ID = "nsqd-acquisition"
ACQUISITION_PROMPT_VERSION_ID = "nsqd-acquisition-v1"
ACQUISITION_PROFILE_ID = "nsqd-acquisition"
MAX_MARKDOWN_BYTES = 10 * 1024 * 1024
ACQUISITION_PROMPT_BODY = DRAFT_PARAPHRASE_PROMPT


@dataclass(frozen=True)
class NsqdPaperRuntime:
    nsqd: NsqdContainer
    paper_runner: Any
    analysis_defaults: AnalysisDefaults


def bootstrap_analysis_defaults(
    *,
    prompt_store: Any,
    profile_store: Any,
    llm_base_url: str,
    profile_name: str,
    model_name: str,
) -> AnalysisDefaults:
    if prompt_store.get_prompt(ACQUISITION_PROMPT_ID) is None:
        prompt_store.create_prompt(ACQUISITION_PROMPT_ID, "NSQD acquisition draft")
    if prompt_store.get_latest_version(ACQUISITION_PROMPT_ID) is None:
        prompt_store.create_version(
            ACQUISITION_PROMPT_VERSION_ID,
            ACQUISITION_PROMPT_ID,
            1,
            ACQUISITION_PROMPT_BODY,
            "markdown_only",
            None,
        )
    desired_profile_name = profile_name.strip() or "default"
    profile = profile_store.get(ACQUISITION_PROFILE_ID)
    if profile is None:
        profile_store.create_profile(
            ACQUISITION_PROFILE_ID,
            desired_profile_name,
            llm_base_url,
        )
    elif profile.get("name") != desired_profile_name or profile.get("base_url") != llm_base_url:
        profile_store.update_profile(
            ACQUISITION_PROFILE_ID,
            desired_profile_name,
            llm_base_url,
        )
    latest = prompt_store.get_latest_version(ACQUISITION_PROMPT_ID)
    prompt_version_id = None if latest is None else str(latest["prompt_version_id"])
    return AnalysisDefaults(
        prompt_id=ACQUISITION_PROMPT_ID,
        profile_id=ACQUISITION_PROFILE_ID,
        model_name=_require_model_name(model_name),
        prompt_version_id=prompt_version_id,
    )


def compose_default_runtime(
    *,
    papers: Any,
    nsqd_db_path: Path,
    nsqd_index_path: Path,
    llm_base_url: str,
    clock: Clock | None = None,
    approved_projection_digests: frozenset[str] | None = None,
) -> NsqdPaperRuntime:
    llm_settings = getattr(papers.settings, "llm", None)
    profile_name = str(getattr(llm_settings, "default_profile", None) or "default")
    model_name = _require_model_name(getattr(llm_settings, "default_model", None))
    defaults = bootstrap_analysis_defaults(
        prompt_store=papers.prompt_store,
        profile_store=papers.profile_store,
        llm_base_url=llm_base_url,
        profile_name=profile_name,
        model_name=model_name,
    )
    discover = DiscoverCandidatesUseCase(
        scholar_client=papers.scholar_client,
        candidate_store=papers.candidate_store,
    )
    importer = ImportCandidateUseCase(
        candidate_store=papers.candidate_store,
        paper_store=papers.paper_store,
        job_queue=papers.job_queue,
        external_id_store=getattr(papers, "external_id_store", None),
        atomic_candidate_import=getattr(papers, "atomic_candidate_import", None),
        project_store=getattr(papers, "project_store", None),
        tag_store=getattr(papers, "tag_store", None),
    )
    analysis = RunAnalysisUseCase(
        job_queue=papers.job_queue,
        prompt_store=papers.prompt_store,
        profile_store=papers.profile_store,
        analysis_store=papers.analysis_store,
    )
    bridge = PapersAcquisitionBridge(
        discover_candidates=discover,
        import_candidate=importer,
        run_analysis=analysis,
        paper_store=papers.paper_store,
        analysis_defaults=defaults,
        get_markdown=markdown_reader(getattr(papers, "blob_store", None)),
        candidate_lookup=papers.candidate_store,
        llm_client=getattr(papers, "llm_client", None),
        llm_profile={"base_url": llm_base_url},
        draft_prompt=ACQUISITION_PROMPT_BODY,
    )
    nsqd = build_container(
        db_path=nsqd_db_path,
        index_path=nsqd_index_path,
        clock=clock,
        approved_projection_digests=approved_projection_digests,
        paper_bridge=bridge,
        embedder=getattr(papers, "embedder", None),
        enabled_operators=enabled_operators_from_settings(getattr(papers, "settings", None)),
    )
    return NsqdPaperRuntime(
        nsqd=nsqd,
        paper_runner=papers.job_runner,
        analysis_defaults=defaults,
    )


def markdown_reader(blob_store: Any) -> Any:
    def get_markdown(paper_id: str) -> str | None:
        if blob_store is None:
            return None
        getter = getattr(blob_store, "get_markdown_path", None)
        if getter is None:
            return None
        path = getter(paper_id)
        if path is None:
            return None
        markdown_path = Path(path).resolve()
        paths = getattr(blob_store, "_paths", None)
        markdown_root = getattr(paths, "md_dir", None)
        if markdown_root is not None:
            try:
                markdown_path.relative_to(Path(markdown_root).resolve())
            except ValueError as exc:
                raise ValueError("paper markdown path is outside the blob root") from exc
        try:
            with markdown_path.open("rb") as handle:
                content = handle.read(MAX_MARKDOWN_BYTES + 1)
        except OSError:
            return None
        if len(content) > MAX_MARKDOWN_BYTES:
            raise ValueError("paper markdown is too large")
        return content.decode("utf-8")

    return get_markdown


def _require_model_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("papers.settings.llm.default_model is required")
    return value.strip()
