from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import JsonValue, TypeAdapter

from gleansight.api.nsqd.portfolios import (
    ArtifactRequest,
    PlanRequest,
    ProjectRequest,
    plan,
    project,
    replay,
    stage,
)
from nsqd.app.portfolio.artifacts import read_artifact
from nsqd.app.portfolio.inputs import freeze_input, verified_input
from nsqd.domain.contribution import ContributionReport
from nsqd.null_adapters import HashParaphraseEmbedder
from papers.app import composition_root
from papers.app.ports import LLMResponse
from tests.api.nsqd.test_workflows import FIXTURES, ScratchRuntime, mapping
from tests.api.papers.fakes import Converter, Index, Scholar


class OfflineEmbedder(HashParaphraseEmbedder):
    def model_name(self) -> str:
        return self.model_id()


class OfflineLLM:
    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, JsonValue],
        model: str,
        timeout_s: int | None = None,
    ) -> LLMResponse:
        if prompt.startswith("Rank these discovery candidates"):
            payload = TypeAdapter(dict[str, JsonValue]).validate_json(prompt.split("\n\n", 1)[1])
            candidates = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
                payload["candidates"]
            )
            return LLMResponse(
                json.dumps([item["candidate_id"] for item in candidates]), 2, 2, None
            )
        return LLMResponse("A pending mechanism paraphrase for researcher review.", 2, 2, None)


class OfflineScholar(Scholar):
    def search(
        self,
        query: str,
        filters: dict[str, JsonValue],
        max_results: int,
        page_size: int,
        offset: int = 0,
    ) -> list[dict[str, JsonValue]]:
        frozen = freeze_input(FIXTURES / "gamma-fragility.yaml", FIXTURES / "manifest.toml")
        source = verified_input(frozen)["source_paper_id"]
        return [
            {
                "source_paper_id": source,
                "title": "Offline finance mechanism",
                "authors": [],
                "abstract": "A local mechanism description for deterministic acquisition QA.",
            }
        ]


def offline_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(composition_root, "build_docling_converter", Converter)
    monkeypatch.setattr(
        composition_root, "build_configured_ollama_embedder", lambda settings: OfflineEmbedder()
    )
    monkeypatch.setattr(composition_root, "LanceDBVectorIndex", Index)
    monkeypatch.setattr(
        composition_root, "build_openai_compat_client", lambda **kwargs: OfflineLLM()
    )
    monkeypatch.setattr(composition_root, "build_s2_client", lambda **kwargs: OfflineScholar())


def test_real_bridge_api_persistence_and_offline_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    offline_providers(monkeypatch)
    runtime = ScratchRuntime(tmp_path)
    runtime.nsqd.ctx.snapshots.commit("initial", [], schema_version=1)
    planned = mapping(
        plan(runtime, PlanRequest(snapshot_id="initial", domain_policy_id="finance/1"))
    )
    plan_path = Path(TypeAdapter(str).validate_python(mapping(planned["artifact"])["bundle_path"]))
    staged = mapping(stage(runtime, ArtifactRequest(bundle_path=plan_path)))
    staged_path = Path(TypeAdapter(str).validate_python(mapping(staged["artifact"])["bundle_path"]))
    sources = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
        mapping(staged["staged"])["sources"]
    )
    assert len(sources) == 1
    assert len(TypeAdapter(list[str]).validate_python(sources[0]["target_ids"])) == 3
    result = mapping(
        project(
            runtime,
            ProjectRequest(
                bundle_path=staged_path,
                approved_projections=[FIXTURES / "gamma-fragility.yaml"] * 2,
                approval_manifest=FIXTURES / "manifest.toml",
            ),
        )
    )
    report_path = Path(TypeAdapter(str).validate_python(mapping(result["artifact"])["bundle_path"]))
    restarted = ScratchRuntime(tmp_path)
    verified = mapping(replay(restarted, ArtifactRequest(bundle_path=report_path)))
    assert (
        verified["verified"] is True and verified["projections"] == 2 and verified["no_change"] == 1
    )
    report = read_artifact(tmp_path, report_path, ContributionReport)
    assert report.entries[0].created and not report.entries[1].created
    assert not report.entries[0].after.failures
    assert runtime.nsqd.ctx.approved_projection_digests == frozenset()
    assert (tmp_path / report_path / "report.json").is_file()
    (tmp_path / report_path / "report.json").write_text("{}")
    with pytest.raises(ValueError):
        replay(restarted, ArtifactRequest(bundle_path=report_path))
