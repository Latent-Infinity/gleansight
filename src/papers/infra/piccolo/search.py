from __future__ import annotations

from piccolo.engine.sqlite import TransactionType
from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync

from papers.infra.piccolo.fts import literal_fts_query
from papers.infra.piccolo.tables import Paper


class PiccoloPaperFTS:
    def __init__(self, *, fail_after_inserts: int | None = None) -> None:
        self._fail_after_inserts = fail_after_inserts

    def rebuild(self) -> int:
        async def rebuild_in_transaction() -> int:
            database = Paper._meta.db
            async with database.transaction(transaction_type=TransactionType.immediate):
                rows = await Paper.select(Paper.paper_id, Paper.title, Paper.abstract).run()
                await database.run_querystring(QueryString("DELETE FROM papers_fts"))
                for index, row in enumerate(rows, start=1):
                    await database.run_querystring(
                        QueryString(
                            "INSERT INTO papers_fts(title, abstract, paper_id) VALUES({}, {}, {})",
                            str(row["title"] or ""),
                            str(row.get("abstract") or ""),
                            str(row["paper_id"]),
                        )
                    )
                    if self._fail_after_inserts == index:
                        raise ValueError("injected FTS rebuild failure")
                return len(rows)

        return run_sync(rebuild_in_transaction())

    def search(self, query: str, limit: int) -> list[str]:
        if not query.strip():
            return []
        sql = """
            SELECT paper_id
            FROM papers_fts
            WHERE papers_fts MATCH {}
            ORDER BY rank
            LIMIT {}
        """
        literal_query = literal_fts_query(query)
        result = run_sync(Paper._meta.db.run_querystring(QueryString(sql, literal_query, limit)))
        rows = result if result is not None else []
        return [row["paper_id"] for row in rows]
