from __future__ import annotations

from pathlib import Path

import pytest

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloExtractionStore


class _Extraction:
    def __init__(self, field_path: str, value_text: str) -> None:
        self.entity_type = "paper"
        self.entity_ref = None
        self.field_path = field_path
        self.value_text = value_text
        self.value_numeric = None
        self.value_boolean = None


def test_query_by_field(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "extract.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    store.upsert_extractions(
        run_id="run",
        paper_id="paper",
        prompt_version_id="prompt",
        extractions=[_Extraction("field", "value")],
    )
    paper_ids = store.query(
        "field",
        prompt_version_id="prompt",
        constraints={"value_text": "value"},
        latest_only=False,
    )
    assert paper_ids == ["paper"]


def test_query_rejects_unsupported_constraint_field(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "extract-invalid.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()

    with pytest.raises(ValueError, match="unsupported extraction constraint field"):
        store.query(
            "field",
            prompt_version_id="prompt",
            constraints={"value_text; DROP TABLE analysis_extractions; --": "value"},
            latest_only=True,
        )


def test_search_text_uses_extractions_fts(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "extract-text.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    store.upsert_extractions(
        run_id="run",
        paper_id="paper",
        prompt_version_id="prompt",
        extractions=[_Extraction("summary", "hybrid retrieval and ranking")],
    )

    paper_ids = store.search_text("retrieval", prompt_version_id="prompt")
    assert paper_ids == ["paper"]


def test_search_text_matches_nonadjacent_literal_terms(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "extract-text-terms.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    store.upsert_extractions(
        run_id="run",
        paper_id="paper",
        prompt_version_id="prompt",
        extractions=[_Extraction("summary", "hybrid methods for retrieval")],
    )

    assert store.search_text("hybrid retrieval", prompt_version_id="prompt") == ["paper"]


def test_search_text_treats_fts_syntax_as_literal_text(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "extract-text-literal.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()

    assert store.search_text('unmatched"', prompt_version_id="prompt") == []
