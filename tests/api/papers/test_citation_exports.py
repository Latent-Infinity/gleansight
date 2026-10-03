from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Success
from gleansight.api.papers.exports import operations
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.domain.citations import ExportManifest
from papers.infra.piccolo.stores import PiccoloPaperExternalIdStore, PiccoloPaperStore


@pytest.fixture
def export_api(tmp_path: Path) -> GleansightAPI:
    runtime = ApiRuntime(ApiConfiguration(repo_root=tmp_path))
    runtime.paper_database.bind_tables()
    PiccoloPaperStore().create_paper(
        {
            "paper_id": "paper-1",
            "title": 'Étude {graphs} & "quotes"',
            "authors": ["García, José", "研究者"],
            "year": 2024,
            "venue": "R&D",
        }
    )
    PiccoloPaperExternalIdStore().create_external_ids("paper-1", {"DOI": "10.1/example"})
    return GleansightAPI(ApiConfiguration(repo_root=tmp_path), operations=operations())


@pytest.mark.parametrize("format", ["bibtex", "ris", "csv", "extractions"])
def test_export_creates_verified_snapshot(export_api: GleansightAPI, format: str) -> None:
    # Given a persisted paper with multilingual metadata.
    # When exporting through the shared client.
    result = export_api.call("papers.exports.create", {"paper_ids": ["paper-1"], "format": format})
    # Then the artifacts and immutable manifest verify through the public operation.
    assert isinstance(result, Success), result
    paths = TypeAdapter(dict[str, str]).validate_python(result.data)
    manifest = ExportManifest.model_validate_json(Path(paths["manifest_path"]).read_text())
    assert manifest.paper_ids == ("paper-1",)
    assert manifest.papers[0].doi == "10.1/example"
    assert Path(paths["artifact_path"]).exists()
    verified = export_api.call("papers.exports.verify", {"manifest_path": paths["manifest_path"]})
    assert isinstance(verified, Success), verified
    assert verified.data == {"valid": True}


def artifact_paths(api: GleansightAPI, parameters: dict[str, JsonValue]) -> dict[str, str]:
    result = api.call("papers.exports.create", parameters)
    assert isinstance(result, Success), result
    return TypeAdapter(dict[str, str]).validate_python(result.data)


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"paper_ids": ["paper-1"], "project_id": "project-1"},
        {"paper_ids": ["missing"]},
        {"project_id": "missing"},
        {"paper_ids": ["paper-1"], "format": "unsupported"},
    ],
)
def test_export_rejects_invalid_selection(
    export_api: GleansightAPI, parameters: dict[str, JsonValue]
) -> None:
    from gleansight.api.models import Failure

    assert isinstance(export_api.call("papers.exports.create", parameters), Failure)


@pytest.mark.parametrize("target", ["artifact_path", "manifest_path"])
def test_verification_rejects_tampering(export_api: GleansightAPI, target: str) -> None:
    from gleansight.api.models import Failure

    paths = artifact_paths(export_api, {"paper_ids": ["paper-1"]})
    Path(paths[target]).write_text("tampered", encoding="utf-8")
    result = export_api.call("papers.exports.verify", {"manifest_path": paths["manifest_path"]})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"


