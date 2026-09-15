from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from papers.app.ports import BlobStore, LLMResponse, PaperProjectStore, PaperStore, ProjectStore
from papers.app.use_cases.ideation import (
    IdeateProjectRequest,
    IdeateProjectUseCase,
    PlanIdeaRequest,
    PlanIdeaUseCase,
)
from papers.domain.errors import OutputValidationFailed
from papers.domain.ideation_bundle import (
    BundleIntegrityError,
    BundleType,
    verify_manifest,
    write_manifest,
)
from tests.investigation_plan_test_data import valid_investigation_plan_payload


@dataclass
class FakeProjectStore:
    def get(self, project_id: str) -> dict[str, Any] | None:
        return {"project_id": project_id, "name": "Test Project"}


@dataclass
class FakeMembershipStore:
    paper_ids: list[str]

    def list_paper_ids(self, project_id: str, label: str | None = None) -> list[str]:
        return self.paper_ids


@dataclass
class FakePaperStore:
    papers: dict[str, dict[str, Any]]

    def get(self, paper_id: str) -> dict[str, Any] | None:
        return self.papers.get(paper_id)


@dataclass
class FakeBlobStore:
    paths: dict[str, Path]

    def get_markdown_path(self, paper_id: str) -> Path | None:
        return self.paths.get(paper_id)


@dataclass
class FakeLLM:
    responses: list[str]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {"prompt": prompt, "profile": profile, "model": model, "timeout_s": timeout_s}
        )
        return LLMResponse(text=self.responses.pop(0), tokens_in=10, tokens_out=20, cost_usd=None)


def _generation() -> str:
    return json.dumps(
        {
            "question": "Find a testable gap",
            "evidence_cards": [
                {
                    "card_id": "card-1",
                    "category": "method",
                    "claim_kind": "paper_claim",
                    "statement": "The method predicts masked representations.",
                    "excerpt_ids": ["paper-1:e001"],
                    "uncertainty": None,
                }
            ],
            "ideas": [
                {
                    "idea_id": "idea-1",
                    "title": "Adaptive masks",
                    "gap": "Mask schedules are not compared.",
                    "mechanism": "Adapt masking to volatility.",
                    "citation_excerpt_ids": ["paper-1:e001"],
                    "known_overlap": "Builds on the cited masking method.",
                    "falsifiable_question": "Do adaptive masks reduce forecast error?",
                    "smallest_test": "Compare fixed and adaptive masks on one split.",
                    "data_assumptions": "One public time-series split exists.",
                    "model_assumptions": "Mask scheduling is configurable.",
                    "compute_assumptions": "Two pilot runs fit one GPU.",
                    "feasibility_uncertainty": "Runtime and memory are not reported.",
                }
            ],
        }
    )


def _critique() -> str:
    return json.dumps(
        {
            "reviews": [
                {
                    "idea_id": "idea-1",
                    "verdict": "keep",
                    "rationale": "The comparison is falsifiable.",
                    "overlap": "Uses the paper's masking mechanism.",
                    "contradiction": None,
                    "uncertainty": "Feasibility remains unmeasured.",
                    "duplicate_of": None,
                    "evidence_excerpt_ids": ["paper-1:e001"],
                }
            ]
        }
    )


def _use_case(tmp_path: Path, llm: FakeLLM, paper_count: int = 1) -> IdeateProjectUseCase:
    paths: dict[str, Path] = {}
    papers: dict[str, dict[str, Any]] = {}
    for index in range(paper_count):
        paper_id = f"paper-{index + 1}"
        path = tmp_path / f"{paper_id}.md"
        path.write_text("# Abstract\nThe method predicts masked representations.\n")
        paths[paper_id] = path
        papers[paper_id] = {"paper_id": paper_id, "title": f"Paper {index + 1}"}
    return IdeateProjectUseCase(
        project_store=cast(ProjectStore, FakeProjectStore()),
        paper_project_store=cast(PaperProjectStore, FakeMembershipStore(list(papers))),
        paper_store=cast(PaperStore, FakePaperStore(papers)),
        blob_store=cast(BlobStore, FakeBlobStore(paths)),
        llm_client=llm,
        repo_root=tmp_path,
    )


