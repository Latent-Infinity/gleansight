from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from papers.domain.ideation import Critique, EvidenceMap, GenerationOutput
from papers.domain.ideation_bundle import (
    IDEATION_ARTIFACTS,
    atomic_bundle,
    write_json,
    write_manifest,
)
from papers.domain.ideation_renderer import render_ideation_report


@dataclass(frozen=True, slots=True)
class IdeationBundleData:
    evidence: EvidenceMap
    generation: GenerationOutput
    critique: Critique
    generation_model: str
    critic_model: str


def write_ideation_bundle(repo_root: Path, data: IdeationBundleData) -> Path:
    with atomic_bundle(repo_root, "project-ideation") as (staging, published):
        write_json(staging / "evidence-map.json", data.evidence.model_dump(mode="json"))
        write_json(staging / "ideas.json", data.generation.model_dump(mode="json"))
        write_json(staging / "critique.json", data.critique.model_dump(mode="json"))
        (staging / "report.md").write_text(
            render_ideation_report(data.evidence, data.generation, data.critique)
        )
        write_json(
            staging / "provenance.json",
            {
                "created_at": datetime.now(UTC).isoformat(),
                "project_id": data.evidence.project_id,
                "question": data.generation.question,
                "generation_model": data.generation_model,
                "critic_model": data.critic_model,
                "llm_calls": 2,
                "full_text_analyzed": False,
                "literature_search_performed": False,
                "human_approval_claimed": False,
                "hashes_are_authenticated_provenance": False,
            },
        )
        write_manifest(staging, IDEATION_ARTIFACTS)
    return published
