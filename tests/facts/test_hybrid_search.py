from __future__ import annotations

import math
import tomllib
from pathlib import Path

import pytest

from papers.app.use_cases.search import SearchPapersUseCase, compute_rrf_scores
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.stores import PiccoloPaperStore

APPROVED = Path(__file__).resolve().parents[1] / "fixtures" / "approved"
QUERY = "optimization algorithm"
ROLES = ("DATA-01a", "DATA-01b", "DATA-01c")
# FTS A,C,B and vector B,A,C → one-based RRF k=60
EXPECTED_SCORES = {
    "DATA-01a": 0.03252247,  # ranks 1, 2
    "DATA-01b": 0.03226646,  # ranks 3, 1
    "DATA-01c": 0.03200205,  # ranks 2, 3
}


def _load_fixtures() -> dict[str, dict[str, str]]:
    data = tomllib.loads((APPROVED / "manifest.toml").read_text(encoding="utf-8"))
    fixtures = data["fixture"]
    assert isinstance(fixtures, dict)
    rows: dict[str, dict[str, str]] = {}
    for role in ROLES:
        row = fixtures[role]
        assert isinstance(row, dict)
        markdown = (APPROVED / str(row["markdown_path"])).read_text(encoding="utf-8")
        rows[role] = {
            "paper_id": str(row["paper_id"]),
            "title": str(row["title"]),
            "abstract": str(row["abstract"]),
            "markdown": markdown,
        }
    return rows


class _MarkdownVectorIndex:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def query(
        self,
        embedding: list[float],
        limit: int,
        *,
        allowed_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        scored: list[tuple[str, float]] = []
        for paper_id, vector in self._vectors.items():
            if allowed_ids is not None and paper_id not in allowed_ids:
                continue
            scored.append((paper_id, _cosine(embedding, vector)))
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]


class _FixtureEmbedder:
    """Embeds fixture markdown to realize vector order B, A, C; query matches B."""

    def __init__(self, markdown_by_id: dict[str, str]) -> None:
        self._by_text = {
            markdown_by_id["paper-10"]: [1.0, 0.0, 0.0],  # B
            markdown_by_id["paper-30"]: [0.85, 0.15, 0.0],  # A
            markdown_by_id["paper-20"]: [0.20, 0.80, 0.0],  # C
            QUERY: [1.0, 0.0, 0.0],
        }

    def embed(self, text: str) -> list[float]:
        return list(self._by_text[text])


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l == 0 or norm_r == 0:
        return 0.0
    return dot / (norm_l * norm_r)


def test_hybrid_search_fused_order_and_one_based_scores(tmp_path: Path) -> None:
    fixtures = _load_fixtures()
    db = PiccoloDatabase(tmp_path / "hybrid.sqlite")
    db.initialize_schema()
    store = PiccoloPaperStore()
    markdown_by_id: dict[str, str] = {}
    for role in ROLES:
        row = fixtures[role]
        store.create_paper(
            {
                "paper_id": row["paper_id"],
                "title": row["title"],
                "abstract": row["abstract"],
            }
        )
        markdown_by_id[row["paper_id"]] = row["markdown"]

    fts = PiccoloPaperFTS()
    fts_order = fts.search(QUERY, limit=10)
    role_by_id = {fixtures[role]["paper_id"]: role for role in ROLES}
    fts_roles = [role_by_id[paper_id] for paper_id in fts_order]
    assert fts_roles == ["DATA-01a", "DATA-01c", "DATA-01b"], (
        "FTS on title+abstract must rank A, C, B; "
        f"got {fts_roles}. Do not invent abstracts to force the order."
    )

    embedder = _FixtureEmbedder(markdown_by_id)
    vectors = {paper_id: embedder.embed(markdown) for paper_id, markdown in markdown_by_id.items()}
    index = _MarkdownVectorIndex(vectors)
    vector_ids = [paper_id for paper_id, _ in index.query(embedder.embed(QUERY), limit=10)]
    vector_roles = [role_by_id[paper_id] for paper_id in vector_ids]
    assert vector_roles == ["DATA-01b", "DATA-01a", "DATA-01c"]

    use_case = SearchPapersUseCase(papers_fts=fts, vector_index=index, embedder=embedder)
    results = use_case.search(QUERY, limit=5)
    fused_ids = [row["paper_id"] for row in results]
    fused_roles = [role_by_id[paper_id] for paper_id in fused_ids]
    assert fused_roles == ["DATA-01a", "DATA-01b", "DATA-01c"]
    assert fused_ids != sorted(fused_ids)
    assert fused_ids != fts_order
    assert fused_ids != vector_ids

    scores = {row["paper_id"]: row["score"] for row in results}
    for role in ROLES:
        paper_id = fixtures[role]["paper_id"]
        assert scores[paper_id] == pytest.approx(EXPECTED_SCORES[role], abs=5e-9)

    role_lists = [
        [fixtures[role]["paper_id"] for role in ("DATA-01a", "DATA-01c", "DATA-01b")],
        [fixtures[role]["paper_id"] for role in ("DATA-01b", "DATA-01a", "DATA-01c")],
    ]
    oracle = compute_rrf_scores(role_lists, k=60)
    for role in ROLES:
        paper_id = fixtures[role]["paper_id"]
        assert oracle[paper_id] == pytest.approx(EXPECTED_SCORES[role], abs=5e-9)

    zero_based = {}
    for ranking in role_lists:
        for rank, paper_id in enumerate(ranking):
            zero_based[paper_id] = zero_based.get(paper_id, 0.0) + 1.0 / (60 + rank)
    assert scores[fixtures["DATA-01a"]["paper_id"]] != pytest.approx(
        zero_based[fixtures["DATA-01a"]["paper_id"]], abs=1e-8
    )
