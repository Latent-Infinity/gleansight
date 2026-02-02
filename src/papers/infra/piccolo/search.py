from __future__ import annotations

from papers.infra.piccolo.tables import Paper


class PiccoloPaperFTS:
    def search(self, query: str, limit: int) -> list[str]:
        if not query.strip():
            return []
        like_pattern = f"%{query}%"
        rows = (
            Paper.select(Paper.paper_id)
            .where((Paper.title.ilike(like_pattern)) | (Paper.abstract.ilike(like_pattern)))
            .limit(limit)
            .run_sync()
        )
        return [row["paper_id"] for row in rows]
