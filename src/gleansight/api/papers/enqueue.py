from __future__ import annotations

import json
from pathlib import Path
from typing import assert_never

from pydantic import JsonValue, TypeAdapter

from gleansight.api.models import OperationError
from gleansight.api.papers.common import database, require_paper
from gleansight.api.papers.job_requests import (
    AnalyzeJob,
    ConvertJob,
    DiscoverJob,
    DownloadJob,
    EmbedJob,
    EnqueueJob,
    JobId,
)
from gleansight.api.papers.pipeline import analysis_use_case
from gleansight.api.runtime import ApiRuntime
from papers.infra.piccolo.stores import PiccoloJobQueue, PiccoloPromptStore


def enqueue(runtime: ApiRuntime, request: EnqueueJob) -> JsonValue:
    db = database(runtime)
    job = request.job
    payload = job.payload.model_dump(mode="json", exclude_none=True)
    match job:
        case DiscoverJob():
            paper_id, run_id = None, None
        case AnalyzeJob():
            require_paper(runtime, job.paper_id)
            run = db.fetchone("SELECT * FROM analysis_runs WHERE run_id = ?", [job.run_id])
            if run is None:
                raise OperationError("not_found", "Analysis run does not exist.")
            expected = {
                "paper_id": job.paper_id,
                "prompt_version_id": job.payload.prompt_version_id,
                "profile_id": job.payload.profile_id,
                "model_name": job.payload.model_name,
            }
            if any(run.get(key) != value for key, value in expected.items()):
                raise OperationError("conflict", "Analysis job does not match its run.")
            paper_id, run_id = job.paper_id, job.run_id
        case DownloadJob() | ConvertJob():
            require_paper(runtime, job.paper_id)
            paper_id, run_id = job.paper_id, None
            if job.payload.source_path is not None:
                payload["source_path"] = str(runtime.resolve(Path(job.payload.source_path)))
        case EmbedJob():
            require_paper(runtime, job.paper_id)
            paper_id, run_id = job.paper_id, None
        case unreachable:
            assert_never(unreachable)
    return {"job_id": PiccoloJobQueue().enqueue(job.type, paper_id, run_id, payload)}


def retry(runtime: ApiRuntime, request: JobId) -> JsonValue:
    row = database(runtime).fetchone("SELECT * FROM jobs WHERE job_id = ?", [request.job_id])
    if row is None:
        raise OperationError("not_found", "Job does not exist.")
    if row["status"] not in {"failed", "canceled", "succeeded"}:
        raise OperationError("conflict", "Only a terminal job can be retried.")
    payload = TypeAdapter(dict[str, JsonValue]).validate_json(row["payload_json"])
    job: dict[str, JsonValue] = {"type": row["type"], "payload": payload}
    if row["paper_id"] is not None:
        job["paper_id"] = row["paper_id"]
    if row["run_id"] is not None:
        job["run_id"] = row["run_id"]
    parsed_request = EnqueueJob.model_validate_json(json.dumps({"job": job}))
    match parsed_request.job:
        case AnalyzeJob() as analysis:
            version = PiccoloPromptStore().get_version(analysis.payload.prompt_version_id)
            if version is None:
                raise OperationError("not_found", "Prompt version does not exist.")
            require_paper(runtime, analysis.paper_id)
            return {
                "run_id": analysis_use_case(runtime)(
                    paper_id=analysis.paper_id,
                    prompt_id=version["prompt_id"],
                    prompt_version_id=analysis.payload.prompt_version_id,
                    profile_id=analysis.payload.profile_id,
                    model_name=analysis.payload.model_name,
                    force=True,
                )
            }
        case DownloadJob() | ConvertJob() | EmbedJob() | DiscoverJob():
            return enqueue(runtime, parsed_request)
        case unreachable:
            assert_never(unreachable)
