# Audit Review Standards

Last updated: 2026-01-28

This document defines a systematic, plan-agnostic methodology for auditing implementations against any development plan's acceptance criteria. Use this framework to ensure complete coverage and identify gaps regardless of plan structure or project phase.

---

## Purpose

- Provide a repeatable audit methodology for any task or deliverable
- Ensure systematic verification of acceptance criteria from any development plan
- Create traceability between plan → tests → implementation → documentation
- Identify gaps systematically with actionable fix plans
- Maintain quality gates throughout development

---

## Core Audit Methodology

### Step 1: Extract Acceptance Criteria

**Objective:** Identify all verifiable requirements from the plan.

**Process:**
1. Read the task/deliverable description from the development plan
2. Extract explicit acceptance criteria (usually marked with `[ ]` checkboxes)
3. Identify implicit requirements (e.g., "implement X" implies tests for X)
4. Classify each criterion by type (see Verification Categories below)
5. Note any coverage targets or quality metrics specified

**Output:** Numbered list of criteria with types:
```
1. [Test] Unit tests cover Model X validation [Coverage: 95%]
2. [Implement] Model X handles invalid inputs [Error: ValidationError]
3. [Document] Model X fields documented in docstrings
4. [Quality] All tests pass, no linting errors
```

---

### Step 2: Build Traceability Matrix

**Objective:** Map each criterion to concrete files and verification evidence.

**Process:**
1. For each criterion, identify the expected artifacts:
   - **Test criteria:** Which test file(s) and test function(s)?
   - **Implementation criteria:** Which source file(s) and symbols (class/function)?
   - **Documentation criteria:** Which doc file(s) or docstrings?
   - **Quality criteria:** Which tool(s) and command(s)?

2. Create a mapping table:
   ```
   Criterion ID | Type    | Expected Artifact                | Exists? | Location/Evidence
   -------------|---------|----------------------------------|---------|------------------
   1            | Test    | tests/test_model.py::test_req    | ✅      | tests/test_model.py:45-62
   2            | Impl    | src/model.py::Model.validate     | ✅      | src/model.py:123-145
   3            | Doc     | Model class docstring            | ❌      | Missing
   4            | Quality | ruff check, pytest               | ✅      | Exit code 0
   ```

3. For missing artifacts, mark as gaps for Step 4

**Output:** Complete traceability matrix with ✅/❌ status for each criterion

---

### Step 3: Execute Verification by Category

**Objective:** Systematically verify each category of requirement.

Apply the appropriate verification standard based on criterion type:

#### 3.1 Test Verification

For any criterion requiring tests:

- [ ] **Test exists** and is discoverable by test runner
- [ ] **Test name** clearly describes what it verifies
- [ ] **Test is atomic** (tests one behavior/requirement)
- [ ] **Test has assertions** (not just execution without verification)
- [ ] **Test covers success path** (valid inputs → expected outputs)
- [ ] **Test covers failure paths** (invalid inputs → expected errors)
- [ ] **Test uses appropriate fixtures/mocks** (no external dependencies unless integration test)
- [ ] **Test is marked appropriately** (@pytest.mark.unit, @pytest.mark.integration, etc.)
- [ ] **Test passes** in current codebase state

**For specific test categories:**

**Data Models/Value Objects:**
- [ ] Required fields: Test fails with missing/empty required fields
- [ ] Optional fields: Test succeeds with missing optional fields
- [ ] Enums/literals: Test all valid values succeed, invalid values fail
- [ ] Invariants: Test cross-field validation rules
- [ ] Serialization: Test to/from dict, JSON, or wire format (if applicable)
- [ ] Equality: Test equality semantics if custom `__eq__` defined

**Business Logic/Policies:**
- [ ] Pure functions: No I/O, deterministic results
- [ ] Rule validation: Both allowed and disallowed cases tested
- [ ] Edge cases: Boundary values, empty inputs, null handling
- [ ] State transitions: All valid transitions succeed, invalid fail
- [ ] Idempotency: Repeated calls with same input produce same result (if required)

**Error Handling:**
- [ ] Each error type has dedicated test
- [ ] Error raised by realistic triggering condition (not just instantiation)
- [ ] Error message/attributes verified in assertions
- [ ] Error inheritance chain correct (if using hierarchy)

**Integration/Adapters:**
- [ ] Happy path integration test exists
- [ ] Error path tests (network failure, timeout, invalid response)
- [ ] Uses test doubles (fakes/mocks) or test environment
- [ ] Marked appropriately for CI (may be skipped in unit-only runs)
- [ ] Cleans up resources (connections, files, state)

