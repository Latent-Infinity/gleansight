from datetime import UTC, datetime, timedelta

import pytest

from gleansight.api.models import OperationError
from gleansight.api.runtime import ApiRuntime
from papers.infra.piccolo.stores import PiccoloJobQueue
from tests.api.papers.support import call, identifier, items, prompt_version, record


def test_cancel_only_changes_active_jobs(populated: ApiRuntime) -> None:
    # Given
    job_id = identifier(call(populated, "pipeline.convert", {"paper_id": "paper-1"}), "job_id")
    PiccoloJobQueue().mark_succeeded(job_id)
    # When
    result = call(populated, "jobs.cancel", {"job_id": job_id})
    # Then
    assert result == {"canceled": 0}
    assert call(populated, "jobs.status", {}) == [{"status": "succeeded", "count": 1}]


def test_running_job_blocks_bulk_deletion_atomically(populated: ApiRuntime) -> None:
    # Given
    first = identifier(call(populated, "pipeline.convert", {"paper_id": "paper-1"}), "job_id")
    second = identifier(call(populated, "pipeline.embed", {"paper_id": "paper-1"}), "job_id")
    PiccoloJobQueue().claim_next(datetime.now(UTC))
    # When / Then
    with pytest.raises(OperationError, match="Cancel running"):
        call(populated, "jobs.bulk-delete", {"job_ids": [first, second]})
    assert len(items(populated, "jobs.list", {})) == 2


def test_cancel_then_delete_terminal_job(populated: ApiRuntime) -> None:
    # Given
    job_id = identifier(call(populated, "pipeline.convert", {"paper_id": "paper-1"}), "job_id")
    call(populated, "jobs.cancel", {"job_id": job_id})
    # When
    result = call(populated, "jobs.delete", {"job_id": job_id})
    # Then
    assert result == {"deleted": 1}
    assert call(populated, "jobs.status", {}) == []


def test_retry_terminal_job_creates_new_job(populated: ApiRuntime) -> None:
    # Given
    previous = identifier(call(populated, "pipeline.convert", {"paper_id": "paper-1"}), "job_id")
    PiccoloJobQueue().mark_failed(previous, "Conversion failed")
    # When
    result = call(populated, "jobs.retry", {"job_id": previous})
    # Then
    assert identifier(result, "job_id") != previous
    assert call(populated, "jobs.status", {}) == [
        {"status": "failed", "count": 1},
        {"status": "queued", "count": 1},
    ]


def test_retry_analysis_creates_new_run(populated: ApiRuntime) -> None:
    # Given
    prompt_id, version_id = prompt_version(populated)
    previous_run = identifier(
        call(
            populated,
            "pipeline.analyze",
            {
                "paper_id": "paper-1",
                "prompt_id": prompt_id,
                "prompt_version_id": version_id,
                "profile_id": "local",
                "model_name": "fake",
            },
        ),
        "run_id",
    )
    previous_job = PiccoloJobQueue().list_jobs()[0]["job_id"]
    PiccoloJobQueue().mark_failed(previous_job, "Provider unavailable")
    # When
    result = call(populated, "jobs.retry", {"job_id": previous_job})
    # Then
    assert identifier(result, "run_id") != previous_run
    assert len(items(populated, "runs.list", {"paper_id": "paper-1"})) == 2


def test_recover_requeues_stale_lease(populated: ApiRuntime) -> None:
    # Given
    job_id = identifier(call(populated, "pipeline.embed", {"paper_id": "paper-1"}), "job_id")
    PiccoloJobQueue().claim_next(datetime.now(UTC))
    populated.paper_database.execute(
        "UPDATE jobs SET updated_at = ? WHERE job_id = ?",
        [(datetime.now(UTC) - timedelta(days=1)).isoformat(), job_id],
    )
    # When
    result = call(populated, "jobs.recover", {"stuck_after_seconds": 60})
    # Then
    assert result == [job_id]
    assert call(populated, "jobs.status", {}) == [{"status": "queued", "count": 1}]


def test_run_bounded_executes_local_pipeline(populated: ApiRuntime, providers: None) -> None:
    # Given
    pdf = populated.repo_root / "paper.pdf"
    pdf.write_bytes(b"%PDF-local-fake")
    call(populated, "pipeline.download", {"paper_id": "paper-1", "source_path": "paper.pdf"})
    # When
    result = call(populated, "jobs.run-bounded", {"max_jobs": 3})
    # Then
    assert result == {"processed": 3}, str(call(populated, "jobs.list", {}))
    assert record(populated, "papers.get", {"paper_id": "paper-1"})["pipeline_stage"] == "embedded"
    assert call(populated, "jobs.status", {}) == [{"status": "succeeded", "count": 3}]
    assert "Adaptive learning" in identifier(
        call(populated, "papers.get-markdown", {"paper_id": "paper-1"}), "markdown"
    )
