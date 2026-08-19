# Development Plan: RAG Q&A and Synthesis Feature

**Status:** Superseded (2026-08-18). Landed synthesis UI/CLI stay experimental (open-work V0.4 = B). Productization is a future authorized v1.1 plan, not `docs/development-plan-open-work.md`.
**Guide Version:** 1.x (layer-based Phase 10).
**Plan Set:** gleansight
**Supersedes:** none
**Superseded by:** `docs/development-plan-open-work.md`

This plan details the addition of a Retrieval-Augmented Generation (RAG) feature for conversational Q&A and idea synthesis. It follows the project's established development guide, including a strict Test-Driven Development (TDD) approach.

## Audit status (2026-08-17)

Checked against the current tree. `[x]` means the criterion is met; `[ ]` means missing or only partial.

| Phase | Status | Remaining gaps |
|---|---|---|
| 10 RAG & Synthesis | Mostly complete | Retrieval is vector-only (not FTS+RRF hybrid); tag scoping unimplemented; prompt is an inline string; UI has no project/tag scope and sources are not links |

`papers ask --project` is wired to `PiccoloPaperProjectStore`. Process checkbox (**Stage changes for human review**) stays unchecked.

---

## Phase 10: RAG & Synthesis (Coverage ≥90%)

This phase introduces the backend use case for synthesis, a new dedicated UI screen, and a corresponding CLI command.

### Task 10.1: Test Synthesis Use Case

**Type:** Test

**Description:**
Write unit and integration tests for the new `SynthesizeFromCorpusUseCase`. These tests will validate the entire RAG pipeline from question to context retrieval and prompt generation, using mocked external dependencies.

**Acceptance Criteria:**
- [ ] Tests verify a user's question is correctly embedded and used for a hybrid search to retrieve relevant document chunks.
- [x] Tests verify that retrieved content is correctly assembled into a context block for the LLM.
- [x] Tests verify the LLM is called with a correctly formatted prompt containing both the retrieved context and the original question.
- [x] Tests verify the use case returns both a generated answer and a list of source paper IDs for provenance.
- [ ] Tests verify that scoping by project or tags correctly limits the document search space.
- [x] Tests pass with ≥90% coverage maintained.

**Files Affected (optional):**
- `tests/app/use_cases/test_synthesis.py` (create)

---

### Task 10.2: Implement Synthesis Use Case

**Type:** Implement

**Description:**
Implement the `SynthesizeFromCorpusUseCase` in the application layer. This use case will orchestrate the full RAG pipeline, reusing existing infrastructure components.

**Acceptance Criteria:**
- [x] The use case orchestrates the Retrieve-Augment-Generate flow.
- [ ] It reuses existing embedder and search adapters.
- [ ] It introduces a new prompt template specifically for synthesis tasks.
- [x] All tests from Task 10.1 pass.
- [x] Tests pass with ≥90% coverage maintained.

**Files Affected (optional):**
- `src/papers/app/use_cases/synthesis.py` (create)

---

### Task 10.3: Test Synthesis UI Screen

**Type:** Test

**Description:**
Write tests for the new "Synthesis" UI screen. These tests will mock the `SynthesizeFromCorpusUseCase` to verify UI logic, event handling, and state management.

**Acceptance Criteria:**
- [ ] Tests verify the screen contains an input for the question and controls for scoping.
- [x] Tests verify the use case is called with the correct parameters when the user submits a question.
- [x] Tests verify the generated answer is displayed in a markdown-capable component.
- [ ] Tests verify the list of source papers is displayed and links correctly.
- [x] Tests pass with ≥90% coverage maintained.

**Files Affected (optional):**
- `tests/ui/test_synthesis_screen.py` (create)

---

### Task 10.4: Implement Synthesis UI Screen

**Type:** Implement

**Description:**
Build the new "Synthesis" screen using Flet, providing a dedicated interface for the Q&A feature.

**Acceptance Criteria:**
- [x] A new "Synthesis" entry is added to the main UI navigation in `src/papers/ui/app.py`.
- [ ] The screen allows users to input a question and optionally select a scope (e.g., a project).
- [x] The screen displays a loading indicator while the use case is running.
- [x] The final answer and its sources are clearly presented.
- [x] All tests from Task 10.3 pass.
- [x] Tests pass with ≥90% coverage maintained.

**Files Affected (optional):**
- `src/papers/ui/screens/synthesis.py` (create)
- `src/papers/ui/app.py` (modify)

---

### Task 10.5: Test Synthesis CLI Command

**Type:** Test

**Description:**
Write integration tests for a new `papers ask` command to ensure it correctly calls the synthesis use case and handles arguments.

**Acceptance Criteria:**
- [x] Tests verify the `ask` command is registered correctly within the Typer application.
- [x] Tests verify the command calls `SynthesizeFromCorpusUseCase` with the question text.
- [x] Tests verify that `--project` and other scoping flags are parsed and passed to the use case.
- [x] Tests check for correct output formatting and error handling.
- [x] Tests pass with ≥90% coverage maintained.

**Files Affected (optional):**
- `tests/cli/test_synthesis_commands.py` (create)

---

### Task 10.6: Implement Synthesis CLI Command

**Type:** Implement

**Description:**
Implement the `papers ask "[QUESTION]"` command, providing a headless interface for the RAG feature.

**Acceptance Criteria:**
- [x] The `papers ask` command is added to a new `src/papers/cli/commands/synthesis.py` module and registered in the main app.
- [x] It accepts a question and optional scoping flags.
- [x] The answer and source papers are printed to the console using `rich`.
- [x] All tests from Task 10.5 pass.
- [x] Tests pass with ≥90% coverage maintained.

**Files Affected (optional):**
- `src/papers/cli/commands/synthesis.py` (create)
- `src/papers/cli/app.py` (modify)

---

**Phase 10 Exit Criteria:**
- [ ] New `SynthesizeFromCorpusUseCase` is fully implemented and tested.
- [ ] New "Synthesis" UI screen is functional and tested.
- [x] New `papers ask` CLI command is functional and tested.
- [x] All tests pass and overall coverage remains ≥90%.
- [ ] **Stage changes for human review**
