from __future__ import annotations

from pathlib import Path

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloExtractionStore


class _Extraction:
    def __init__(
        self,
        field_path: str,
        value_text: str | None = None,
        value_numeric: float | None = None,
    ) -> None:
        self.entity_type: str = "paper"
        self.entity_ref: str | None = None
        self.field_path: str = field_path
        self.value_text: str | None = value_text
        self.value_numeric: float | None = value_numeric
        self.value_boolean: int | None = None


def test_upsert_and_list(tmp_path: Path) -> None:
    db = PiccoloDatabase(tmp_path / "extract.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    store.upsert_extractions(
        run_id="run",
        paper_id="paper",
        prompt_version_id="prompt",
        extractions=[_Extraction("field", value_text="value")],
    )
    results = store.list_by_paper("paper")
    assert len(results) == 1
    assert results[0].field_path == "field"


def test_count_by_value(tmp_path: Path) -> None:
    """Test count_by_value aggregation."""
    db = PiccoloDatabase(tmp_path / "count.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()

    # Insert extractions for 3 papers with different algorithm families
    store.upsert_extractions(
        run_id="run1",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("algorithm_family", value_text="transformer")],
    )
    store.upsert_extractions(
        run_id="run2",
        paper_id="p2",
        prompt_version_id="pv1",
        extractions=[_Extraction("algorithm_family", value_text="transformer")],
    )
    store.upsert_extractions(
        run_id="run3",
        paper_id="p3",
        prompt_version_id="pv1",
        extractions=[_Extraction("algorithm_family", value_text="cnn")],
    )

    # Count by value
    counts = store.count_by_value("algorithm_family", "pv1", latest_only=False)

    assert counts == {"transformer": 2, "cnn": 1}


