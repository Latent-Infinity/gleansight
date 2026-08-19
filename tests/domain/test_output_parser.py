from __future__ import annotations

import pytest

from papers.domain.errors import OutputParseFailed
from papers.domain.models import OutputFormat
from papers.domain.policies import ParsedOutput, parse_llm_output


def test_parse_yaml_block_success() -> None:
    raw = "Some text\n```yaml\nname: Foo\nscore: 4\n```\nMore text"
    result = parse_llm_output(raw_text=raw, output_format=OutputFormat.yaml_block)
    assert isinstance(result, ParsedOutput)
    assert result.data == {"name": "Foo", "score": 4}
    assert result.raw_text == raw


def test_parse_yaml_block_no_fence() -> None:
    with pytest.raises(OutputParseFailed, match="yaml"):
        parse_llm_output(raw_text="No fenced block here", output_format=OutputFormat.yaml_block)


def test_parse_yaml_block_invalid_yaml() -> None:
    raw = "```yaml\n: invalid: {{{\n```"
    with pytest.raises(OutputParseFailed):
        parse_llm_output(raw_text=raw, output_format=OutputFormat.yaml_block)


def test_parse_yaml_block_non_dict() -> None:
    raw = "```yaml\n- item1\n- item2\n```"
    with pytest.raises(OutputParseFailed, match="object"):
        parse_llm_output(raw_text=raw, output_format=OutputFormat.yaml_block)


def test_parse_json_block_success() -> None:
    raw = 'Narrative\n```json\n{"key": "value", "num": 42}\n```\nEnd'
    result = parse_llm_output(raw_text=raw, output_format=OutputFormat.json_block)
    assert result.data == {"key": "value", "num": 42}
    assert result.raw_text == raw


def test_parse_json_block_no_fence() -> None:
    with pytest.raises(OutputParseFailed, match="json"):
        parse_llm_output(raw_text="No json block", output_format=OutputFormat.json_block)


def test_parse_json_only_success() -> None:
    raw = '{"algorithm": "SGD", "score": 9.5}'
    result = parse_llm_output(raw_text=raw, output_format=OutputFormat.json_only)
    assert result.data == {"algorithm": "SGD", "score": 9.5}


def test_parse_json_only_invalid() -> None:
    with pytest.raises(OutputParseFailed, match="JSON"):
        parse_llm_output(raw_text="not json at all", output_format=OutputFormat.json_only)


def test_parse_markdown_only() -> None:
    raw = "# Analysis\nThis paper is great."
    result = parse_llm_output(raw_text=raw, output_format=OutputFormat.markdown_only)
    assert result.data is None
    assert result.raw_text == raw


def test_parse_empty_response_raises() -> None:
    with pytest.raises(OutputParseFailed, match="empty"):
        parse_llm_output(raw_text="", output_format=OutputFormat.yaml_block)


def test_parse_whitespace_only_raises() -> None:
    with pytest.raises(OutputParseFailed, match="empty"):
        parse_llm_output(raw_text="   \n\t\n  ", output_format=OutputFormat.json_only)


def test_parse_yaml_block_picks_first_fence() -> None:
    raw = "```yaml\nfirst: 1\n```\nText\n```yaml\nsecond: 2\n```"
    result = parse_llm_output(raw_text=raw, output_format=OutputFormat.yaml_block)
    assert result.data == {"first": 1}


def test_parse_json_block_with_surrounding_text() -> None:
    raw = (
        "Here is my analysis:\n\n"
        '```json\n{"evaluation": {"rigor": 4}}\n```\n\n'
        "In conclusion, this is good."
    )
    result = parse_llm_output(raw_text=raw, output_format=OutputFormat.json_block)
    assert result.data == {"evaluation": {"rigor": 4}}
