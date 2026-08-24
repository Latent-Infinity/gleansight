from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from papers.app import ports


@dataclass(frozen=True)
class LanceDBConfig:
    path: Path
    table_name: str = "paper_embeddings"
    embedding_model: str | None = None
    embedding_dimension: int | None = None


def _contract_table_name(base_name: str, model: str, dimension: int) -> str:
    digest = hashlib.sha256(f"{model}:{dimension}".encode()).hexdigest()[:16]
    return f"{base_name}__{digest}"


def _require_contract_dimension(
    expected_dimension: int | None,
    actual_dimension: int,
    *,
    embedding_model: str | None,
) -> None:
    if expected_dimension is None or actual_dimension == expected_dimension:
        return
    model = embedding_model or "the configured embedding model"
    raise ValueError(
        "embedding dimension mismatch for the configured index contract; "
        f"expected {expected_dimension}, got {actual_dimension}. "
        f"rebuild the index for {model}."
    )


class LanceDBVectorIndex(ports.VectorIndex):
    def __init__(self, config: LanceDBConfig) -> None:
        try:
            import lancedb
        except Exception as exc:  # pragma: no cover - optional dependency
            raise ImportError("lancedb is required for LanceDBVectorIndex") from exc
        self._lancedb: Any = lancedb
        self._config = config
        self._table_name = (
            _contract_table_name(
                config.table_name,
                config.embedding_model,
                config.embedding_dimension,
            )
            if config.embedding_model is not None and config.embedding_dimension is not None
            else config.table_name
        )
        self._db: Any
        connect = getattr(self._lancedb, "connect", None)
        if callable(connect):
            self._db = connect(str(config.path))
        else:
            lancedb_connect = getattr(self._lancedb, "lancedb_connect", None)
            db_module = getattr(self._lancedb, "db", None)
            db_connect = getattr(db_module, "connect", None)
            db_lancedb_connect = getattr(db_module, "lancedb_connect", None)
            if callable(lancedb_connect):
                self._db = lancedb_connect(str(config.path))
            elif callable(db_connect):
                self._db = db_connect(str(config.path))
            elif callable(db_lancedb_connect):
                self._db = db_lancedb_connect(str(config.path))
            else:  # pragma: no cover - defensive for API changes
                raise AttributeError("lancedb has no supported connect API")

    def _get_table(self, dimension: int | None = None):
        try:
            return self._db.open_table(self._table_name)
        except Exception:
            if dimension is None:
                raise
            import pyarrow as pa

            schema = pa.schema(
                [
                    ("paper_id", pa.string()),
                    ("embedding", self._lancedb.vector(dimension)),
                    ("updated_at", pa.string()),
                ]
            )
            return self._db.create_table(self._table_name, schema=schema)

    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        import numpy as np

        _require_contract_dimension(
            self._config.embedding_dimension,
            len(embedding),
            embedding_model=self._config.embedding_model,
        )
        table = self._get_table(len(embedding))
        rows = [
            {
                "paper_id": paper_id,
                "embedding": np.array(embedding, dtype=float),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ]
        (
            table.merge_insert("paper_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(rows)
        )

    def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        if allowed_ids == set():
            return []
        _require_contract_dimension(
            self._config.embedding_dimension,
            len(embedding),
            embedding_model=self._config.embedding_model,
        )
        try:
            table = self._get_table()
        except Exception:
            return []
        search = table.search(embedding, vector_column_name="embedding")
        if allowed_ids is not None:
            quoted_ids = ", ".join(
                f"'{paper_id.replace(chr(39), chr(39) * 2)}'" for paper_id in sorted(allowed_ids)
            )
            search = search.where(f"paper_id IN ({quoted_ids})")
        results = search.limit(limit).to_list()
        output: list[tuple[str, float]] = []
        for row in results:
            score = float(row.get("_distance", row.get("score", 0.0)))
            output.append((row["paper_id"], score))
        return output

    def reset(self) -> None:
        try:
            self._db.drop_table(self._table_name)
        except Exception:
            return None
