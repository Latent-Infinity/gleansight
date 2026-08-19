from __future__ import annotations

from papers.domain.policies import ValidationIssue, ValidationResult, validate_extraction_output


def test_validate_no_schema_always_valid() -> None:
    result = validate_extraction_output({"anything": "goes"}, schema=None)
    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.issues == []


def test_validate_valid_data() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["name"],
    }
    result = validate_extraction_output({"name": "Foo", "score": 4.5}, schema=schema)
    assert result.valid is True
    assert result.issues == []


def test_validate_required_field_missing() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
        },
        "required": ["name"],
    }
    result = validate_extraction_output({}, schema=schema)
    assert result.valid is False
    assert len(result.issues) >= 1
    assert any(i.severity == "error" for i in result.issues)
    assert any("name" in i.path for i in result.issues)


def test_validate_optional_field_wrong_type() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "number"},
        },
        "required": ["name"],
    }
    result = validate_extraction_output({"name": "Foo", "score": "not-a-number"}, schema=schema)
    assert result.valid is True  # only optional field failed
    assert len(result.issues) >= 1
    assert all(i.severity == "warning" for i in result.issues)


def test_validate_multiple_issues() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "score": {"type": "number"},
            "tags": {"type": "array"},
        },
        "required": ["name", "score"],
    }
    # name missing (required), tags wrong type (optional)
    result = validate_extraction_output({"score": "bad", "tags": 42}, schema=schema)
    assert result.valid is False
    error_issues = [i for i in result.issues if i.severity == "error"]
    warning_issues = [i for i in result.issues if i.severity == "warning"]
    assert len(error_issues) >= 1  # missing name
    assert len(warning_issues) >= 1  # score wrong type or tags wrong type


def test_validate_nested_required_field() -> None:
    schema = {
        "type": "object",
        "properties": {
            "evaluation": {
                "type": "object",
                "properties": {
                    "rigor": {"type": "number"},
                },
                "required": ["rigor"],
            },
        },
        "required": ["evaluation"],
    }
    result = validate_extraction_output({"evaluation": {}}, schema=schema)
    assert result.valid is False
    assert any("rigor" in i.path for i in result.issues)


def test_validate_value_preview_truncated() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "number"},
        },
    }
    long_value = "x" * 200
    result = validate_extraction_output({"name": long_value}, schema=schema)
    assert len(result.issues) >= 1
    for issue in result.issues:
        if issue.value_preview is not None:
            assert len(issue.value_preview) <= 100


def test_validate_empty_object_all_required_missing() -> None:
    schema = {
        "type": "object",
        "properties": {
            "a": {"type": "string"},
            "b": {"type": "string"},
        },
        "required": ["a", "b"],
    }
    result = validate_extraction_output({}, schema=schema)
    assert result.valid is False
    error_issues = [i for i in result.issues if i.severity == "error"]
    assert len(error_issues) >= 2


def test_validation_issue_fields() -> None:
    issue = ValidationIssue(
        path="name",
        severity="error",
        message="missing",
        value_preview=None,
    )
    assert issue.path == "name"
    assert issue.severity == "error"
    assert issue.message == "missing"
    assert issue.value_preview is None
