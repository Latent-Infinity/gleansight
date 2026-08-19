from __future__ import annotations

from piccolo.querystring import QueryString
from piccolo.utils.sync import run_sync

from papers.infra.piccolo.fts import literal_fts_query
from papers.infra.piccolo.tables import Paper


class PiccoloPaperFTS:
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
        rows = run_sync(Paper._meta.db.run_querystring(QueryString(sql, literal_query, limit)))
        return [row["paper_id"] for row in rows]
