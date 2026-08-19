from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from papers.app import ports
from papers.domain.errors import NotFoundError


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class EnqueueDownloadUseCase:
    job_queue: ports.JobQueue

    def __call__(self, *, paper_id: str, source_path: str, max_attempts: int = 3) -> str:
        payload = {"source_path": source_path, "max_attempts": max_attempts}
        job_id = self.job_queue.enqueue("download", paper_id, None, payload)
        _log_enqueue(
            job_id=job_id,
            job_type="download",
            paper_id=paper_id,
            run_id=None,
        )
        return job_id


@dataclass(frozen=True)
class EnqueueConvertUseCase:
    job_queue: ports.JobQueue

    def __call__(self, *, paper_id: str, max_attempts: int = 3) -> str:
        payload = {"max_attempts": max_attempts}
        job_id = self.job_queue.enqueue("convert", paper_id, None, payload)
        _log_enqueue(
            job_id=job_id,
            job_type="convert",
            paper_id=paper_id,
            run_id=None,
        )
        return job_id


@dataclass(frozen=True)
class EnqueueEmbedUseCase:
    job_queue: ports.JobQueue

    def __call__(self, *, paper_id: str, max_attempts: int = 3) -> str:
        payload = {"max_attempts": max_attempts}
        job_id = self.job_queue.enqueue("embed", paper_id, None, payload)
        _log_enqueue(
            job_id=job_id,
            job_type="embed",
            paper_id=paper_id,
            run_id=None,
        )
        return job_id


@dataclass(frozen=True)
class RunAnalysisUseCase:
    job_queue: ports.JobQueue
    prompt_store: ports.PromptStore
    profile_store: ports.ProfileStore
    analysis_store: ports.AnalysisRunStore

    def __call__(
        self,
        *,
        paper_id: str,
        prompt_id: str,
        prompt_version_id: str | None,
        profile_id: str,
        model_name: str,
        force: bool = False,
    ) -> str:
        version = self._resolve_prompt_version(prompt_id, prompt_version_id)
        if self.profile_store.get(profile_id) is None:
            raise NotFoundError("profile not found")
        existing = None
        if not force:
            existing = self.analysis_store.get_latest_successful_run(
                paper_id=paper_id,
                prompt_version_id=version["prompt_version_id"],
                profile_id=profile_id,
                model_name=model_name,
            )
        if existing is not None:
            _log_enqueue(
                job_id=existing["run_id"],
                job_type="analyze",
                paper_id=paper_id,
                run_id=existing["run_id"],
                prompt_version_id=version["prompt_version_id"],
                profile_id=profile_id,
                model_name=model_name,
                status_from="succeeded",
                status_to="reuse",
            )
            return existing["run_id"]
        run_id = _new_id()
        self.analysis_store.create_run(
            run_id=run_id,
            paper_id=paper_id,
            prompt_version_id=version["prompt_version_id"],
            profile_id=profile_id,
            model_name=model_name,
        )
        payload = {
            "prompt_version_id": version["prompt_version_id"],
            "profile_id": profile_id,
            "model_name": model_name,
        }
        job_id = self.job_queue.enqueue("analyze", paper_id, run_id, payload)
        _log_enqueue(
            job_id=job_id,
            job_type="analyze",
            paper_id=paper_id,
            run_id=run_id,
            prompt_version_id=version["prompt_version_id"],
            profile_id=profile_id,
            model_name=model_name,
        )
        return run_id

    def _resolve_prompt_version(
        self,
        prompt_id: str,
        prompt_version_id: str | None,
    ) -> dict[str, Any]:
        if prompt_version_id:
            version = self.prompt_store.get_version(prompt_version_id)
        else:
            version = self.prompt_store.get_latest_version(prompt_id)
        if version is None:
            raise NotFoundError("prompt version not found")
        if version["prompt_id"] != prompt_id:
            raise NotFoundError("prompt version not found for prompt")
        return version


def _log_enqueue(
    *,
    job_id: str,
    job_type: str,
    paper_id: str,
    run_id: str | None,
    prompt_version_id: str | None = None,
    profile_id: str | None = None,
    model_name: str | None = None,
    status_from: str = "new",
    status_to: str = "queued",
) -> None:
    logger = logging.getLogger("papers.use_cases")
    logger.info(
        "enqueue_job",
        extra={
            "timestamp": datetime.now(UTC).isoformat(),
            "job_id": job_id,
            "job_type": job_type,
            "paper_id": paper_id,
            "run_id": run_id,
            "status_from": status_from,
            "prompt_version_id": prompt_version_id,
            "profile_id": profile_id,
            "model_name": model_name,
            "status_to": status_to,
        },
    )