#### 3.2 Implementation Verification

For any criterion requiring code implementation:

- [ ] **Code exists** at expected location (file path, symbol name)
- [ ] **Implements specified interface/protocol** (if applicable)
- [ ] **Handles specified inputs** (signature matches requirement)
- [ ] **Produces specified outputs** (return types match requirement)
- [ ] **Raises specified errors** (error handling as documented)
- [ ] **No obvious bugs** (logic errors, off-by-one, null derefs)
- [ ] **Follows project coding standards** (naming, formatting, style)
- [ ] **No security vulnerabilities** (see Security Verification below)
- [ ] **Appropriate logging** (see Logging Verification below)
- [ ] **Covered by tests** from Step 3.1

**Implementation Anti-Patterns to Flag:**
- [ ] No hardcoded configuration (use environment/config)
- [ ] No caught exceptions without logging or re-raising
- [ ] No business logic in infrastructure/adapter layers
- [ ] No I/O operations in domain/business logic layers
- [ ] No mutable default arguments in function signatures
- [ ] No God objects (>10 methods or >500 LOC in single class)
- [ ] No functions >100 lines (consider refactoring)

#### 3.3 Documentation Verification

For any criterion requiring documentation:

- [ ] **Documentation exists** at expected location
- [ ] **Documentation is current** (matches implemented behavior)
- [ ] **Covers all required topics** per criterion
- [ ] **Includes examples** (code samples, usage patterns)
- [ ] **Describes error conditions** (what errors, when, how to handle)
- [ ] **Links to related documentation** (cross-references)

**Docstring Standards:**
- [ ] Public APIs have docstrings (modules, classes, functions)
- [ ] Docstrings describe purpose (what/why, not just how)
- [ ] Parameters documented (name, type, description)
- [ ] Return values documented (type, description)
- [ ] Exceptions documented (which errors, under what conditions)
- [ ] Examples provided for non-obvious usage

**Project Documentation:**
- [ ] README exists with setup/usage instructions
- [ ] Architecture documentation matches implementation
- [ ] Error handling strategy documented (exception hierarchy)
- [ ] Configuration options documented (env vars, files, defaults)
- [ ] Logging patterns documented (levels, format, interpretation)

#### 3.4 Interface/Protocol Verification

If plan specifies interfaces, protocols, or ABCs:

