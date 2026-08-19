# Development Plan Creation Guide

> **Canonical authority is guide v2.0:**
> `/Users/firestrand/Library/CloudStorage/Dropbox/Projects/Software-Standards/development-plan-creation-guide.md`
> This in-repo file is the older layer-based outline. Do not use it to author or revise plans.

A practical framework for creating software development plans that produce stable, maintainable, and well-tested code.

---

## Core Principles

Before planning any feature or system, internalize these constraints:

| Principle | Planning Implication |
|-----------|---------------------|
| **SOLID** | Each task should modify/create components with single responsibilities. Plan for abstractions before implementations. |
| **DRY** | Identify shared abstractions early. Schedule refactoring tasks when duplication becomes apparent. |
| **KISS** | Prefer the simplest solution that meets requirements. Defer optimization until profiling proves necessity. |
| **TDD** | Every implementation task is preceded by its test task. No exceptions. |
| **≥90% Coverage** | All phases maintain minimum 90% test coverage. Foundation and domain layers target higher. |
| **Stable Stages** | Each phase ends with passing tests, no broken imports, and staged changes ready for human review. |

---

## Plan Structure

```
Development Plan: [Feature/System Name]
├── Phase 0: Foundation & Standards
├── Phase 1: Core Domain
├── Phase 2: Primary Implementation
├── Phase 3: Integration
├── Phase 4: Hardening
└── Phase 5: Polish & Documentation
```

---

## Human Review Workflow

Each phase concludes with staged changes for human review:

1. **Stage Changes:** `git add -A` (or selective staging)
2. **Run Verification:**
   - All tests pass
   - Coverage meets phase target (≥90%)
   - Linting/formatting passes
3. **Human Review:** Reviewer examines staged changes
4. **Human Commits:** Reviewer commits with appropriate message and any necessary adjustments

The developer does not commit directly. All commits flow through human review.

---

## Phase Definitions

### Phase 0: Foundation & Standards
**Goal:** Establish project scaffolding, tooling, standards, and interfaces without business logic.

**Coverage Target:** ≥95% (interface contracts and configuration validation)

**Standard Tasks:**

#### Repository Setup
1. Initialize git repository if not already initialized (`git init`)
2. Create/update `.gitignore` for project patterns:
   - Language-specific ignores (`.pyc`, `__pycache__/`, `node_modules/`, etc.)
   - IDE/editor files (`.idea/`, `.vscode/`, `*.swp`)
   - Environment files (`.env`, `.env.local`)
   - Data files (`*.csv`, `*.parquet`, `*.db`, `data/`, `datasets/`)
   - Model artifacts (`*.pkl`, `*.joblib`, `models/`)
   - Build outputs (`dist/`, `build/`, `*.egg-info/`)
   - Test artifacts (`.coverage`, `htmlcov/`, `.pytest_cache/`)
   - OS files (`.DS_Store`, `Thumbs.db`)
   - Project-specific unique files (document explicitly)

#### Library Standards Definition
3. **Human Decision Point:** Define and document preferred libraries for the project:

   | Category | Preferred | Avoid | Rationale |
   |----------|-----------|-------|-----------|
   | CLI Framework | `typer` | `argparse`, `click` | Type hints, auto-help, less boilerplate |
   | Terminal Output | `rich` | `colorama`, print | Tables, progress bars, consistent styling |
   | Data Processing | `polars` | `pandas` | Performance, memory efficiency, clearer API |
   | HTTP Client | `httpx` | `requests` | Async support, modern API |
   | Validation | `pydantic` | `dataclasses` + manual | Rich validation, serialization |
   | Testing | `pytest` | `unittest` | Fixtures, parametrize, plugins |
   | Logging | `structlog` | `logging` | Structured output, context binding |

   *Adjust table based on project needs. Document deviations and rationale.*

4. Create dependency manifest (e.g., `pyproject.toml`, `requirements.txt`)
5. Set up linting/formatting configuration (e.g., `ruff`, `black`, `prettier`)
6. Configure test runner and coverage requirements (≥90% enforced)

#### Interface Definition
7. Create directory/module structure
8. Define public interfaces/protocols/ABCs
9. Create placeholder implementations (raise `NotImplementedError`)
10. Write interface contract tests (they should fail against placeholders)
11. Define custom exception hierarchy for the module
12. Define logging patterns and context requirements