def test_ideate_project_uses_exactly_generation_then_critic(tmp_path: Path) -> None:
    llm = FakeLLM([_generation(), _critique()])

    bundle = _use_case(tmp_path, llm).run(
        IdeateProjectRequest(
            project_id="project-1",
            question="Find a testable gap",
            profile={},
            model="local-model",
            critic_model=None,
            max_papers=12,
            excerpt_bytes=1200,
            max_excerpts_per_paper=6,
            timeout_s=60,
            max_tokens=4000,
        )
    )

    assert len(llm.calls) == 2
    assert "The method predicts masked representations." in llm.calls[1]["prompt"]
    assert '"sha256":' in llm.calls[1]["prompt"]
    generation_schema = llm.calls[0]["profile"]["chat_options"]["response_format"]["json_schema"][
        "schema"
    ]
    expected_excerpt_ids = ["paper-1:e001"]
    assert (
        generation_schema["$defs"]["EvidenceCard"]["properties"]["excerpt_ids"]["items"]["enum"]
        == expected_excerpt_ids
    )
    assert (
        generation_schema["$defs"]["DraftIdea"]["properties"]["citation_excerpt_ids"]["items"][
            "enum"
        ]
        == expected_excerpt_ids
    )
    critique_schema = llm.calls[1]["profile"]["chat_options"]["response_format"]["json_schema"][
        "schema"
    ]
    assert (
        critique_schema["$defs"]["IdeaCritique"]["properties"]["evidence_excerpt_ids"]["items"][
            "enum"
        ]
        == expected_excerpt_ids
    )
    assert llm.calls[1]["profile"]["chat_options"]["reasoning_effort"] == "none"
    assert {path.name for path in bundle.iterdir()} == {
        "critique.json",
        "evidence-map.json",
        "ideas.json",
        "manifest.json",
        "provenance.json",
        "report.md",
    }
    assert verify_manifest(bundle, BundleType.project_ideation)["report.md"]
    assert "Only selected excerpts" in (bundle / "report.md").read_text()
    assert "Critic evidence: paper-1:e001" in (bundle / "report.md").read_text()


def test_ideation_write_failure_does_not_publish_partial_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_manifest(bundle: Path, names: tuple[str, ...]) -> dict[str, str]:
        raise OSError("simulated manifest failure")

    monkeypatch.setattr("papers.domain.ideation_artifacts.write_manifest", fail_manifest)

    with pytest.raises(OSError, match="simulated manifest failure"):
        _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
            IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
        )

    output = tmp_path / "output" / "project-ideation"
    assert not output.exists() or list(output.iterdir()) == []


def test_ideate_project_rejects_project_overflow_without_llm_call(tmp_path: Path) -> None:
    llm = FakeLLM([])

    with pytest.raises(ValueError, match="contains 2 papers; maximum is 1"):
        _use_case(tmp_path, llm, paper_count=2).run(
            IdeateProjectRequest(
                project_id="project-1",
                question="Find a testable gap",
                profile={},
                model="local-model",
                critic_model=None,
                max_papers=1,
                excerpt_bytes=1200,
                max_excerpts_per_paper=6,
                timeout_s=60,
                max_tokens=4000,
            )
        )

    assert llm.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_papers", 0),
        ("excerpt_bytes", 199),
        ("max_excerpts_per_paper", 0),
        ("max_excerpts_per_paper", 13),
        ("timeout_s", -1),
        ("timeout_s", 0),
        ("timeout_s", 601),
        ("max_tokens", -1),
        ("max_tokens", 0),
        ("max_tokens", 255),
    ],
)
def test_ideate_project_request_rejects_values_outside_cli_bounds(field: str, value: int) -> None:
    values = {
        "project_id": "project-1",
        "question": "Find a testable gap",
        "profile": {},
        "model": "local-model",
        "critic_model": None,
        "max_papers": 12,
        "excerpt_bytes": 1200,
        "max_excerpts_per_paper": 6,
        "timeout_s": 60,
        "max_tokens": 4000,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        IdeateProjectRequest(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("timeout_s", -1),
        ("timeout_s", 0),
        ("timeout_s", 601),
        ("max_tokens", -1),
        ("max_tokens", 0),
        ("max_tokens", 255),
    ],
)
def test_plan_idea_request_rejects_values_outside_cli_bounds(field: str, value: int) -> None:
    values = {
        "bundle": Path("bundle"),
        "idea_id": "idea-1",
        "profile": {},
        "model": "local-model",
        "timeout_s": 60,
        "max_tokens": 4000,
        "selection_note": "test-selected QA demonstration",
    }
    values[field] = value

    with pytest.raises(ValidationError):
        PlanIdeaRequest(**values)


