# Library Standards

Confirmed libraries for this project (per design doc and Phase 0 decision):

| Category | Preferred | Avoid | Rationale |
|---|---|---|---|
| Env/Deps | uv | pip-tools, poetry | Fast, reproducible workflows |
| Lint/Format | ruff | flake8, black | Single tool, fast, consistent |
| CLI Framework | typer | argparse, click | Type hints, auto-help, less boilerplate |
| Terminal Output | rich | colorama, print | Tables, progress, consistent styling |
| UI | flet | tkinter, qt | Thin client, fast iteration |
| PDF → Text | docling | custom parsers | Higher quality extraction |
| Embeddings | sentence-transformers | custom embeddings | Proven, configurable |
| Vector DB | lancedb | faiss-only | Vector store with persistence |
| Metadata Store (ORM) | Piccolo (SQLite backend) | raw SQL in app code | ORM models + migrations on SQLite |

Notes:
- No deviations are expected unless explicitly documented here.
