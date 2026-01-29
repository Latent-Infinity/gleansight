from __future__ import annotations

from pathlib import Path

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


def test_upsert_and_list(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "extract.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    store.upsert_extractions(
        run_id="run",
        paper_id="paper",
        prompt_version_id="prompt",
        extractions=[_Extraction("field", "value")],
    )
    results = store.list_by_paper("paper")
    assert len(results) == 1
    assert results[0].field_path == "field"
