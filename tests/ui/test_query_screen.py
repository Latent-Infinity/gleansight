"""Tests for the Query screen."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.screens.query import QueryScreen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PAPER = {
    "paper_id": "p1",
    "title": "Attention Is All You Need",
    "year": 2017,
    "venue": "NeurIPS",
    "authors_json": json.dumps(["Vaswani", "Shazeer", "Parmar"]),
    "abstract": "We propose a new architecture based on attention mechanisms.",
    "pipeline_stage": "analyzed",
    "pipeline_health": "ok",
}

_HIT = {"paper_id": "p1", "score": 0.95}


def _build_query_services(**overrides):
    """Build a minimal services object for QueryScreen tests."""
    svc = type("Services", (), {})()
    # search use-case mock
    search_uc = type("FakeSearch", (), {})()
    search_uc.search = lambda *, query, limit=10: [_HIT]
    filter_uc = type("FakeFilter", (), {})()
    filter_uc.filter = lambda *, field_path, prompt_version_id, constraints, latest_only=True: [
        "p1"
    ]
    aggregate_uc = type("FakeAggregate", (), {})()
    aggregate_uc.count_by_value = lambda *, field_path, prompt_version_id, latest_only=True: {
        "transformer": 1
    }
    aggregate_uc.average_numeric = (
        lambda *, field_path, prompt_version_id, group_by=None, latest_only=True: 0.95
    )
    svc.search = search_uc
    svc.filter_extractions = filter_uc
    svc.aggregate_extractions = aggregate_uc
    svc.list_paper = lambda pid: _PAPER if pid == "p1" else None
    svc.get_paper_markdown = lambda pid: "# Markdown" if pid == "p1" else None
    svc.enqueue_job = lambda t, p, r, pl: "job-id"
    svc.delete_paper = lambda pid: None
    svc.reset_pipeline_stage = lambda pid, stage: None
    svc.ui_settings = {}
    for key, val in overrides.items():
        setattr(svc, key, val)
    return svc


def _find_all(root: ft.Control, control_type: type) -> list:
    """Recursively find all controls of a given type in the tree."""
    found = []
    if isinstance(root, control_type):
        found.append(root)
    for attr in ("controls", "content", "items"):
        child = getattr(root, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for c in child:
                if isinstance(c, ft.Control):
                    found.extend(_find_all(c, control_type))
        elif isinstance(child, ft.Control):
            found.extend(_find_all(child, control_type))
    return found


def _find_text_values(root: ft.Control) -> list[str]:
    """Collect all ft.Text.value strings in the tree."""
    texts = _find_all(root, ft.Text)
    return [t.value for t in texts if t.value]


def _control_label(ctrl: ft.Control) -> str:
    """Extract display label from a control (handles both text and content)."""
    for attr in ("text", "content"):
        val = getattr(ctrl, attr, None)
        if val is None:
            continue
        if isinstance(val, str):
            return val
        if isinstance(val, ft.Text):
            return val.value or ""
    return ""


def _trigger_query(col: ft.Column, query_text: str = "attention") -> ft.ListView:
    """Enter a query and trigger the search, return the ListView."""
    listviews = _find_all(col, ft.ListView)
    assert listviews, "No ListView found in control tree"
    results_view = listviews[0]

    textfields = _find_all(col, ft.TextField)
    query_input = next((tf for tf in textfields if tf.label == "Query"), None)
    assert query_input is not None, "No Query TextField found"

    query_input.value = query_text
    with patch.object(ft.Control, "update", return_value=None):
        query_input.on_submit(MagicMock())

    return results_view


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_query_builds() -> None:
    """Screen instantiation produces a Control."""
    services = _build_query_services()
    screen = QueryScreen(services)
    control = screen.build()
    assert isinstance(control, ft.Control)


def test_query_executes_search() -> None:
    """Triggering a search populates the results view."""
    services = _build_query_services()
    screen = QueryScreen(services)
    col = screen.build()

    results_view = _trigger_query(col, "attention")

    assert len(results_view.controls) == 1, "Expected one result card"


def test_query_enriches_with_paper_data() -> None:
    """Each search hit is enriched via list_paper."""
    calls = []
    services = _build_query_services(
        list_paper=lambda pid: (calls.append(pid), _PAPER)[1],
    )
    screen = QueryScreen(services)
    col = screen.build()

    _trigger_query(col, "attention")

    assert "p1" in calls


def test_query_filters_null_papers() -> None:
    """Hits where list_paper returns None are excluded from results."""
    search_uc = type("S", (), {})()
    search_uc.search = lambda *, query, limit=10: [
        {"paper_id": "p1", "score": 0.9},
        {"paper_id": "missing", "score": 0.5},
    ]
    services = _build_query_services(
        search=search_uc,
        list_paper=lambda pid: _PAPER if pid == "p1" else None,
    )
    screen = QueryScreen(services)
    col = screen.build()

    results_view = _trigger_query(col, "test")

    assert len(results_view.controls) == 1, "Should filter out the missing paper"


def test_query_result_card_shows_metadata() -> None:
    """Result card displays title, venue, year, and score."""
    services = _build_query_services()
    screen = QueryScreen(services)
    col = screen.build()

    results_view = _trigger_query(col, "attention")
    assert results_view.controls

    card = results_view.controls[0]
    text_vals = _find_text_values(card)
    combined = " ".join(text_vals)

    assert "Attention Is All You Need" in combined
    assert "NeurIPS" in combined
    assert "2017" in combined
    assert "0.950" in combined  # score with 3 decimals


def test_query_retry_enqueues_job() -> None:
    """Retry action on a 'downloaded' paper enqueues a convert job."""
    enqueue_calls = []
    downloaded_paper = dict(_PAPER, pipeline_stage="downloaded")
    services = _build_query_services(
        list_paper=lambda pid: downloaded_paper if pid == "p1" else None,
        enqueue_job=lambda t, p, r, pl: (enqueue_calls.append((t, p)) or "job-id"),
    )
    screen = QueryScreen(services)
    col = screen.build()

    _trigger_query(col, "attention")

    with patch.object(ft.Control, "update", return_value=None):
        popup_items = _find_all(col, ft.PopupMenuItem)
        retry_item = next(
            (item for item in popup_items if "retry" in _control_label(item).lower()),
            None,
        )
        if retry_item and retry_item.on_click:
            mock_event = MagicMock()
            mock_event.page = MagicMock()
            mock_event.control.page = MagicMock()
            retry_item.on_click(mock_event)
            assert len(enqueue_calls) >= 1
            assert enqueue_calls[0][0] == "convert"


def test_query_delete_shows_confirmation() -> None:
    """Delete action shows a confirmation dialog."""
    services = _build_query_services()
    screen = QueryScreen(services)
    col = screen.build()

    _trigger_query(col, "attention")

    with patch.object(ft.Control, "update", return_value=None):
        popup_items = _find_all(col, ft.PopupMenuItem)
        delete_item = next(
            (item for item in popup_items if "delete" in _control_label(item).lower()),
            None,
        )
        if delete_item and delete_item.on_click:
            mock_event = MagicMock()
            mock_page = MagicMock()
            mock_event.page = mock_page
            mock_event.control.page = mock_page
            delete_item.on_click(mock_event)
            assert mock_page.show_dialog.called or mock_page.method_calls


def test_query_does_not_call_page_update_on_search() -> None:
    """Search should call results_view.update(), not page.update()."""
    services = _build_query_services()
    screen = QueryScreen(services)
    col = screen.build()

    textfields = _find_all(col, ft.TextField)
    query_input = next((tf for tf in textfields if tf.label == "Query"), None)
    assert query_input is not None

    query_input.value = "attention"

    mock_page = MagicMock()
    mock_event = MagicMock()
    mock_event.page = mock_page

    with patch.object(ft.Control, "update", return_value=None):
        query_input.on_submit(mock_event)

    # results_view.update() is called (patched), but page.update() must NOT be called
    mock_page.update.assert_not_called()


def test_query_applies_extraction_filter() -> None:
    captured: dict[str, object] = {}
    filter_uc = type("CapturingFilter", (), {})()
    filter_uc.filter = lambda **kwargs: (captured.update(kwargs), ["p1"])[1]
    services = _build_query_services(filter_extractions=filter_uc)
    screen = QueryScreen(services)
    col = screen.build()

    textfields = _find_all(col, ft.TextField)
    field_path = next((tf for tf in textfields if tf.label == "Filter field path"), None)
    prompt_id = next((tf for tf in textfields if tf.label == "Prompt version"), None)
    constraint_value = next((tf for tf in textfields if tf.label == "Constraint value"), None)
    assert field_path is not None
    assert prompt_id is not None
    assert constraint_value is not None
    field_path.value = "algorithm"
    prompt_id.value = "pv-1"
    constraint_value.value = "transformer"

    buttons = _find_all(col, ft.OutlinedButton)
    apply_filter = next((b for b in buttons if "apply filter" in _control_label(b).lower()), None)
    assert apply_filter is not None
    with patch.object(ft.Control, "update", return_value=None):
        apply_filter.on_click(MagicMock())

    assert captured["field_path"] == "algorithm"
    assert captured["prompt_version_id"] == "pv-1"
    assert captured["constraints"] == {"value_text": "transformer"}


def test_query_runs_aggregation_and_shows_output() -> None:
    services = _build_query_services()
    screen = QueryScreen(services)
    col = screen.build()

    textfields = _find_all(col, ft.TextField)
    agg_field = next((tf for tf in textfields if tf.label == "Aggregate field path"), None)
    agg_prompt = [tf for tf in textfields if tf.label == "Prompt version"][1]
    assert agg_field is not None
    assert agg_prompt is not None
    agg_field.value = "algorithm"
    agg_prompt.value = "pv-1"

    buttons = _find_all(col, ft.OutlinedButton)
    aggregate_button = next(
        (b for b in buttons if "run aggregation" in _control_label(b).lower()),
        None,
    )
    assert aggregate_button is not None

    with patch.object(ft.Control, "update", return_value=None):
        aggregate_button.on_click(MagicMock())

    text_vals = _find_text_values(col)
    assert "transformer" in " ".join(text_vals)


def test_query_exports_current_results_csv(tmp_path) -> None:
    services = _build_query_services()
    screen = QueryScreen(services)
    col = screen.build()

    _trigger_query(col, "attention")
    export_target = tmp_path / "query-results.csv"
    textfields = _find_all(col, ft.TextField)
    export_path = next((tf for tf in textfields if tf.label == "Export path"), None)
    assert export_path is not None
    export_path.value = str(export_target)

    buttons = _find_all(col, ft.Button)
    export_button = next((b for b in buttons if "export csv" in _control_label(b).lower()), None)
    assert export_button is not None

    with patch.object(ft.Control, "update", return_value=None):
        export_button.on_click(MagicMock())

    content = export_target.read_text(encoding="utf-8")
    assert "paper_id,score,title,year,venue,pipeline_stage,pipeline_health" in content
    assert "p1" in content
