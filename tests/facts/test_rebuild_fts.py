from __future__ import annotations

from pathlib import Path

import pytest

from papers.app.use_cases.admin import RebuildTitleAbstractIndexUseCase
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.search import PiccoloPaperFTS
from papers.infra.piccolo.tables import Paper


def test_rebuild_fts_indexes_papers_missing_from_title_abstract_table(tmp_path: Path) -> None:
    PiccoloDatabase(tmp_path / "app.sqlite").initialize_schema()
    Paper(
        {
            "paper_id": "paper-1",
            "title": "Gamma Fragility in Flow Driven Markets",
            "abstract": "Dealer hedging convexity and drawdown.",
            "pipeline_stage": "imported",
            "pipeline_health": "ok",
        }
    ).save().run_sync()
    fts = PiccoloPaperFTS()
    assert fts.search("Gamma Fragility", limit=10) == []

    count = RebuildTitleAbstractIndexUseCase(
        rebuild=fts.rebuild,
    )()

    assert count == 1
    assert fts.search("Gamma Fragility", limit=10) == ["paper-1"]


def test_rebuild_fts_rolls_back_when_an_insert_fails(tmp_path: Path) -> None:
    PiccoloDatabase(tmp_path / "app.sqlite").initialize_schema()
    Paper(
        {
            "paper_id": "paper-1",
            "title": "Existing Search Result",
            "abstract": "Preserve this index entry.",
            "pipeline_stage": "imported",
            "pipeline_health": "ok",
        }
    ).save().run_sync()
    fts = PiccoloPaperFTS()
    assert fts.rebuild() == 1
    assert fts.search("Existing Search Result", limit=10) == ["paper-1"]

    Paper(
        {
            "paper_id": "paper-2",
            "title": "New Uncommitted Result",
            "abstract": "This rebuild will fail.",
            "pipeline_stage": "imported",
            "pipeline_health": "ok",
        }
    ).save().run_sync()

    with pytest.raises(ValueError, match="injected FTS rebuild failure"):
        PiccoloPaperFTS(fail_after_inserts=1).rebuild()

    assert fts.search("Existing Search Result", limit=10) == ["paper-1"]
    assert fts.search("New Uncommitted Result", limit=10) == []