def test_reanalysis_preserves_snapshot(export_api: GleansightAPI, tmp_path: Path) -> None:
    from papers.infra.piccolo.stores import PiccoloAnalysisRunStore

    runtime = ApiRuntime(ApiConfiguration(repo_root=tmp_path))
    db = runtime.paper_database
    output = tmp_path / "output.json"
    output.write_text('{"score": 0.25}')
    PiccoloAnalysisRunStore().create_run("run-1", "paper-1", "prompt-1", "profile", "model")
    db.execute(
        "UPDATE analysis_runs SET output_blob_path_json = ? WHERE run_id = ?",
        [str(output), "run-1"],
    )
    db.execute(
        "INSERT INTO analysis_extractions "
        "(extraction_id, run_id, paper_id, prompt_version_id, entity_type, field_path, "
        "value_numeric, value_text, value_boolean, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, CURRENT_TIMESTAMP)",
        ["e-1", "run-1", "paper-1", "prompt-1", "paper", "score", 0.25],
    )
    paths = artifact_paths(export_api, {"paper_ids": ["paper-1"], "format": "extractions"})
    before = {key: Path(value).read_bytes() for key, value in paths.items()}
    rows = TypeAdapter(list[dict[str, JsonValue]]).validate_json(before["artifact_path"])
    assert rows[0]["value"] == 0.25
    assert rows[0]["source_locator"] is None
    manifest = ExportManifest.model_validate_json(before["manifest_path"])
    assert manifest.runs[0].artifacts[0].sha256 is not None
    output.write_text('{"score": 0.75}')
    db.execute("UPDATE analysis_extractions SET value_numeric = 0.75")
    newer = artifact_paths(export_api, {"paper_ids": ["paper-1"], "format": "extractions"})
    assert newer["manifest_path"] != paths["manifest_path"]
    assert all(Path(paths[key]).read_bytes() == content for key, content in before.items())
    assert isinstance(
        export_api.call("papers.exports.verify", {"manifest_path": paths["manifest_path"]}), Success
    )


def test_project_scope_and_missing_metadata(export_api: GleansightAPI, tmp_path: Path) -> None:
    from papers.infra.piccolo.stores import PiccoloProjectStore

    runtime = ApiRuntime(ApiConfiguration(repo_root=tmp_path))
    db = runtime.paper_database
    PiccoloPaperStore().create_paper({"paper_id": "paper-2", "title": "Sparse"})
    project = "project-1"
    PiccoloProjectStore().create_project(project, "Cohort")
    db.execute(
        "INSERT INTO paper_projects (paper_id, project_id) VALUES (?, ?)", ["paper-2", project]
    )
    paths = artifact_paths(export_api, {"project_id": project, "format": "ris"})
    manifest = ExportManifest.model_validate_json(Path(paths["manifest_path"]).read_bytes())
    assert manifest.paper_ids == ("paper-2",)
    assert set(manifest.missing_fields["paper-2"]) == {"authors", "year", "venue", "doi"}
    assert "DO  -" not in Path(paths["artifact_path"]).read_text()


def test_empty_project_is_rejected(export_api: GleansightAPI, tmp_path: Path) -> None:
    from gleansight.api.models import Failure
    from papers.infra.piccolo.stores import PiccoloProjectStore

    ApiRuntime(ApiConfiguration(repo_root=tmp_path)).paper_database.bind_tables()
    PiccoloProjectStore().create_project("empty-project", "Empty")
    result = export_api.call("papers.exports.create", {"project_id": "empty-project"})
    assert isinstance(result, Failure)
    assert result.error.code == "invalid_request"


@pytest.mark.parametrize(
    "value_column, stored, expected",
    [
        ("value_text", "quoted {value} — 研究", "quoted {value} — 研究"),
        ("value_boolean", 0, False),
        ("value_boolean", 1, True),
        ("value_text", None, None),
    ],
)
def test_extraction_values_preserve_types(
    export_api: GleansightAPI,
    tmp_path: Path,
    value_column: str,
    stored: JsonValue,
    expected: JsonValue,
) -> None:
    runtime = ApiRuntime(ApiConfiguration(repo_root=tmp_path))
    db = runtime.paper_database
    db.execute(
        "INSERT INTO analysis_extractions "
        "(extraction_id, run_id, paper_id, prompt_version_id, entity_type, field_path, "
        "value_text, value_numeric, value_boolean, created_at) "
        "VALUES ('e-typed', 'r-typed', 'paper-1', 'v-typed', 'paper', 'typed', "
        "NULL, NULL, NULL, CURRENT_TIMESTAMP)"
    )
    assert value_column in {"value_text", "value_boolean"}
    db.execute(f"UPDATE analysis_extractions SET {value_column} = ?", [stored])
    paths = artifact_paths(export_api, {"paper_ids": ["paper-1"], "format": "extractions"})
    rows = TypeAdapter(list[dict[str, JsonValue]]).validate_json(
        Path(paths["artifact_path"]).read_bytes()
    )
    assert rows[0]["value"] == expected
    assert type(rows[0]["value"]) is type(expected)
