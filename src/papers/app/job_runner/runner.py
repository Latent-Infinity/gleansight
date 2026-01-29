from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from papers.app.job_runner.handlers import HANDLERS, HandlerContext, HandlerResult
from papers.app.ports import Job, JobQueue
from papers.domain.errors import ErrorCode, NotFoundError, NotReadyError, PipelineError


@dataclass(frozen=True)
class JobRunner:
    job_queue: JobQueue
    context: HandlerContext

    def run_next(self, now: datetime) -> bool:
        job = self.job_queue.claim_next(now)
        if job is None:
            return False
        if self.job_queue.is_cancelled(job.job_id):
            return False
        started_at = now
        _log_event(
            logging.INFO,
            job=job,
            status_from="queued",
            status_to="running",
            attempts=job.attempts,
            max_attempts=job.max_attempts,
        )
        handler = HANDLERS.get(job.type)
        if handler is None:
            self.job_queue.mark_failed(job.job_id, f"unknown job type: {job.type}")
            _log_event(
                logging.ERROR,
                job=job,
                status_from="running",
                status_to="failed",
                error_message=f"unknown job type: {job.type}",
            )
            return True
        try:
            result = handler(job, self.context)
        except NotReadyError as exc:
            result = HandlerResult.retryable(
                str(exc),
                delay_s=_retry_delay_s(job.attempts),
            )
        except NotFoundError as exc:
            result = HandlerResult.failed(str(exc))
        except PipelineError as exc:
            result = _result_from_pipeline_error(exc, job.attempts)
        except Exception as exc:  # pragma: no cover - safety net
            result = HandlerResult.failed(str(exc))
        self._finalize(job, result, started_at)
        return True

    def _finalize(self, job: Job, result: HandlerResult, started_at: datetime) -> None:
        if result.status == "canceled" or self.job_queue.is_cancelled(job.job_id):
            _log_event(
                logging.INFO,
                job=job,
                status_from="running",
                status_to="canceled",
            )
            return
        duration_ms = _duration_ms(started_at, datetime.now(UTC))
        if result.status == "succeeded":
            self.job_queue.mark_succeeded(job.job_id)
            self.context.metrics.increment(
                "job_succeeded_total",
                tags={"job_type": job.type},
            )
            self.context.metrics.observe(
                "job_duration_ms",
                duration_ms,
                tags={"job_type": job.type},
            )
            _log_event(
                logging.INFO,
                job=job,
                status_from="running",
                status_to="succeeded",
                duration_ms=duration_ms,
            )
        elif result.status == "retryable" and result.retry_after is not None:
            self.job_queue.mark_retryable(
                job.job_id,
                result.error or "retryable",
                result.retry_after,
            )
            self.context.metrics.increment(
                "job_retries_total",
                tags={"job_type": job.type, "error_code": result.error_code or "unknown"},
            )
            self.context.metrics.observe(
                "job_duration_ms",
                duration_ms,
                tags={"job_type": job.type},
            )
            _log_event(
                logging.WARNING,
                job=job,
                status_from="running",
                status_to="queued",
                error_code=result.error_code,
                error_message=result.error,
                duration_ms=duration_ms,
            )
        else:
            self.job_queue.mark_failed(job.job_id, result.error or "failed")
            self.context.metrics.increment(
                "job_failures_total",
                tags={"job_type": job.type, "error_code": result.error_code or "unknown"},
            )
            self.context.metrics.observe(
                "job_duration_ms",
                duration_ms,
                tags={"job_type": job.type},
            )
            _log_event(
                logging.ERROR,
                job=job,
                status_from="running",
                status_to="failed",
                error_code=result.error_code,
                error_message=result.error,
                duration_ms=duration_ms,
            )
        if (
            result.status in {"retryable", "failed"}
            and job.paper_id is not None
            and job.type in {"download", "convert", "embed"}
            and result.error_code
        ):
            self.context.paper_store.set_pipeline_health_error(
                job.paper_id,
                result.error_code,
                result.error or "error",
                job.job_id,
            )


def _retry_delay_s(attempts: int) -> int:
    base = 60
    delay = base * (2**attempts)
    return min(delay, 3600)


def _result_from_pipeline_error(exc: PipelineError, attempts: int) -> HandlerResult:
    code = exc.code
    if code in _RETRYABLE_ERROR_CODES:
        return HandlerResult.retryable(
            str(exc),
            delay_s=_retry_delay_s(attempts),
            error_code=str(code),
        )
    if code == ErrorCode.CONVERSION_FAILED and _is_transient_error(str(exc)):
        return HandlerResult.retryable(
            str(exc),
            delay_s=_retry_delay_s(attempts),
            error_code=str(code),
        )
    return HandlerResult.failed(str(exc), error_code=str(code))


def _is_transient_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "timeout",
            "temporar",
            "retry",
            "connection",
            "network",
            "unavailable",
        )
    )


_RETRYABLE_ERROR_CODES = {
    ErrorCode.RATE_LIMITED,
    ErrorCode.NETWORK_ERROR,
    ErrorCode.TIMEOUT,
    ErrorCode.LLM_TIMEOUT,
    ErrorCode.CONVERTER_TIMEOUT,
    ErrorCode.CONVERTER_OOM,
}


def _duration_ms(started_at: datetime, finished_at: datetime) -> float:
    return (finished_at - started_at).total_seconds() * 1000.0


def _log_event(
    level: int,
    *,
    job: Job,
    status_from: str,
    status_to: str,
    attempts: int | None = None,
    max_attempts: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    duration_ms: float | None = None,
) -> None:
    logger = logging.getLogger("papers.job_runner")
    logger.log(
        level,
        "job_event",
        extra={
            "timestamp": datetime.now(UTC).isoformat(),
            "job_id": job.job_id,
            "job_type": job.type,
            "status_from": status_from,
            "status_to": status_to,
            "paper_id": job.paper_id,
            "run_id": job.run_id,
            "attempts": attempts,
            "max_attempts": max_attempts,
            "error_code": error_code,
            "error_message": error_message,
            "duration_ms": duration_ms,
        },
    )
