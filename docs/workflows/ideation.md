# Project-wide ideation

Generate a bounded evidence map and draft research ideas from every paper attached to one project:

```bash
uv run python -m papers.cli ideate-project PROJECT_ID "What testable gaps remain?"
```

The command enumerates project membership directly. It does not use vector top-N retrieval. The
default maximum is 12 papers; a larger project fails with an explicit error unless `--max-papers`
is increased. Each readable Markdown document contributes bounded, section-aware excerpts with
stable IDs, UTF-8 byte offsets, exact-quote hashes, and coverage metadata. Missing Markdown and
partial selection are retained in the complete project inventory.

The configured `llm.default_profile` and `llm.default_model` are used by default. `--profile-id`,
`--model`, and `--critic-model` provide explicit overrides. Generation and critique have bounded
`--timeout-s` and `--max-tokens` values. Ideation makes exactly two model calls: generation, then a
fresh critic pass. There is no repair loop, paid-provider fallback, novelty claim, or approval gate.

Each run creates a unique ignored `output/project-ideation/<UTC-run-id>/` bundle:

- `evidence-map.json`: complete inventory, bounded excerpts, offsets, hashes, and coverage warning.
- `ideas.json`: source-bound evidence cards and zero to six draft ideas.
- `critique.json`: one keep/revise/reject review per known idea and validated deduplication links.
- `report.md`: human-readable evidence, ideas, separate critique, and limitations.
- `provenance.json`: models, call count, and explicit non-approval/non-search declarations.
- `manifest.json`: SHA-256 hashes for accidental-tamper detection, not authenticated provenance.

The report only describes selected excerpts as analyzed. It is not a full-text systematic review or
an exhaustive literature search.

## Frozen selected-idea planning

Create an investigation plan for one explicit draft idea:

```bash
uv run python -m papers.cli plan-idea \
  output/project-ideation/RUN_ID IDEA_ID
```

`plan-idea` verifies the source manifest before making a model call. It uses only saved exact
excerpts cited by the selected idea and does not query the vector index, project store, paper store,
or Markdown blobs. The response is validated by the shared replication-first investigation schema,
including source closure and the prohibition on unsupported `verified` work. It writes a separate
`output/selected-idea-plan/<UTC-run-id>/` bundle containing `investigation-plan.json`, `report.md`,
`provenance.json`, and `manifest.json`.

Selecting an idea on the command line is an operator or QA action. It does not record human
endorsement, execute an experiment, admit evidence, or activate any NS/QD operator.
