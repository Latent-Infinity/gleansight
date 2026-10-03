# Local MCP adapter

The adapter exposes the existing operation registry through stdio. Install the project with
`uv sync --locked`, then configure your MCP client to start:

```sh
uv run --project /absolute/path/to/gleansight gleansight-mcp \
  --repo-root /absolute/path/to/workspace --namespace papers
```

Repeat `--namespace` to expose several namespaces, or repeat `--tool` to select exact operation
names. When both are supplied, their intersection is exposed. Unknown explicit tool names cause
startup to exit with status 2. Omit both options to expose the full registry. Discovery does not
create a database or contact providers.

`--config`, `--nsqd-db`, and `--nsqd-index` select the same workspace resources as the Python
API and JSON CLI. Use absolute paths in client configuration. Credentials remain in the
workspace's normal configuration; tool arguments do not configure another credential store.

Tool input schemas, names, effects, and human-approval requirements come from registered
operations. Calls return the same success/error envelope in both structured content and text.
Unavailable tools and invalid input produce errors without invoking their handlers. The MCP
annotations describe effects; approval is enforced by the underlying runtime. Approval-bearing
operations refuse by default. `--allow-approvals` enables the existing explicit approval path
for an authorized operator session.

Provider messages go to stderr while stdout carries protocol messages. Calls are serialized
within a server, and API calls preserve workspace database bindings. A managed worker still
owns job execution until its reservation ends; MCP does not bypass that guard.

The dependency is pinned to `mcp==2.3.0`. Integration tests use its official Python client over
an actual stdio subprocess and negotiate protocol revision `2025-11-25`. They cover schema
discovery, successful calls, validation failures, unavailable tools, approval refusal, and
noisy provider output. This is a local stdio transport; hosted transports are a separate
roadmap decision.
