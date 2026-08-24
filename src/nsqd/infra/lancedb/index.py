from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, SupportsFloat, cast

from nsqd.ports import CorpusHit


def _cosine_distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0.0 or norm_r == 0.0:
        return 1.0
    return 1.0 - (dot / (norm_l * norm_r))


def _vector_values(value: object) -> list[float]:
    tolist = getattr(value, "tolist", None)
    raw = tolist() if callable(tolist) else value
    if not isinstance(raw, list):
        raise TypeError("embedding must be list-like")
    return [float(cast(SupportsFloat, item)) for item in raw]


def _snapshot_filter(snapshot_id: str) -> str:
    escaped = snapshot_id.replace("'", "''")
    return f"snapshot_id = '{escaped}'"


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
        "embedding dimension mismatch for the configured corpus index contract; "
        f"expected {expected_dimension}, got {actual_dimension}. "
        f"rebuild the corpus index for {model}."
    )


class LanceDBCorpusIndex:
    def __init__(
        self,
        path: Path,
        *,
        table_name: str = "nsqd_corpus",
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
    ) -> None:
        try:
            import lancedb
        except Exception as exc:  # pragma: no cover - optional dependency
            raise ImportError("lancedb is required for LanceDBCorpusIndex") from exc
        self._lancedb = lancedb
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._table_name = (
            _contract_table_name(table_name, embedding_model, embedding_dimension)
            if embedding_model is not None and embedding_dimension is not None
            else table_name
        )
        if hasattr(lancedb, "connect"):
            self._db = lancedb.connect(str(path))
        else:  # pragma: no cover - defensive for API changes
            raise AttributeError("lancedb has no supported connect API")

    def _key(self, snapshot_id: str, record_id: str) -> str:
        return json.dumps([snapshot_id, record_id], ensure_ascii=False, separators=(",", ":"))

    def _count_rows(self, table: Any, filter_expr: str) -> int:
        return int(table.count_rows(filter=filter_expr))

    def _get_table(self, dimension: int | None = None):
        try:
            return self._db.open_table(self._table_name)
        except Exception:
            if dimension is None:
                raise
            import pyarrow as pa

            schema = pa.schema(
                [
                    ("key", pa.string()),
                    ("snapshot_id", pa.string()),
                    ("record_id", pa.string()),
                    ("embedding", self._lancedb.vector(dimension)),
                ]
            )
            return self._db.create_table(self._table_name, schema=schema)

    def upsert(self, snapshot_id: str, record_id: str, vector: list[float]) -> None:
        import numpy as np

        _require_contract_dimension(
            self._embedding_dimension,
            len(vector),
            embedding_model=self._embedding_model,
        )
        table = self._get_table(len(vector))
        rows = [
            {
                "key": self._key(snapshot_id, record_id),
                "snapshot_id": snapshot_id,
                "record_id": record_id,
                "embedding": np.array(vector, dtype=float),
            }
        ]
        (
            table.merge_insert("key")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(rows)
        )

    def query(
        self,
        snapshot_id: str,
        vector: list[float],
        k: int,
        *,
        allowed_record_ids: frozenset[str] | None = None,
    ) -> list[CorpusHit]:
        if k <= 0:
            return []
        _require_contract_dimension(
            self._embedding_dimension,
            len(vector),
            embedding_model=self._embedding_model,
        )
        try:
            table = self._get_table()
        except Exception:
            return []
        filter_expr = _snapshot_filter(snapshot_id)
        row_count = self._count_rows(table, filter_expr)
        if row_count <= 0:
            return []
        search = table.search(vector, vector_column_name="embedding")
        search = search.where(filter_expr)
        rows = search.limit(row_count).to_list()
        scored: list[tuple[str, float]] = []
        for row in rows:
            record_id = str(row["record_id"])
            if allowed_record_ids is not None and record_id not in allowed_record_ids:
                continue
            stored = _vector_values(row["embedding"])
            scored.append((record_id, _cosine_distance(vector, stored)))
        scored.sort(key=lambda item: (item[1], item[0]))
        return [
            CorpusHit(record_id=record_id, distance=distance, rank=rank)
            for rank, (record_id, distance) in enumerate(scored[:k], start=1)
        ]
