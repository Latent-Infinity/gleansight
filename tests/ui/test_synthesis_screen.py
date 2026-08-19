"""Tests for the Synthesis screen."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import flet as ft

from papers.ui.screens.synthesis import SynthesisScreen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """Extract the display label from a Button."""
    for attr in ("text", "content"):
        val = getattr(btn, attr, None)
        if val is None:
            continue
        if isinstance(val, str):
            return val
        if isinstance(val, ft.Text):
            return val.value or ""
    return ""


@dataclass
class FakeSynthesizeFromCorpusUseCase:
    answer: str = "Mocked Synthesis Answer"
    sources: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"paper_id": "paper-1", "title": "Mock Paper 1"},
            {"paper_id": "paper-2", "title": "Mock Paper 2"},
        ]
    )
    mock_exception: type[Exception] | None = None
    call_args: list[dict[str, Any]] = field(default_factory=list)

    def synthesize(
        self,
        question: str,
        project_id: str | None = None,
        tags: list[str] | None = None,
        num_retrieved_docs: int = 5,
        llm_profile: dict[str, Any] | None = None,
        llm_model: str = "gpt-4o-mini",
    ) -> tuple[str, list[dict[str, Any]]]:
        self.call_args.append(
            {
                "question": question,
                "project_id": project_id,
                "tags": tags,
                "num_retrieved_docs": num_retrieved_docs,
                "llm_profile": llm_profile,
                "llm_model": llm_model,
            }
        )
        if self.mock_exception:
            raise self.mock_exception("Mock Synthesis Error")
        return self.answer, self.sources


def _build_synthesis_services(**overrides):
    """Build a minimal services object for SynthesisScreen tests."""
    services = type("Services", (), {})()
    services.synthesize_from_corpus = FakeSynthesizeFromCorpusUseCase()
    services.ui_settings = {}
    for key, val in overrides.items():
        setattr(services, key, val)
    return services


def _trigger_ask(col: ft.Column, question_text: str) -> None:
    """Enter a question and trigger the ask action."""
    textfields = _find_all(col, ft.TextField)
    question_input = next((tf for tf in textfields if tf.label == "Your Question"), None)
    assert question_input is not None, "No question TextField found"
    question_input.value = question_text

    with patch.object(ft.Control, "update", return_value=None):
        question_input.on_submit(MagicMock())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_synthesis_screen_builds() -> None:
    """Screen instantiation produces a Control."""
    services = _build_synthesis_services()
    screen = SynthesisScreen(services)
    control = screen.build()
    assert isinstance(control, ft.Control)


def test_synthesis_screen_has_question_input_and_ask_button() -> None:
    """Screen has a question TextField and an Ask button."""
    services = _build_synthesis_services()
    screen = SynthesisScreen(services)
    col = screen.build()

    textfields = _find_all(col, ft.TextField)
    question_input = next((tf for tf in textfields if tf.label == "Your Question"), None)
    assert question_input is not None

    buttons = _find_all(col, ft.Button)
    ask_button = next((b for b in buttons if "ask" in _button_label(b).lower()), None)
    assert ask_button is not None


def test_synthesis_screen_submits_question_and_displays_answer() -> None:
    """Submitting a question calls the use case and displays the answer."""
    mock_uc = FakeSynthesizeFromCorpusUseCase()
    services = _build_synthesis_services(synthesize_from_corpus=mock_uc)
    screen = SynthesisScreen(services)
    col = screen.build()

    _trigger_ask(col, "How does RAG work?")

    # Verify use case was called
    assert len(mock_uc.call_args) == 1
    assert mock_uc.call_args[0]["question"] == "How does RAG work?"

    # Verify answer is displayed in a Markdown control
    markdowns = _find_all(col, ft.Markdown)
    assert any(md.value == mock_uc.answer for md in markdowns)


def test_synthesis_screen_displays_sources() -> None:
    """Source papers are listed after synthesis."""
    mock_uc = FakeSynthesizeFromCorpusUseCase()
    services = _build_synthesis_services(synthesize_from_corpus=mock_uc)
    screen = SynthesisScreen(services)
    col = screen.build()

    _trigger_ask(col, "Sources please")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    for source in mock_uc.sources:
        assert source["title"] in combined


def test_synthesis_screen_shows_loading_indicator() -> None:
    """A progress bar exists and is initially hidden."""
    services = _build_synthesis_services()
    screen = SynthesisScreen(services)
    col = screen.build()

    progress_bars = _find_all(col, ft.ProgressBar)
    assert len(progress_bars) >= 1
    assert progress_bars[0].visible is False


def test_synthesis_screen_displays_error_message() -> None:
    """An error from the use case is displayed."""
    mock_uc = FakeSynthesizeFromCorpusUseCase(mock_exception=ValueError)
    services = _build_synthesis_services(synthesize_from_corpus=mock_uc)
    screen = SynthesisScreen(services)
    col = screen.build()

    _trigger_ask(col, "Cause an error")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    assert "Error: Mock Synthesis Error" in combined


def test_synthesis_screen_empty_question_shows_validation() -> None:
    """Submitting an empty question shows a validation message."""
    services = _build_synthesis_services()
    screen = SynthesisScreen(services)
    col = screen.build()

    _trigger_ask(col, "")

    text_vals = _find_text_values(col)
    combined = " ".join(text_vals)
    assert "Please enter a question" in combined


def test_synthesis_screen_ask_button_triggers_synthesis() -> None:
    """Clicking the Ask button triggers synthesis."""
    mock_uc = FakeSynthesizeFromCorpusUseCase()
    services = _build_synthesis_services(synthesize_from_corpus=mock_uc)
    screen = SynthesisScreen(services)
    col = screen.build()

    # Set question text
    textfields = _find_all(col, ft.TextField)
    question_input = next((tf for tf in textfields if tf.label == "Your Question"), None)
    assert question_input is not None
    question_input.value = "Test via button click"

    # Find and click the Ask button
    buttons = _find_all(col, ft.Button)
    ask_button = next((b for b in buttons if "ask" in _button_label(b).lower()), None)
    assert ask_button is not None

    with patch.object(ft.Control, "update", return_value=None):
        ask_button.on_click(MagicMock())

    assert len(mock_uc.call_args) == 1
    assert mock_uc.call_args[0]["question"] == "Test via button click"
