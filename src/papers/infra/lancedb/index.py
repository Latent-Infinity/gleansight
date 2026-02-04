from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from papers.app import ports


@dataclass(frozen=True)
class LanceDBConfig:
    path: Path
    table_name: str = "paper_embeddings"


class LanceDBVectorIndex(ports.VectorIndex):
    def __init__(self, config: LanceDBConfig) -> None:
        try:
            import lancedb
        except Exception as exc:  # pragma: no cover - optional dependency
            raise ImportError("lancedb is required for LanceDBVectorIndex") from exc
        self._lancedb = lancedb
        self._config = config
        if hasattr(lancedb, "connect"):
            self._db = lancedb.connect(str(config.path))
        elif hasattr(lancedb, "lancedb_connect"):
            self._db = lancedb.lancedb_connect(str(config.path))
        elif hasattr(lancedb, "db") and hasattr(lancedb.db, "connect"):
            self._db = lancedb.db.connect(str(config.path))
        elif hasattr(lancedb, "db") and hasattr(lancedb.db, "lancedb_connect"):
            self._db = lancedb.db.lancedb_connect(str(config.path))
        else:  # pragma: no cover - defensive for API changes
            raise AttributeError("lancedb has no supported connect API")

    def _get_table(self, dimension: int | None = None):
        try:
            return self._db.open_table(self._config.table_name)
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
            return self._db.create_table(self._config.table_name, schema=schema)

    def upsert(self, paper_id: str, embedding: list[float]) -> None:
        import numpy as np

        table = self._get_table(len(embedding))
        table.add(
            [
                {
                    "paper_id": paper_id,
                    "embedding": np.array(embedding, dtype=float),
                    "updated_at": datetime.now().isoformat(),
                }
            ]
        )

    def query(self, embedding: list[float], limit: int) -> list[tuple[str, float]]:
        try:
            table = self._get_table()
        except Exception:
            return []
        results = table.search(embedding, vector_column_name="embedding").limit(limit).to_list()
        output: list[tuple[str, float]] = []
        for row in results:
            score = float(row.get("_distance", row.get("score", 0.0)))
            output.append((row["paper_id"], score))
        return output

    def reset(self) -> None:
        try:
            self._db.drop_table(self._config.table_name)
        except Exception:
            return None
