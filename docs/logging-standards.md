# Logging Standards

Structured logging fields required on every job lifecycle event:

- `timestamp` (UTC ISO 8601)
- `job_id`
- `job_type`
- `status_from`
- `status_to`
- `paper_id` (nullable for discover)
- `run_id` (nullable for non-analyze jobs)

Additional recommended context fields:

- `attempts`
- `max_attempts`
- `error_code`
- `error_message`
- `duration_ms`
- `pipeline_stage`

Severity guidelines:

- `DEBUG`: entry/exit of public methods, detailed payloads (bounded)
- `INFO`: state transitions and decisions
- `WARNING`: retryable failures, validation warnings
- `ERROR`: permanent failures and unhandled exceptions

Security:
- Do not log secrets, tokens, or full document contents.
- Redact or hash external identifiers when needed.
