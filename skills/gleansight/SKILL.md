---
name: gleansight
description: Run Gleansight's local paper research and NSQD discovery workflows through its public Python API or JSON CLI. Use for discovering, importing, analyzing, querying, synthesizing, or governing Gleansight research artifacts.
---

# Gleansight workflows

Use the public operation catalog. From the repository, `uv run gleansight api operations` lists compact metadata; add `--with-schemas` for every input schema. `uv run gleansight api describe OPERATION` returns one full schema and effects; `uv run gleansight api call OPERATION --input-json '{...}'` invokes it. `--input-file PATH` also accepts `-` for stdin. The Python equivalent is `GleansightAPI(ApiConfiguration(...)).operations()`, `.describe(name)`, and `.call(name, parameters)` from `gleansight.api`. Metadata discovery does not initialize storage or providers.

Choose an operation by its description, inspect its schema before constructing inputs, and check the returned `status`. All calls return a versioned `ok` or `error` envelope; CLI errors exit nonzero. Use stable operation names, never internal stores, as the mutation interface. For details specific to a paper task, read [references/papers.md](references/papers.md). For NSQD, read [references/nsqd.md](references/nsqd.md). The complete embedded and CLI contract is in [docs/agent-api.md](../../docs/agent-api.md).

Call `system.capabilities` to inspect configured operator allowlists, resolved resource paths, and provider metadata. It reads settings without creating storage or connecting to providers and does not return credentials. A supported operator in a request schema may still be disabled by configuration.

Set `--repo-root` to the intended project root when running elsewhere. Optional `--config`, `--nsqd-db`, `--nsqd-index`, and `--llm-base-url` select existing configuration and local resources. Live discovery, downloads, embeddings, and model work need their configured providers; do not print secrets or invent credential-write operations. Reports use `output/<workflow>/<UTC>/` where the workflow provides a report bundle.

Read `effects` before calling. An `approval` effect requires a human to authorize that **specific** action and explicit `--allow-approvals` or `ApiConfiguration(allow_approvals=True)` for that call. An acquisition `human_decision` field records the supplied decision; it does not approve a projection digest. Preserve immutable `archive/reviews/v1` evidence and use only verified manifest/projection inputs.
