from pathlib import Path

import pytest
from pydantic import ValidationError

from gleansight.api.papers import operations
from gleansight.api.runtime import ApiConfiguration, ApiRuntime


@pytest.fixture
def runtime(tmp_path: Path) -> ApiRuntime:
    return ApiRuntime(ApiConfiguration(repo_root=tmp_path))


def test_invalid_request_has_no_database_effect(runtime: ApiRuntime) -> None:
    # Given
    operation = next(item for item in operations() if item.name == "papers.projects.create")
    # When / Then
    with pytest.raises(ValidationError):
        operation.invoke(runtime, {"name": "x", "unexpected": True})
    assert not (runtime.repo_root / "data").exists()


def test_project_creation_is_idempotent(runtime: ApiRuntime) -> None:
    # Given
    operation = next(item for item in operations() if item.name == "papers.projects.create")
    first = operation.invoke(runtime, {"name": "Isolated research"})
    # When
    second = operation.invoke(runtime, {"name": "Isolated research"})
    # Then
    assert second == first
    row = runtime.paper_database.fetchone("SELECT count(*) AS n FROM projects")
    assert row is not None and row["n"] == 1


def test_projects_page_continues_without_duplicates(runtime: ApiRuntime) -> None:
    # Given
    catalog = {item.name: item for item in operations()}
    for name in ("alpha", "beta", "gamma"):
        catalog["papers.projects.create"].invoke(runtime, {"name": name})
    # When
    first = catalog["papers.projects.list"].invoke(runtime, {"limit": 2})
    second = catalog["papers.projects.list"].invoke(runtime, {"limit": 2, "offset": 2})
    # Then
    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["next_offset"] == 2
    assert second["next_offset"] is None
    assert isinstance(first["items"], list) and isinstance(second["items"], list)
    assert len(first["items"]) == 2 and len(second["items"]) == 1
