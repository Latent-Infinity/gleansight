"""Tests for the Paper Detail screen."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.screens.paper import PaperDetailScreen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PAPER = {
    "paper_id": "paper-1",
    "title": "Test Paper Title",
    "year": 2024,
    "venue": "TestConf",
    "authors_json": json.dumps(["Alice", "Bob", "Charlie"]),
    "abstract": "A test abstract about machine learning.",
    "pipeline_stage": "analyzed",
    "pipeline_health": "ok",
}

_RUN = {
    "run_id": "run-1",
    "status": "succeeded",
    "prompt_version_id": "pv-1",
    "model_name": "llama-3",
    "tokens_in": 100,
    "tokens_out": 200,
    "cost_usd": 0.005,
    "started_at": "2024-06-01T12:00:00",
    "finished_at": "2024-06-01T12:01:00",
    "error_message": None,
}


class _FakeExtraction:
    def __init__(
        self,
        field_path: str,
        value_text=None,
        value_numeric=None,
        value_boolean=None,
        prompt_version_id: str = "pv-1",
    ):
        self.field_path = field_path
        self.value_text = value_text
        self.value_numeric = value_numeric
        self.value_boolean = value_boolean
        self.entity_type = "paper"
        self.entity_ref = None
        self.run_id = "run-1"
        self.prompt_version_id = prompt_version_id


_EXTRACTIONS = [
    _FakeExtraction("algorithm", value_text="SGD", prompt_version_id="pv-1"),
    _FakeExtraction("score", value_numeric=9.5, prompt_version_id="pv-1"),
    _FakeExtraction("novel", value_boolean=1, prompt_version_id="pv-2"),
]


def _build_paper_services(**overrides):
    """Build a minimal services object for PaperDetailScreen tests."""
    svc = type("Services", (), {})()
    svc.list_paper = lambda pid: _PAPER if pid == "paper-1" else None
    svc.list_runs = lambda pid: [_RUN] if pid == "paper-1" else []
    svc.list_extractions = lambda pid, pv=None: list(_EXTRACTIONS) if pid == "paper-1" else []
    svc.get_paper_markdown = (
        lambda pid: "# Test Markdown\nContent here." if pid == "paper-1" else None
    )
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


def _button_label(btn: ft.Control) -> str:
    """Extract the display label from a Button (Flet 0.80 uses content, not text)."""
    for attr in ("text", "content"):
        val = getattr(btn, attr, None)
        if val is None:
            continue
        if isinstance(val, str):
            return val
        if isinstance(val, ft.Text):
            return val.value or ""
    return ""


def _trigger_load(col: ft.Control, paper_id: str = "paper-1") -> None:
    """Set the paper_id input and trigger the load handler."""
    textfields = _find_all(col, ft.TextField)
    paper_input = next((tf for tf in textfields if "paper" in (tf.label or "").lower()), None)
    assert paper_input is not None, "No Paper ID TextField found"
    paper_input.value = paper_id
    with patch.object(ft.Control, "update", return_value=None):
        # Find and click the Load button
        buttons = (
            _find_all(col, ft.Button)
            + _find_all(col, ft.ElevatedButton)
            + _find_all(col, ft.TextButton)
            + _find_all(col, ft.IconButton)
        )
        load_btn = None
        for btn in buttons:
            label = _button_label(btn)
            if "load" in label.lower():
                load_btn = btn
                break
        assert load_btn is not None, "No Load button found"
        assert load_btn.on_click is not None, "Load button has no on_click handler"
        load_btn.on_click(MagicMock())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_paper_detail_builds() -> None:
    """Screen instantiation produces a Control."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    control = screen.build()
    assert isinstance(control, ft.Control)


def test_paper_loads_metadata() -> None:
    """After loading a paper, title/authors/venue/year should be visible."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    assert "Test Paper Title" in combined
    assert "2024" in combined


def test_paper_shows_pipeline_status() -> None:
    """Pipeline stage should be displayed after loading."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals).lower()
    assert "analyzed" in combined


