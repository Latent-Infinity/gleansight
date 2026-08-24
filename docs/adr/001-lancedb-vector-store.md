# 001. LanceDB for the paper vector index

## Status

Accepted

## Context

Paper search needs an on-disk vector index that stays local, replaces without a server, and matches the embedder dimension. A hosted vector database would fight the local-first product constraint.

## Decision

Use LanceDB as the vector store behind the `VectorIndex` port (`src/papers/infra/lancedb/`). Embeddings are produced by the OpenAI-compatible Ollama embedder (`qwen3-embedding:latest`, 4096-d, L2-normalized) and upserted after convert/embed. Hybrid search queries this index on **markdown**, not title/abstract. Changing the embedding family requires rebuilding the index.

NS/QD corpus embeddings use the same embedder behind a separate port in `src/nsqd/infra/lancedb/`. Hermetic tests may inject a hash embedder.

## Consequences

- No network dependency for nearest-neighbor search.
- Index files live under the configured LanceDB directory and can be rebuilt (`rebuild-index`).
- Schema and metric choices stay in the adapter; domain code never imports `lancedb`.