def test_manifest_detects_tampering(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    (bundle / "ideas.json").write_text("{}")

    with pytest.raises(BundleIntegrityError, match="hash mismatch"):
        verify_manifest(bundle, BundleType.project_ideation)


def test_ideation_manifest_rejects_omitted_artifact_hash(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest.pop("ideas.json")
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    (bundle / "ideas.json").write_text("{}")

    with pytest.raises(BundleIntegrityError, match="artifact set"):
        verify_manifest(bundle, BundleType.project_ideation)


def test_manifest_rejects_noncanonical_digest(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["ideas.json"] = "A" * 64
    (bundle / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(BundleIntegrityError, match="digest"):
        verify_manifest(bundle, BundleType.project_ideation)


@pytest.mark.parametrize("manifest_payload", ["{", "[]"])
def test_manifest_rejects_invalid_json_shape(tmp_path: Path, manifest_payload: str) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    (bundle / "manifest.json").write_text(manifest_payload)

    with pytest.raises(
        BundleIntegrityError, match="manifest is missing or invalid|manifest is invalid"
    ):
        verify_manifest(bundle, BundleType.project_ideation)


def test_plan_idea_uses_frozen_bundle_without_stores(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    plan_payload = valid_investigation_plan_payload("Do adaptive masks reduce forecast error?")
    plan_payload["sources"][0] = {"paper_id": "paper-1", "title": "Paper 1"}
    llm = FakeLLM([json.dumps(plan_payload)])

    plan_bundle = PlanIdeaUseCase(llm_client=llm, repo_root=tmp_path).run(
        PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model")
    )

    assert len(llm.calls) == 1
    assert "paper-1:e001" in llm.calls[0]["prompt"]
    plan_schema = llm.calls[0]["profile"]["chat_options"]["response_format"]["json_schema"][
        "schema"
    ]
    for definition in (
        "EvidenceStatement",
        "InformationCompleteness",
        "NumericEstimate",
    ):
        assert plan_schema["$defs"][definition]["properties"]["source_refs"]["items"]["enum"] == [
            "paper-1"
        ]
    assert plan_schema["$defs"]["SourceReference"]["properties"]["paper_id"]["enum"] == ["paper-1"]
    assert (plan_bundle / "investigation-plan.json").exists()
    assert "# Investigation Plan" in (plan_bundle / "report.md").read_text()


def test_plan_write_failure_does_not_publish_partial_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    plan_payload = valid_investigation_plan_payload("Do adaptive masks reduce forecast error?")
    plan_payload["sources"][0] = {"paper_id": "paper-1", "title": "Paper 1"}

    def fail_manifest(bundle: Path, names: tuple[str, ...]) -> dict[str, str]:
        raise OSError("simulated manifest failure")

    monkeypatch.setattr("papers.app.use_cases.ideation.write_manifest", fail_manifest)

    with pytest.raises(OSError, match="simulated manifest failure"):
        PlanIdeaUseCase(llm_client=FakeLLM([json.dumps(plan_payload)]), repo_root=tmp_path).run(
            PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model")
        )

    output = tmp_path / "output" / "selected-idea-plan"
    assert not output.exists() or list(output.iterdir()) == []


def test_plan_manifest_rejects_omitted_artifact_hash(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    plan_payload = valid_investigation_plan_payload("Do adaptive masks reduce forecast error?")
    plan_payload["sources"][0] = {"paper_id": "paper-1", "title": "Paper 1"}
    plan_bundle = PlanIdeaUseCase(
        llm_client=FakeLLM([json.dumps(plan_payload)]), repo_root=tmp_path
    ).run(PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model"))
    manifest = json.loads((plan_bundle / "manifest.json").read_text())
    manifest.pop("report.md")
    (plan_bundle / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(BundleIntegrityError, match="artifact set"):
        verify_manifest(plan_bundle, BundleType.selected_idea_plan)


def test_plan_idea_rejects_tampered_source_bundle_before_llm(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    (bundle / "evidence-map.json").write_text("{}")
    llm = FakeLLM([])

    with pytest.raises(BundleIntegrityError):
        PlanIdeaUseCase(llm_client=llm, repo_root=tmp_path).run(
            PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model")
        )

    assert llm.calls == []


def _rehash_ideation_bundle(bundle: Path) -> None:
    write_manifest(
        bundle,
        ("evidence-map.json", "ideas.json", "critique.json", "provenance.json", "report.md"),
    )


def test_plan_idea_rejects_rehashed_bundle_with_changed_question(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    ideas = json.loads((bundle / "ideas.json").read_text())
    ideas["question"] = "A forged question"
    (bundle / "ideas.json").write_text(json.dumps(ideas))
    _rehash_ideation_bundle(bundle)
    llm = FakeLLM([])

    with pytest.raises(OutputValidationFailed, match="question does not match"):
        PlanIdeaUseCase(llm_client=llm, repo_root=tmp_path).run(
            PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model")
        )

    assert llm.calls == []


def test_plan_idea_rejects_rehashed_bundle_with_project_mismatch(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    evidence = json.loads((bundle / "evidence-map.json").read_text())
    evidence["project_id"] = "forged-project"
    (bundle / "evidence-map.json").write_text(json.dumps(evidence))
    _rehash_ideation_bundle(bundle)

    with pytest.raises(OutputValidationFailed, match="project does not match"):
        PlanIdeaUseCase(llm_client=FakeLLM([]), repo_root=tmp_path).run(
            PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model")
        )


def test_plan_idea_rejects_rehashed_bundle_with_unknown_citation(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    ideas = json.loads((bundle / "ideas.json").read_text())
    ideas["ideas"][0]["citation_excerpt_ids"] = ["forged:e001"]
    (bundle / "ideas.json").write_text(json.dumps(ideas))
    _rehash_ideation_bundle(bundle)
    llm = FakeLLM([])

    with pytest.raises(OutputValidationFailed, match="outside frozen evidence"):
        PlanIdeaUseCase(llm_client=llm, repo_root=tmp_path).run(
            PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model")
        )

    assert llm.calls == []


def test_plan_idea_rejects_rehashed_bundle_with_incomplete_critique(tmp_path: Path) -> None:
    bundle = _use_case(tmp_path, FakeLLM([_generation(), _critique()])).run(
        IdeateProjectRequest.defaults("project-1", "Find a testable gap", {}, "local-model")
    )
    (bundle / "critique.json").write_text('{"reviews": []}')
    _rehash_ideation_bundle(bundle)
    llm = FakeLLM([])

    with pytest.raises(OutputValidationFailed, match="exactly the generated idea IDs"):
        PlanIdeaUseCase(llm_client=llm, repo_root=tmp_path).run(
            PlanIdeaRequest.defaults(bundle, "idea-1", {}, "local-model")
        )

    assert llm.calls == []