- [ ] **Interface defined** with all required methods
- [ ] **Type hints complete** (parameters and return types)
- [ ] **Docstrings present** describing contract
- [ ] **Contract tests exist** verifying interface compliance
- [ ] **All implementations** pass contract tests
- [ ] **Dependency injection** uses interface types, not concrete classes
- [ ] **No protocol violations** (implementations don't add extra public methods outside protocol)

#### 3.5 Configuration Verification

If plan includes configuration requirements:

- [ ] **Required configuration** explicitly validated at startup
- [ ] **Validation tests** cover missing, invalid, and out-of-range values
- [ ] **Fail-fast behavior** (invalid config stops execution with clear error)
- [ ] **Configuration sources** documented (env vars, files, CLI args, defaults)
- [ ] **Secrets not hardcoded** (loaded from environment or secrets manager)
- [ ] **Configuration errors** logged at appropriate level (CRITICAL for startup failures)
- [ ] **Default values** documented and sensible

#### 3.6 Logging Verification

If plan requires logging:

- [ ] **Logging configured** (handler, formatter, level)
- [ ] **Structured logging** used (key-value pairs, not string interpolation)
- [ ] **Appropriate levels** used per event type:
  - DEBUG: Entry/exit of functions, detailed flow
  - INFO: Business events, successful operations
  - WARNING: Recoverable errors, retries, deprecated usage
  - ERROR: Failures, exceptions
  - CRITICAL: System-wide failures
- [ ] **Context included** (request ID, user ID, correlation ID, etc.)
- [ ] **No sensitive data** in logs (PII, credentials, tokens, keys)
- [ ] **Logging tested** (verify log messages and levels in tests)
- [ ] **Log format consistent** (parseable by log aggregation tools)

#### 3.7 Security Verification

For any code interfacing with external inputs or systems:

- [ ] **Input validation** at system boundaries (APIs, CLI, file parsing)
- [ ] **No injection vulnerabilities:**
  - [ ] SQL: Use parameterized queries, not string concatenation
  - [ ] Command: Avoid shell=True, sanitize subprocess inputs
  - [ ] Path: Validate file paths, prevent traversal (../)
  - [ ] XSS: Escape HTML/JS outputs (if web app)
- [ ] **Secrets management:**
  - [ ] No credentials in code or git history
  - [ ] Secrets loaded from environment or secrets manager
  - [ ] Secrets not logged or included in error messages
- [ ] **Authentication/authorization** checked before privileged operations
- [ ] **Dependency scanning** for known vulnerabilities (if applicable)
- [ ] **Rate limiting** on public endpoints (if applicable)

#### 3.8 Quality Gates Verification

For any task/deliverable, verify these baseline quality gates:

**Linting:**
- [ ] `ruff check .` (or equivalent linter) passes with no errors
- [ ] `ruff format --check .` (or equivalent formatter) passes

**Type Checking:**
- [ ] Type checker (`ty check`) passes with no errors
- [ ] All public APIs have type hints

**Testing:**
- [ ] All tests pass (`pytest`, `npm test`, etc.)
- [ ] No skipped tests without justification
- [ ] No flaky tests (tests that pass/fail non-deterministically)

**Coverage:**
- [ ] Coverage meets target specified in plan (typically ≥90%)
- [ ] Coverage report generated and reviewed
- [ ] Critical paths have higher coverage (≥95% for domain/business logic)
- [ ] Coverage excludes only documented exceptions

**Import/Build:**
- [ ] All modules importable without error
- [ ] Build succeeds (if compiled language)
- [ ] No circular dependencies

**Git State:**
- [ ] Changes staged as expected by plan (if staging required)
- [ ] No unintended files staged (check .gitignore)
- [ ] No large binary files committed
- [ ] No sensitive files in history

---

### Step 4: Record Gaps Systematically

**Objective:** Document all gaps with sufficient detail for remediation.

For each criterion that fails verification:

**Required Gap Information:**
```markdown
### Gap: [Task ID] - [Criterion Number]

**Criterion:** [Exact text of acceptance criterion]

**Status:** Not Started | Partially Complete | Blocked

**Expected:**
[What should exist or be true]

**Actual:**
[What currently exists or is true]

**Evidence:**
- Expected location: [file path, symbol, line numbers]
- Actual state: [file doesn't exist | symbol missing | test fails | etc.]
- Related files: [any relevant context]

**Impact:** Critical | High | Medium | Low
[Why this gap matters - affects security, blocks other tasks, breaks functionality, etc.]

**Root Cause:** [If known - missing implementation, incorrect logic, outdated docs, etc.]

**Fix Plan:**
1. [Specific action to address gap]
2. [Another action]
3. [Verification step]

**Estimated Complexity:** Trivial | Simple | Moderate | Complex
[Helps prioritize gaps]

**Dependencies:** [Any other gaps or tasks that must be resolved first]

**Owner:** [Who will fix this - can be "Unassigned"]
```

**Gap Prioritization:**
- **Critical:** Security vulnerability, data loss risk, blocks all other work
- **High:** Core functionality broken, blocks dependent tasks, test coverage <90%
- **Medium:** Non-critical feature incomplete, documentation missing, minor bugs
- **Low:** Polish items, nice-to-have improvements, documentation enhancements

---

### Step 5: Generate Audit Report

**Objective:** Provide clear status and actionable next steps.

**Report Structure:**

```markdown
# Audit Report: [Task/Deliverable Name]

**Date:** YYYY-MM-DD
**Task ID:** [From development plan]
**Auditor:** [Agent or human name]
**Plan Reference:** [Path to development plan, section/phase]

---

## Executive Summary

- **Total Criteria:** [N]
- **Verified Complete:** [N] ([XX%])
- **Gaps Identified:** [N] ([XX%])
  - Critical: [N]
  - High: [N]
  - Medium: [N]
  - Low: [N]

**Overall Status:** ✅ Ready for Review | ⚠️ Gaps Require Attention | ❌ Significant Work Remaining

---

## Quality Gates

| Gate | Command/Tool | Target | Actual | Status |
|------|--------------|--------|--------|--------|
| Linting | `ruff check .` | 0 errors | [N] errors | ✅/❌ |
| Formatting | `ruff format --check .` | Formatted | [status] | ✅/❌ |
| Type Check | `ty check` | 0 errors | [N] errors | ✅/❌ |
| Tests Pass | `pytest -q` | 100% pass | [XX%] pass | ✅/❌ |
| Coverage | `pytest --cov` | ≥90% | [XX%] | ✅/❌ |
| Import | `python -c "import module"` | Success | [status] | ✅/❌ |

---

## Traceability Matrix

| # | Criterion | Type | Expected Artifact | Status | Evidence/Gap Reference |
|---|-----------|------|-------------------|--------|------------------------|
| 1 | [criterion text] | Test | tests/test_x.py::test_y | ✅ | tests/test_x.py:45-62 |
| 2 | [criterion text] | Impl | src/x.py::Class.method | ❌ | Gap #1 |
| 3 | [criterion text] | Doc | README.md section | ⚠️ | Gap #2 |

Legend: ✅ Complete | ⚠️ Partial | ❌ Missing | 🚫 Blocked

---

## Critical Gaps Requiring Immediate Attention

[List only Critical and High priority gaps with fix plans]

---

## Complete Gap Details

[Full gap records from Step 4, organized by priority]

---

## Recommendations

**For Human Review:**
- [Specific questions or decisions needed]
- [Areas requiring domain expertise]

**For Immediate Action:**
1. [Most critical gap to address first]
2. [Next priority]

**Before Proceeding:**
- [ ] [Prerequisite that must be met]
- [ ] [Another prerequisite]

**Ready for Next Stage:** Yes | No | Conditional

---

## Appendix: Full Verification Results

[Detailed results for each verification category from Step 3]
```

---

## Audit Frequency and Triggers

**When to Audit:**

1. **After each task completion** (before marking task as done)
2. **Before staging changes** for human review
3. **Before declaring a phase/milestone complete**
4. **When tests start failing** (regression audit)
5. **When requirements change** (re-audit affected criteria)
6. **On explicit request** (ad-hoc audit)

**Audit Scope:**

- **Task-level:** Verify criteria for single task only
- **Phase-level:** Verify all tasks in a phase, check phase-level criteria
- **Full audit:** Verify entire plan, all phases, cumulative coverage

---

## Success Criteria for Audit Completion

An audit is complete when:

- [ ] All criteria extracted from plan (Step 1 complete)
- [ ] Traceability matrix 100% populated (Step 2 complete)
- [ ] All verification categories executed (Step 3 complete)
- [ ] All gaps documented with fix plans (Step 4 complete)
- [ ] Audit report generated (Step 5 complete)
- [ ] Quality gates status determined
- [ ] Recommendations provided for next steps

An implementation is audit-passing when:

- [ ] All criteria verified complete (✅ in traceability matrix)
- [ ] All quality gates passing
- [ ] Zero Critical gaps, zero High gaps (or approved exceptions)
- [ ] Coverage meets target from plan
- [ ] Ready for human review or next stage

---

## Templates

### Quick Audit Checklist

Use this for task-level audits:

```markdown
## Quick Audit: [Task ID]

**Criteria Verification:**
- [ ] Criterion 1: [status]
- [ ] Criterion 2: [status]
- [ ] Criterion N: [status]

**Quality Gates:**
- [ ] Linting passes
- [ ] Type checking passes
- [ ] All tests pass
- [ ] Coverage ≥ target
- [ ] Imports work

**Gaps:** [N] ([list gap IDs or "None"])

**Status:** ✅ Complete | ⚠️ Needs work | ❌ Blocked

**Next Action:** [What needs to happen]
```

---

## Audit Agent Instructions

When performing an audit as an AI agent:

1. **Be systematic:** Follow all 5 steps in order, don't skip
2. **Be thorough:** Check every criterion, run every verification
3. **Be specific:** Use exact file paths, line numbers, function names
4. **Be objective:** Report what is, not what you assume or hope
5. **Be actionable:** Every gap needs a concrete fix plan
6. **Be honest:** If uncertain, mark as "Requires Human Review"
7. **Prefer automated verification:** Run tools, don't just read code
8. **Read before verifying:** Use Read tool to inspect actual file contents
9. **Test before claiming coverage:** Run tests, check exit codes
10. **Document evidence:** Link to specific lines, paste relevant snippets

**Anti-patterns for agents:**
- ❌ Assuming tests exist because implementation exists
- ❌ Marking criteria complete without running verification commands
- ❌ Skipping security verification because "it looks safe"
- ❌ Reporting gaps without fix plans
- ❌ Using vague evidence ("somewhere in src/")
- ❌ Ignoring quality gate failures ("only 2 linting errors")
- ❌ Glossing over missing documentation ("code is self-explanatory")

---

## Maintenance

This audit framework should be reviewed and updated:

- When new verification categories are needed
- When new quality gates are added to the project
- When audit reports consistently miss certain gap types
- When feedback indicates audit process is unclear or incomplete

Last reviewed: 2026-01-28
