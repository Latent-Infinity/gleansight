from __future__ import annotations

import pytest

from gleansight.api.models import OperationError
from gleansight.api.papers.grounding import VerifySource, verify
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.synthesis_sources import SynthesisRetrieval
from tests.api.papers.support import call, identifier
from tests.api.papers.test_providers import readable_project


def test_source_verification_exposes_stale_and_missing(
    populated: ApiRuntime, providers: None
) -> None:
    project = readable_project(populated)
    call(populated, "indexes.rebuild-vector", {})
    base = populated.papers
    source = SynthesisRetrieval(
        base.embedder,
        base.vector_index,
        base.paper_store,
        base.blob_store,
        base.paper_project_store,
    ).retrieve("What?", project, 1)[0]
    request = VerifySource(source=source, project_id=project)
    current = verify(populated, request)
    assert isinstance(current, dict) and current["status"] == "valid"
    other = identifier(call(populated, "projects.create", {"name": "Empty"}), "project_id")
    with pytest.raises(OperationError, match="outside"):
        verify(populated, VerifySource(source=source, project_id=other))
    path = base.blob_store.get_markdown_path("paper-1")
    assert path is not None
    path.write_bytes(path.read_bytes() + b"\nChanged.")
    stale = verify(populated, request)
    assert isinstance(stale, dict) and stale["status"] == "stale"
    path.unlink()
    missing = verify(populated, request)
    assert isinstance(missing, dict) and missing["status"] == "missing"


@pytest.mark.parametrize(
    "scenario,expected", [("unscoped", "valid"), ("renamed", "stale"), ("unreadable", "missing")]
)
def test_source_verification_handles_current_artifact_changes(
    populated: ApiRuntime,
    providers: None,
    scenario: str,
    expected: str,
) -> None:
    project = readable_project(populated)
    call(populated, "indexes.rebuild-vector", {})
    base = populated.papers
    source = SynthesisRetrieval(
        base.embedder,
        base.vector_index,
        base.paper_store,
        base.blob_store,
        base.paper_project_store,
    ).retrieve("What?", project, 1)[0]
    if scenario == "renamed":
        base.paper_store.update_metadata("paper-1", {"title": "Renamed paper"})
    if scenario == "unreadable":
        path = base.blob_store.get_markdown_path("paper-1")
        assert path is not None
        path.unlink()
        path.mkdir()
    result = verify(populated, VerifySource(source=source))
    assert isinstance(result, dict) and result["status"] == expected