**Exit Criteria:**
- [ ] Git initialized with comprehensive `.gitignore`
- [ ] Library standards documented and dependencies declared
- [ ] All new modules importable without error
- [ ] Interfaces documented with docstrings
- [ ] Contract tests written (failing against placeholders is expected)
- [ ] Exception types defined
- [ ] Logging patterns established
- [ ] Coverage ≥95% on foundation code (config, interfaces)
- [ ] **Stage changes for human review**

---

### Phase 1: Core Domain
**Goal:** Implement domain models and business logic in isolation.

**Coverage Target:** ≥95% (domain logic is critical path)

**Standard Tasks:**
1. **Test:** Write unit tests for domain models/entities
2. **Implement:** Domain models with validation logic
3. **Test:** Write unit tests for business rules/services
4. **Implement:** Pure business logic (no I/O, no side effects)
5. **Test:** Write unit tests for domain-specific exceptions
6. **Implement:** Exception handling within domain operations
7. **Refactor:** Extract common patterns, ensure SRP compliance

**Exit Criteria:**
- [ ] Domain models fully tested
- [ ] No external dependencies in domain code (no I/O, no network, no filesystem)
- [ ] Domain exceptions raised with meaningful context
- [ ] All domain tests passing
- [ ] Coverage ≥95% on domain layer
- [ ] **Stage changes for human review**

---

### Phase 2: Primary Implementation
**Goal:** Build the main functional pathway end-to-end.

**Coverage Target:** ≥90%

**Standard Tasks:**
1. **Test:** Write tests for adapters/repositories (use fakes/mocks)
2. **Implement:** Adapters for external systems (DB, APIs, filesystem)
3. **Test:** Write tests for adapter-level exception translation
4. **Implement:** Exception translation (external errors → domain exceptions)
5. **Test:** Write tests for primary use case orchestration
6. **Implement:** Service/use-case layer connecting domain to adapters
7. **Test:** Write integration test for happy path
8. **Implement:** Wire up dependency injection / composition root
9. **Implement:** Basic structured logging at service boundaries

**Exit Criteria:**
- [ ] Happy path functional end-to-end
- [ ] Adapters implement interfaces from Phase 0
- [ ] External exceptions wrapped in domain exception types
- [ ] Structured logging captures request context
- [ ] Integration test passes
- [ ] Coverage ≥90%
- [ ] **Stage changes for human review**

---

### Phase 3: Integration
**Goal:** Connect to real external systems and handle edge cases.

**Coverage Target:** ≥90%

**Standard Tasks:**
1. **Test:** Write integration tests against real dependencies (DB, services)
2. **Implement:** Real adapter configurations
3. **Test:** Write tests for error conditions and edge cases
4. **Implement:** Error handling, retry logic, circuit breakers
5. **Test:** Write tests for boundary conditions and input validation
6. **Implement:** Input validation at system boundaries
7. **Test:** Write tests verifying error logging output
8. **Implement:** Error logging with full context (stack traces, request IDs, relevant state)

**Exit Criteria:**
- [ ] Real integration tests passing (or explicitly skipped in CI with markers)
- [ ] Error paths tested and handled gracefully
- [ ] No unhandled exceptions in normal operation
- [ ] Errors logged with sufficient context for debugging
- [ ] Coverage ≥90%
- [ ] **Stage changes for human review**

---

### Phase 4: Hardening
**Goal:** Production-readiness through observability and resilience.

**Coverage Target:** ≥90%

**Standard Tasks:**
1. **Test:** Write tests for logging output format and content
2. **Implement:** Structured logging at key decision points
3. **Test:** Write tests for metrics emission
4. **Implement:** Metrics/telemetry hooks
5. **Test:** Write tests for configuration validation
6. **Implement:** Fail-fast on invalid configuration
7. **Test:** Write load/stress tests (if applicable)
8. **Implement:** Performance optimizations (only if tests prove necessity)
9. **Review:** Security audit of inputs, outputs, and dependencies

**Logging Checklist:**
- [ ] Entry/exit of public API methods (DEBUG level)
- [ ] Business decisions and branches taken (INFO level)
- [ ] Recoverable errors and retries (WARNING level)
- [ ] Failures and exceptions (ERROR level)
- [ ] All logs include correlation/request ID
- [ ] No sensitive data in logs (PII, credentials, tokens)

**Exit Criteria:**
- [ ] Logs provide sufficient debugging context
- [ ] Key operations emit metrics
- [ ] Invalid configuration fails fast with clear message
- [ ] No obvious security vulnerabilities
- [ ] Coverage ≥90%
- [ ] **Stage changes for human review**

