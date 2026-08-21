# 005. Hybrid search with one-based RRF

## Status

Accepted

## Context

Users search the paper corpus with a text query. Lexical and semantic rankings disagree; a single list must be fused without privileging an arbitrary first hit.

## Decision

`SearchPapersUseCase` runs:

1. FTS on **title and abstract**
2. Vector search on **markdown** embeddings
3. Reciprocal Rank Fusion with **k = 60** and **rank starting at 1** (`enumerate(..., start=1)` in `compute_rrf_scores`)

Zero-based ranks are not compatibility policy. The bound oracle for the three approved papers (query `optimization algorithm`) is the full fused order and 8-decimal scores in `SEARCH.HYBRID.FTS_VECTOR_RRF.v1`.

## Consequences

- FTS does not search markdown; vectors do not search title/abstract records.
- Changing k or the rank origin requires a fact change, not a silent tweak.
