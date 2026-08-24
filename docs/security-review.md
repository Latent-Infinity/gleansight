# Security Review

Last updated: 2026-02-09

This document records the security review checklist and findings through Phase 8. It is scoped to the current local-first implementation.

## Checklist

### Secrets and credentials
- [x] API keys stored in OS keychain
  - Reference: design doc Section 13 specifies keychain storage under `paper-manager/endpoint/{profile_name}`.
  - Environment variable fallback: `PAPERS_ENDPOINT_API_KEY_{PROFILE}` and `PAPERS_ENDPOINT_API_KEY`.
- [x] Secrets are not logged
  - Logging standards forbid secrets/tokens. Logging tests validate only structured context fields.
  - Handler-level logging (Phase 8) emits paper_id, model_name, query — no secrets.

### Input validation
- [x] Input validation at boundaries documented
  - Pydantic models validate required fields and enums in `src/papers/domain/models.py`.
  - Config validation enforced in `src/papers/config/settings.py` and startup checks in `src/papers/app/composition_root.py`.
- [x] Startup fail-fast validation
  - `validate_startup()` checks directory existence, creates missing dirs, and verifies dependency availability (lancedb).

### SQL injection prevention
- [x] SQL injection prevention verified
  - Primary persistence uses Piccolo ORM queries and QueryString parameterization in `src/papers/infra/piccolo/`.
  - No string concatenation with untrusted inputs in database writes.

### XSS prevention (UI)
- [x] XSS prevention in UI documented
  - Flet desktop UI (Phase 7) renders via native controls, not HTML.
  - Markdown rendering uses `ft.Markdown` with `GITHUB_WEB` extension set — no raw HTML injection path.
  - No web-facing endpoints; UI runs as a local desktop application only.

### Output handling
- [x] Outputs and artifacts written to local filesystem only
  - Artifacts stored via `FileSystemBlobStore` under local `data/` paths.
  - CSV export (Query screen) writes to user-specified local path only.

### Phase 5: LLM Analysis
- [x] API keys resolved via keychain/env, never embedded in code or config files
- [x] LLM prompts rendered from templates; no user-controlled template injection path
- [x] LLM output parsed and validated against extraction schemas before storage

### Phase 6: Embedding & Vector Search
- [x] Vector store (LanceDB) runs locally — no external embedding API calls
- [x] Embedding model loaded locally via Ollama (`qwen3-embedding:latest`)
- [x] Vector index stored on local filesystem alongside other data artifacts

### Phase 7: UI
- [x] Flet desktop-only — no web server, no exposed ports, no authentication needed
- [x] Paper discovery uses Semantic Scholar public API (read-only, no credentials)
- [x] All UI state is ephemeral (in-memory controls); no cookies or persistent sessions

## Notes / Open Items

- None. All checklist items verified through Phase 8.
