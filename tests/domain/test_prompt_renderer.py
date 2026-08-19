from __future__ import annotations

import pytest

from papers.domain.errors import NotReadyError
from papers.domain.policies import RenderedPrompt, render_prompt_template


def test_render_simple_placeholders() -> None:
    result = render_prompt_template(
        template="Analyze paper {paper_id}: {title}",
        paper_id="p1",
        title="My Paper",
        abstract="Some abstract",
        authors=["Alice", "Bob"],
        year=2024,
        venue="NeurIPS",
        markdown=None,
    )
    assert isinstance(result, RenderedPrompt)
    assert result.text == "Analyze paper p1: My Paper"


def test_render_all_simple_placeholders() -> None:
    result = render_prompt_template(
        template="{paper_id} | {title} | {abstract} | {authors} | {year} | {venue}",
        paper_id="p1",
        title="T",
        abstract="A",
        authors=["X", "Y"],
        year=2023,
        venue="V",
        markdown=None,
    )
    assert result.text == "p1 | T | A | X, Y | 2023 | V"


def test_render_null_values_become_empty_string() -> None:
    result = render_prompt_template(
        template="{title} | {abstract} | {year} | {venue}",
        paper_id="p1",
        title=None,
        abstract=None,
        authors=[],
        year=None,
        venue=None,
        markdown=None,
    )
    assert result.text == " |  |  | "


def test_render_authors_comma_separated() -> None:
    result = render_prompt_template(
        template="Authors: {authors}",
        paper_id="p1",
        title=None,
        abstract=None,
        authors=["Alice", "Bob", "Charlie"],
        year=None,
        venue=None,
        markdown=None,
    )
    assert result.text == "Authors: Alice, Bob, Charlie"


def test_render_authors_empty_list() -> None:
    result = render_prompt_template(
        template="Authors: {authors}",
        paper_id="p1",
        title=None,
        abstract=None,
        authors=[],
        year=None,
        venue=None,
        markdown=None,
    )
    assert result.text == "Authors: "


def test_render_markdown_placeholder() -> None:
    result = render_prompt_template(
        template="Paper content:\n{markdown}",
        paper_id="p1",
        title=None,
        abstract=None,
        authors=[],
        year=None,
        venue=None,
        markdown="# Introduction\nSome text here.",
    )
    assert result.text == "Paper content:\n# Introduction\nSome text here."


def test_render_markdown_required_but_missing_raises_not_ready() -> None:
    with pytest.raises(NotReadyError, match="markdown"):
        render_prompt_template(
            template="Content: {markdown}",
            paper_id="p1",
            title=None,
            abstract=None,
            authors=[],
            year=None,
            venue=None,
            markdown=None,
        )


def test_render_markdown_truncated() -> None:
    result = render_prompt_template(
        template="Content: {markdown_truncated:10}",
        paper_id="p1",
        title=None,
        abstract=None,
        authors=[],
        year=None,
        venue=None,
        markdown="A" * 20,
    )
    assert result.text == "Content: " + "A" * 10


def test_render_markdown_truncated_shorter_than_n() -> None:
    result = render_prompt_template(
        template="Content: {markdown_truncated:100}",
        paper_id="p1",
        title=None,
        abstract=None,
        authors=[],
        year=None,
        venue=None,
        markdown="Short text",
    )
    assert result.text == "Content: Short text"


def test_render_markdown_truncated_missing_raises_not_ready() -> None:
    with pytest.raises(NotReadyError, match="markdown"):
        render_prompt_template(
            template="Content: {markdown_truncated:5000}",
            paper_id="p1",
            title=None,
            abstract=None,
            authors=[],
            year=None,
            venue=None,
            markdown=None,
        )


def test_render_no_placeholders_returns_unchanged() -> None:
    result = render_prompt_template(
        template="Just a plain prompt with no placeholders.",
        paper_id="p1",
        title="T",
        abstract="A",
        authors=["X"],
        year=2024,
        venue="V",
        markdown="M",
    )
    assert result.text == "Just a plain prompt with no placeholders."


def test_render_multiple_truncated_placeholders() -> None:
    result = render_prompt_template(
        template="Short: {markdown_truncated:5}\nLong: {markdown_truncated:15}",
        paper_id="p1",
        title=None,
        abstract=None,
        authors=[],
        year=None,
        venue=None,
        markdown="ABCDEFGHIJKLMNOPQRST",
    )
    assert result.text == "Short: ABCDE\nLong: ABCDEFGHIJKLMNO"


def test_render_markdown_not_needed_when_no_placeholder() -> None:
    """markdown=None should NOT raise if {markdown} is not in the template."""
    result = render_prompt_template(
        template="Just {title}",
        paper_id="p1",
        title="T",
        abstract=None,
        authors=[],
        year=None,
        venue=None,
        markdown=None,
    )
    assert result.text == "Just T"
