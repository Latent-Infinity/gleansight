# Gleansight agent API

The local Python API and `gleansight api` JSON CLI share one operation catalog. Use them for supported paper research and NSQD workflows. The catalog exposes operation descriptions, effects, approval requirements, and validated input schemas without opening storage or providers.

```bash
uv run gleansight api operations
uv run gleansight api operations --namespace papers
uv run gleansight api operations --with-schemas
uv run gleansight api describe papers.candidates.discover
uv run gleansight api call papers.candidates.discover --input-json '{"query":"graph neural networks","max_results":10}'
uv run gleansight api call papers.candidates.get --input-file request.json
```

The last command accepts `--input-file -` for stdin. Omit the input option for a request whose schema accepts `{}`. `operations` emits compact metadata by default; `--with-schemas` includes every input schema. Set `--repo-root PATH` to target a different repository root. `--config PATH`, `--nsqd-db PATH`, `--nsqd-index PATH`, and `--llm-base-url URL` select existing configuration and local resources. Use the same options before the subcommand. `gleansight api` prints one JSON envelope to stdout. Failed calls return nonzero; inspect the envelope's `error.code`, `message`, `retryable`, and any validation `details`.

```python
from pathlib import Path
from gleansight.api import ApiConfiguration, GleansightAPI

api = GleansightAPI(ApiConfiguration(repo_root=Path.cwd()))
paper_operations = api.operations("papers")
schema = api.describe("papers.candidates.discover").input_schema
result = api.call(
    "papers.candidates.discover", {"query": "graph neural networks", "max_results": 10}
)
if result.status == "error":
    raise RuntimeError(f"{result.error.code}: {result.error.message}")
```

Each result has `api_version: "1"`, `status`, and `operation`. Success has `data`; failure has `error`. Requests reject unknown fields and validate against the operation's JSON schema. Use `describe` on the installed version before building a payload; the schema is the authority for required fields and bounds. `operations` and `describe` have no storage or provider startup cost.

`effects` describes what a call may do: `read`, `write`, `external`, or `approval`. An approval operation requires explicit `--allow-approvals` or `ApiConfiguration(allow_approvals=True)` **and** human authorization for that specific action. The opt-in only enables the operation gate. In particular, `nsqd.corpus.acquire` with `human_decision` does not approve a digest; `nsqd.digests.approve` is separate. Never print runtime secrets or add credentials through an imaginary API operation. Live scholarly, PDF, embedding, and LLM work needs its configured provider. NSQD operator E requires explicit configuration; C, D, F, and G remain deferred.

Call `system.capabilities` to read configured operator allowlists, resolved resource paths, and provider metadata without starting providers or creating storage. It excludes credentials. A supported operator in the divergence schema can still be disabled by configuration.

Start with `operations --namespace papers` for discovery, import, pipeline jobs, analysis, prompts, projects/tags, search, synthesis, ideation, and index rebuild. Start with `operations --namespace nsqd` for skeleton, harvest, manifest-verified projection, map, diverge, ground, gate, rescore, ranking, acquisition, Tau, and persisted-resource reads. The [agent skill](../skills/gleansight/SKILL.md) routes those operation groups. Use returned IDs and paths between calls. Generated report bundles live under `output/<workflow>/<UTC>/`; preserve `archive/reviews/v1` as immutable evidence.