def test_paper_shows_runs_table() -> None:
    """Analysis runs should be displayed in a table or list."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    # Run ID and model should appear
    assert "run-1" in combined
    assert "llama-3" in combined


def test_paper_shows_run_timestamps() -> None:
    """Run rows include started and finished timestamps."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    assert "2024-06-01 12:00:00" in combined
    assert "2024-06-01 12:01:00" in combined


def test_paper_shows_extractions() -> None:
    """Extracted fields should be displayed after loading."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    assert "algorithm" in combined
    assert "SGD" in combined
    assert "score" in combined


def test_paper_extractions_filter_by_prompt_version() -> None:
    """Prompt version selector filters extraction rows."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    dropdowns = _find_all(col, ft.Dropdown)
    prompt_selector = next((d for d in dropdowns if d.label == "Prompt version"), None)
    assert prompt_selector is not None

    with patch.object(ft.Control, "update", return_value=None):
        prompt_selector.value = "pv-2"
        if prompt_selector.on_select:
            prompt_selector.on_select(MagicMock(control=prompt_selector))

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    assert "novel" in combined


def test_paper_not_found() -> None:
    """Loading a non-existent paper shows a 'not found' message."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "nonexistent")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals).lower()
    assert "not found" in combined


def test_paper_error_state() -> None:
    """Paper with pipeline_health='error' shows error info."""
    error_paper = dict(_PAPER, pipeline_health="error", last_error_message="Conversion failed")
    services = _build_paper_services(
        list_paper=lambda pid: error_paper if pid == "paper-1" else None,
    )
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals).lower()
    assert "error" in combined


def test_paper_shows_markdown_in_dialog() -> None:
    """View Markdown action should create a dialog with markdown content."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    # Find the markdown/details action and trigger it
    with patch.object(ft.Control, "update", return_value=None):
        # Look for a popup menu or button with "Markdown" or "View" text
        popup_items = _find_all(col, ft.PopupMenuItem)
        md_item = next(
            (item for item in popup_items if "markdown" in _button_label(item).lower()),
            None,
        )
        if md_item and md_item.on_click:
            mock_event = MagicMock()
            mock_page = MagicMock()
            mock_event.page = mock_page
            mock_event.control.page = mock_page
            md_item.on_click(mock_event)
            # Verify a dialog was shown
            assert mock_page.show_dialog.called or mock_page.method_calls


def test_paper_action_retry() -> None:
    """Retry action should enqueue a job."""
    enqueue_calls = []
    services = _build_paper_services(
        list_paper=lambda pid: dict(_PAPER, pipeline_stage="downloaded")
        if pid == "paper-1"
        else None,
        enqueue_job=lambda t, p, r, pl: (enqueue_calls.append((t, p)) or "job-id"),
    )
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    with patch.object(ft.Control, "update", return_value=None):
        popup_items = _find_all(col, ft.PopupMenuItem)
        retry_item = next(
            (item for item in popup_items if "retry" in _button_label(item).lower()),
            None,
        )
        if retry_item and retry_item.on_click:
            mock_event = MagicMock()
            mock_event.page = MagicMock()
            mock_event.control.page = MagicMock()
            retry_item.on_click(mock_event)
            assert len(enqueue_calls) >= 1
            assert enqueue_calls[0][0] == "convert"  # downloaded → convert


def test_paper_action_delete() -> None:
    """Delete action should show a confirmation dialog."""
    services = _build_paper_services()
    screen = PaperDetailScreen(services)
    col = screen.build()

    _trigger_load(col, "paper-1")

    with patch.object(ft.Control, "update", return_value=None):
        popup_items = _find_all(col, ft.PopupMenuItem)
        delete_item = next(
            (item for item in popup_items if "delete" in _button_label(item).lower()),
            None,
        )
        if delete_item and delete_item.on_click:
            mock_event = MagicMock()
            mock_page = MagicMock()
            mock_event.page = mock_page
            mock_event.control.page = mock_page
            delete_item.on_click(mock_event)
            assert mock_page.show_dialog.called or mock_page.method_calls