def test_count_by_value_empty(tmp_path: Path) -> None:
    """Test count_by_value with no data."""
    db = PiccoloDatabase(tmp_path / "count_empty.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()

    counts = store.count_by_value("nonexistent_field", "pv1", latest_only=False)

    assert counts == {}


def test_average_numeric(tmp_path: Path) -> None:
    """Test average_numeric aggregation."""
    db = PiccoloDatabase(tmp_path / "avg.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()

    # Insert numeric extractions
    store.upsert_extractions(
        run_id="run1",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("rigor_rating", value_numeric=4.0)],
    )
    store.upsert_extractions(
        run_id="run2",
        paper_id="p2",
        prompt_version_id="pv1",
        extractions=[_Extraction("rigor_rating", value_numeric=5.0)],
    )
    store.upsert_extractions(
        run_id="run3",
        paper_id="p3",
        prompt_version_id="pv1",
        extractions=[_Extraction("rigor_rating", value_numeric=3.0)],
    )

    # Average numeric
    avg = store.average_numeric("rigor_rating", "pv1", latest_only=False)

    assert avg == 4.0


def test_average_numeric_empty(tmp_path: Path) -> None:
    """Test average_numeric with no data."""
    db = PiccoloDatabase(tmp_path / "avg_empty.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()

    avg = store.average_numeric("nonexistent_field", "pv1", latest_only=False)

    assert avg is None


def test_average_numeric_grouped(tmp_path: Path) -> None:
    """Test average_numeric with grouping."""
    db = PiccoloDatabase(tmp_path / "avg_grouped.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()

    # Insert numeric extractions with different text values for grouping
    store.upsert_extractions(
        run_id="run1",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[
            _Extraction("algorithm_family", value_text="transformer"),
            _Extraction("rigor_rating", value_text="transformer", value_numeric=4.0),
        ],
    )
    store.upsert_extractions(
        run_id="run2",
        paper_id="p2",
        prompt_version_id="pv1",
        extractions=[
            _Extraction("algorithm_family", value_text="transformer"),
            _Extraction("rigor_rating", value_text="transformer", value_numeric=5.0),
        ],
    )
    store.upsert_extractions(
        run_id="run3",
        paper_id="p3",
        prompt_version_id="pv1",
        extractions=[
            _Extraction("algorithm_family", value_text="cnn"),
            _Extraction("rigor_rating", value_text="cnn", value_numeric=3.0),
        ],
    )

    # Average numeric grouped by value_text
    avg_grouped = store.average_numeric(
        "rigor_rating",
        "pv1",
        group_by="value_text",
        latest_only=False,
    )

    assert avg_grouped == {"transformer": 4.5, "cnn": 3.0}


def test_average_numeric_grouped_with_latest_only(tmp_path: Path) -> None:
    """Test average_numeric with grouping and latest_only."""
    from papers.infra.piccolo.database import PiccoloDatabase
    from papers.infra.piccolo.stores import PiccoloAnalysisRunStore, PiccoloJobQueue

    db = PiccoloDatabase(tmp_path / "avg_grouped_latest.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    run_store = PiccoloAnalysisRunStore()
    queue = PiccoloJobQueue()

    # Paper 1: older run with rigor_rating=4.0, algorithm=transformer
    run_store.create_run("run1", "p1", "pv1", "prof1", "model1")
    run_store.mark_started("run1")
    store.upsert_extractions(
        run_id="run1",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("rigor_rating", value_text="transformer", value_numeric=4.0)],
    )
    job_id1 = queue.enqueue("analyze", None, "run1", {})
    queue.mark_succeeded(job_id1)

    # Paper 1: newer run with rigor_rating=5.0, algorithm=transformer (should override)
    run_store.create_run("run2", "p1", "pv1", "prof1", "model1")
    run_store.mark_started("run2")
    store.upsert_extractions(
        run_id="run2",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("rigor_rating", value_text="transformer", value_numeric=5.0)],
    )
    job_id2 = queue.enqueue("analyze", None, "run2", {})
    queue.mark_succeeded(job_id2)

    # Paper 2: single run with rigor_rating=3.0, algorithm=cnn
    run_store.create_run("run3", "p2", "pv1", "prof1", "model1")
    run_store.mark_started("run3")
    store.upsert_extractions(
        run_id="run3",
        paper_id="p2",
        prompt_version_id="pv1",
        extractions=[_Extraction("rigor_rating", value_text="cnn", value_numeric=3.0)],
    )
    job_id3 = queue.enqueue("analyze", None, "run3", {})
    queue.mark_succeeded(job_id3)

    # Average grouped by value_text with latest_only=True
    # Should use run2 (5.0) for p1/transformer, run3 (3.0) for p2/cnn
    avg_grouped = store.average_numeric(
        "rigor_rating",
        "pv1",
        group_by="value_text",
        latest_only=True,
    )

    assert avg_grouped == {"transformer": 5.0, "cnn": 3.0}


def test_query_with_latest_only(tmp_path: Path) -> None:
    """Test query with latest_only filters to latest successful runs."""
    from papers.infra.piccolo.database import PiccoloDatabase
    from papers.infra.piccolo.stores import PiccoloAnalysisRunStore, PiccoloJobQueue

    db = PiccoloDatabase(tmp_path / "latest.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    run_store = PiccoloAnalysisRunStore()
    queue = PiccoloJobQueue()

    # Create first run (older, successful)
    run_store.create_run("run1", "p1", "pv1", "prof1", "model1")
    run_store.mark_started("run1")
    store.upsert_extractions(
        run_id="run1",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("algorithm_family", value_text="old_value")],
    )
    # Mark job as succeeded
    job_id = queue.enqueue("analyze", None, "run1", {})
    queue.mark_succeeded(job_id)

    # Create second run (newer, successful) - this should be the latest
    run_store.create_run("run2", "p1", "pv1", "prof1", "model1")
    run_store.mark_started("run2")
    store.upsert_extractions(
        run_id="run2",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("algorithm_family", value_text="new_value")],
    )
    # Mark job as succeeded
    job_id2 = queue.enqueue("analyze", None, "run2", {})
    queue.mark_succeeded(job_id2)

    # Query with latest_only=True should only return papers with new_value
    papers = store.query(
        "algorithm_family",
        prompt_version_id="pv1",
        constraints={"value_text": "new_value"},
        latest_only=True,
    )
    assert papers == ["p1"]

    # Query for old value with latest_only=True should return nothing
    papers_old = store.query(
        "algorithm_family",
        prompt_version_id="pv1",
        constraints={"value_text": "old_value"},
        latest_only=True,
    )
    assert papers_old == []

    # Query with latest_only=False should return papers with old_value
    papers_all = store.query(
        "algorithm_family",
        prompt_version_id="pv1",
        constraints={"value_text": "old_value"},
        latest_only=False,
    )
    assert papers_all == ["p1"]


def test_count_by_value_with_latest_only(tmp_path: Path) -> None:
    """Test count_by_value with latest_only filters to latest successful runs."""
    from papers.infra.piccolo.database import PiccoloDatabase
    from papers.infra.piccolo.stores import PiccoloAnalysisRunStore, PiccoloJobQueue

    db = PiccoloDatabase(tmp_path / "count_latest.sqlite")
    db.initialize_schema()
    store = PiccoloExtractionStore()
    run_store = PiccoloAnalysisRunStore()
    queue = PiccoloJobQueue()

    # Create first run (older)
    run_store.create_run("run1", "p1", "pv1", "prof1", "model1")
    store.upsert_extractions(
        run_id="run1",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("algorithm_family", value_text="transformer")],
    )
    job_id = queue.enqueue("analyze", None, "run1", {})
    queue.mark_succeeded(job_id)

    # Create second run (newer) - paper changes value
    run_store.create_run("run2", "p1", "pv1", "prof1", "model1")
    store.upsert_extractions(
        run_id="run2",
        paper_id="p1",
        prompt_version_id="pv1",
        extractions=[_Extraction("algorithm_family", value_text="cnn")],
    )
    job_id2 = queue.enqueue("analyze", None, "run2", {})
    queue.mark_succeeded(job_id2)

    # Count with latest_only=True should show cnn=1, not transformer
    counts = store.count_by_value("algorithm_family", "pv1", latest_only=True)
    assert counts == {"cnn": 1}

    # Count with latest_only=False should show both
    counts_all = store.count_by_value("algorithm_family", "pv1", latest_only=False)
    assert counts_all == {"transformer": 1, "cnn": 1}