---

### Phase 5: Polish & Documentation
**Goal:** Make it maintainable for the next developer.

**Coverage Target:** ≥90% (maintain, don't regress)

**Standard Tasks:**
1. Update/create README for the feature/module
2. Add inline documentation for non-obvious decisions
3. Create/update architecture decision records (ADRs) if significant choices were made
4. Document error handling strategy and exception types
5. Document logging patterns and how to interpret logs
6. Review and clean up TODOs
7. Final refactoring pass (naming, structure, dead code removal)
8. Update CHANGELOG

**Exit Criteria:**
- [ ] New developer could understand the module from docs alone
- [ ] Error handling documented
- [ ] No unresolved TODOs (or they're tracked in issue system)
- [ ] Coverage ≥90% maintained
- [ ] **Stage changes for human review**

---

## Task Writing Standards

Each task in your plan should follow this template:

```markdown
### Task [Phase].[Number]: [Action] [Subject]

**Type:** Test | Implement | Refactor | Document | Human Decision

**Description:**
[1-3 sentences explaining what and why]

**Acceptance Criteria:**
- [ ] [Specific, verifiable criterion]
- [ ] [Another criterion]
- [ ] Tests pass with ≥90% coverage maintained

**Files Affected (optional):**
- `path/to/file.py` (create|modify)
```

Keep tasks ordered so that each task's prerequisites appear earlier in the list.

---

## TDD Task Pairing

Every implementation task MUST have a preceding test task. Structure them as pairs:

```markdown
### Task 2.1: Test UserRepository interface compliance

**Type:** Test

**Description:**
Write unit tests verifying UserRepository implementations satisfy the
Repository protocol: save, get_by_id, delete, and list operations.

**Acceptance Criteria:**
- [ ] Tests cover all protocol methods
- [ ] Tests use fake/mock implementations
- [ ] Tests verify both success and failure modes
- [ ] Coverage ≥90% maintained

---

### Task 2.2: Implement PostgresUserRepository

**Type:** Implement

**Description:**
Create PostgreSQL-backed implementation of UserRepository protocol.

**Acceptance Criteria:**
- [ ] All tests from Task 2.1 pass
- [ ] Uses connection pooling
- [ ] Implements proper transaction handling
- [ ] Translates database exceptions to domain exceptions
- [ ] Coverage ≥90% maintained
```

---

## Coverage Requirements

**Minimum coverage is ≥90% for all phases.** Target higher for critical layers:

| Layer | Target Coverage | Rationale |
|-------|-----------------|-----------|
| Domain/Models | ≥95% | Core logic, highest bug impact |
| Interfaces/Contracts | ≥95% | Define system boundaries |
| Services/Use Cases | ≥92% | Orchestration logic |
| Adapters | ≥90% | I/O boundaries |
| Configuration | ≥90% | Fail-fast validation |
| Entry Points (CLI/API) | ≥90% | User-facing surface |

**Exclusions** (document explicitly in coverage config):
- Generated code
- Debug/development-only utilities
- Third-party wrapper thin shims
- Type stubs / protocol definitions without logic

---

## Error Handling Standards

Plan for these error categories in each phase:

| Category | Handling Pattern | Logging Level |
|----------|------------------|---------------|
| Validation errors | Reject early, clear message | WARNING |
| Business rule violations | Domain exception, actionable message | INFO |
| External service failures | Retry with backoff, then wrap in domain exception | ERROR |
| Configuration errors | Fail fast at startup | CRITICAL |
| Unexpected errors | Log full context, generic user message | ERROR |

**Exception Hierarchy Pattern:**
```
BaseModuleError
├── ValidationError
├── NotFoundError
├── ConflictError
├── ExternalServiceError
│   ├── DatabaseError
│   └── APIClientError
└── ConfigurationError
```

---

## Anti-Patterns to Avoid

### In Planning:
- ❌ "Implement feature X" as a single task (too large)
- ❌ Test tasks after implementation tasks
- ❌ Phases without clear exit criteria
- ❌ Skipping Phase 0 (leads to interface churn and inconsistent libraries)
- ❌ Coverage targets below 90%

### In Execution:
- ❌ Staging changes with failing tests
- ❌ Staging changes with coverage below target
- ❌ Refactoring during implementation (separate tasks)
- ❌ Adding unplanned scope without updating plan
- ❌ Catching and swallowing exceptions without logging
- ❌ Logging without context (request IDs, relevant state)

---

## Quick Reference: Plan Creation Checklist

Before starting development, verify your plan:

- [ ] Phase 0 includes git init and .gitignore setup
- [ ] Library standards defined with rationale (human decision point)
- [ ] Every implementation task has a preceding test task
- [ ] Each phase has measurable exit criteria
- [ ] Each phase ends with "stage changes for human review"
- [ ] Phase 0 defines all public interfaces and exception types
- [ ] Domain logic (Phase 1) has no I/O dependencies
- [ ] Error handling addressed in Phases 2-3
- [ ] Logging addressed in Phases 2-4
- [ ] Integration points identified and isolated in Phase 2-3
- [ ] Observability addressed in Phase 4
- [ ] Documentation scheduled, not forgotten
- [ ] Coverage ≥90% required at every phase
- [ ] Tasks ordered so prerequisites come first

---

## Example: Minimal Feature Plan

```markdown
# Development Plan: User Authentication Service

## Phase 0: Foundation & Standards (Coverage ≥95%)
- [ ] 0.1: Initialize git repo, create .gitignore (exclude .env, *.db, data/)
- [ ] 0.2: **Human Decision:** Confirm library choices (typer, rich, structlog, pydantic)
- [ ] 0.3: Create `auth/` module structure
- [ ] 0.4: Define `Authenticator` protocol
- [ ] 0.5: Define `TokenStore` protocol
- [ ] 0.6: Define `AuthError` exception hierarchy
- [ ] 0.7: Define logging context requirements (user_id, request_id)
- [ ] 0.8: Write protocol contract tests
→ Stage for human review

## Phase 1: Core Domain (Coverage ≥95%)
- [ ] 1.1: Test `Credentials` value object validation
- [ ] 1.2: Implement `Credentials` value object
- [ ] 1.3: Test `AuthToken` entity
- [ ] 1.4: Implement `AuthToken` entity
- [ ] 1.5: Test `AuthenticationService` business rules
- [ ] 1.6: Implement `AuthenticationService`
- [ ] 1.7: Test domain exception scenarios
- [ ] 1.8: Implement domain exception raising with context
→ Stage for human review

## Phase 2: Primary Implementation (Coverage ≥90%)
- [ ] 2.1: Test `JWTTokenStore` adapter
- [ ] 2.2: Implement `JWTTokenStore`
- [ ] 2.3: Test `PasswordAuthenticator` adapter
- [ ] 2.4: Implement `PasswordAuthenticator`
- [ ] 2.5: Test exception translation (JWT errors → AuthError)
- [ ] 2.6: Implement exception translation
- [ ] 2.7: Add structured logging to service layer
- [ ] 2.8: Integration test: login flow (happy path)
- [ ] 2.9: Wire up DI container
→ Stage for human review

## Phase 3: Integration (Coverage ≥90%)
- [ ] 3.1: Test Redis token storage integration
- [ ] 3.2: Implement Redis adapter
- [ ] 3.3: Test error handling (invalid creds, expired tokens, Redis failures)
- [ ] 3.4: Implement error responses with appropriate logging
- [ ] 3.5: Test retry logic for Redis connection failures
- [ ] 3.6: Implement retry with exponential backoff
→ Stage for human review

## Phase 4: Hardening (Coverage ≥90%)
- [ ] 4.1: Test logging output format and content
- [ ] 4.2: Add structured logging at all decision points
- [ ] 4.3: Test auth metrics (attempts, failures, latency)
- [ ] 4.4: Implement metrics emission
- [ ] 4.5: Test configuration validation
- [ ] 4.6: Implement fail-fast config validation
- [ ] 4.7: Security review (timing attacks, credential handling)
→ Stage for human review

## Phase 5: Polish (Coverage ≥90%)
- [ ] 5.1: Write module README
- [ ] 5.2: Document exception types and when they're raised
- [ ] 5.3: Document logging patterns and log analysis tips
- [ ] 5.4: Final coverage report verification (≥90%)
→ Stage for human review
```

---

## Adapting the Guide

This framework scales:

- **Small features (1-3 days):** Collapse Phases 3-4, minimal Phase 5
- **Medium features (1-2 weeks):** Follow as written
- **Large systems (2+ weeks):** Add sub-phases, consider separate plans per bounded context

The key invariants regardless of scale:
1. Tests before implementation
2. Interfaces before implementations
3. ≥90% coverage at every phase
4. Each phase ends with staged changes for human review
5. Errors and logging are explicit concerns, not afterthoughts