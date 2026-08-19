from __future__ import annotations

from papers.domain.policies import ExtractionRow, FlattenResult, flatten_extractions


def test_flatten_simple_scalars() -> None:
    result = flatten_extractions({"name": "Foo", "score": 4.5})
    assert isinstance(result, FlattenResult)
    rows_by_path = {r.field_path: r for r in result.rows}
    assert rows_by_path["name"].value_text == "Foo"
    assert rows_by_path["name"].value_numeric is None
    assert rows_by_path["score"].value_numeric == 4.5
    assert result.warnings == []


def test_flatten_nested_object() -> None:
    result = flatten_extractions({"evaluation": {"rigor_rating": 4}})
    rows_by_path = {r.field_path: r for r in result.rows}
    assert "evaluation.rigor_rating" in rows_by_path
    assert rows_by_path["evaluation.rigor_rating"].value_numeric == 4


def test_flatten_array_of_strings() -> None:
    result = flatten_extractions({"tags": ["alpha", "beta"]})
    rows_by_path = {r.field_path: r for r in result.rows}
    assert rows_by_path["tags[0]"].value_text == "alpha"
    assert rows_by_path["tags[1]"].value_text == "beta"


def test_flatten_array_of_objects() -> None:
    data = {
        "comparisons": [
            {"name": "Adam", "improvement": "2.3%"},
            {"name": "SGD", "improvement": "5.1%"},
        ]
    }
    result = flatten_extractions(data)
    rows_by_path = {r.field_path: r for r in result.rows}
    assert rows_by_path["comparisons[0].name"].value_text == "Adam"
    assert rows_by_path["comparisons[0].improvement"].value_text == "2.3%"
    assert rows_by_path["comparisons[1].name"].value_text == "SGD"
    assert rows_by_path["comparisons[1].improvement"].value_text == "5.1%"


def test_flatten_boolean_values() -> None:
    result = flatten_extractions({"uses_stats": True, "is_review": False})
    rows_by_path = {r.field_path: r for r in result.rows}
    assert rows_by_path["uses_stats"].value_boolean == 1
    assert rows_by_path["is_review"].value_boolean == 0


def test_flatten_null_value() -> None:
    result = flatten_extractions({"field": None})
    rows_by_path = {r.field_path: r for r in result.rows}
    row = rows_by_path["field"]
    assert row.value_text is None
    assert row.value_numeric is None
    assert row.value_boolean is None


def test_flatten_integer_values() -> None:
    result = flatten_extractions({"count": 42})
    rows_by_path = {r.field_path: r for r in result.rows}
    assert rows_by_path["count"].value_numeric == 42


def test_flatten_empty_object() -> None:
    result = flatten_extractions({})
    assert result.rows == []
    assert result.warnings == []


def test_flatten_deeply_nested() -> None:
    data = {"a": {"b": {"c": "deep"}}}
    result = flatten_extractions(data)
    rows_by_path = {r.field_path: r for r in result.rows}
    assert rows_by_path["a.b.c"].value_text == "deep"


def test_flatten_entity_type_and_ref_propagated() -> None:
    result = flatten_extractions(
        {"field": "val"},
        entity_type="cited_paper",
        entity_ref="ref-123",
    )
    assert len(result.rows) == 1
    assert result.rows[0].entity_type == "cited_paper"
    assert result.rows[0].entity_ref == "ref-123"


def test_flatten_default_entity_type_is_paper() -> None:
    result = flatten_extractions({"field": "val"})
    assert result.rows[0].entity_type == "paper"
    assert result.rows[0].entity_ref is None


def test_flatten_appendix_b_example() -> None:
    """Test the full Appendix B example from the design doc."""
    data = {
        "evaluation": {
            "rigor_rating": 4,
            "statistical_tests_used": True,
        },
        "datasets_used": ["ImageNet", "CIFAR-10"],
        "comparisons": [
            {"name": "Adam", "improvement_claimed": "2.3%"},
            {"name": "SGD", "improvement_claimed": "5.1%"},
        ],
    }
    result = flatten_extractions(data)
    rows_by_path = {r.field_path: r for r in result.rows}

    assert rows_by_path["evaluation.rigor_rating"].value_numeric == 4
    assert rows_by_path["evaluation.statistical_tests_used"].value_boolean == 1
    assert rows_by_path["datasets_used[0]"].value_text == "ImageNet"
    assert rows_by_path["datasets_used[1]"].value_text == "CIFAR-10"
    assert rows_by_path["comparisons[0].name"].value_text == "Adam"
    assert rows_by_path["comparisons[0].improvement_claimed"].value_text == "2.3%"
    assert rows_by_path["comparisons[1].name"].value_text == "SGD"
    assert rows_by_path["comparisons[1].improvement_claimed"].value_text == "5.1%"
    assert len(result.rows) == 8
    assert result.warnings == []


def test_extraction_row_satisfies_extraction_protocol() -> None:
    """ExtractionRow should have the fields expected by ports.Extraction."""
    row = ExtractionRow(
        entity_type="paper",
        entity_ref=None,
        field_path="test",
        value_text="x",
        value_numeric=None,
        value_boolean=None,
    )
    assert row.entity_type == "paper"
    assert row.field_path == "test"
    assert row.value_text == "x"
