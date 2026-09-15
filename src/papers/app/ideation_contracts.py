from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from papers.domain.ideation import Critique, GenerationOutput
from papers.domain.ideation_bundle import JsonValue
from papers.domain.investigation_evidence import CompletionStr, ContractModel, NonEmptyStr
from papers.domain.investigation_prompt import investigation_plan_schema

type LLMProfile = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class IdeationInputError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class SchemaShapeError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class StructuredOutputOptions:
    name: str
    schema: dict[str, JsonValue]
    max_tokens: int


class IdeateProjectRequest(ContractModel):
    project_id: NonEmptyStr
    question: NonEmptyStr
    profile: LLMProfile
    model: CompletionStr
    critic_model: CompletionStr | None
    max_papers: int = Field(ge=1)
    excerpt_bytes: int = Field(ge=200)
    max_excerpts_per_paper: int = Field(ge=1, le=12)
    timeout_s: int = Field(ge=1, le=600)
    max_tokens: int = Field(ge=256)

    @classmethod
    def defaults(
        cls, project_id: str, question: str, profile: LLMProfile, model: str
    ) -> IdeateProjectRequest:
        return cls(
            project_id=project_id,
            question=question,
            profile=profile,
            model=model,
            critic_model=None,
            max_papers=12,
            excerpt_bytes=1200,
            max_excerpts_per_paper=6,
            timeout_s=300,
            max_tokens=8000,
        )


class PlanIdeaRequest(ContractModel):
    bundle: Path
    idea_id: NonEmptyStr
    profile: LLMProfile
    model: CompletionStr
    timeout_s: int = Field(ge=1, le=600)
    max_tokens: int = Field(ge=256)
    selection_note: CompletionStr

    @classmethod
    def defaults(
        cls, bundle: Path, idea_id: str, profile: LLMProfile, model: str
    ) -> PlanIdeaRequest:
        return cls(
            bundle=bundle,
            idea_id=idea_id,
            profile=profile,
            model=model,
            timeout_s=300,
            max_tokens=8000,
            selection_note="test-selected QA demonstration",
        )


def structured_profile(profile: LLMProfile, output: StructuredOutputOptions) -> LLMProfile:
    resolved = dict(profile)
    existing_options = resolved.get("chat_options")
    options = dict(existing_options) if isinstance(existing_options, dict) else {}
    options["max_tokens"] = output.max_tokens
    options["temperature"] = 0.0
    options["reasoning_effort"] = "none"
    options["response_format"] = {
        "type": "json_schema",
        "json_schema": {"name": output.name, "strict": True, "schema": output.schema},
    }
    resolved["chat_options"] = options
    return resolved


def generation_schema(allowed_excerpt_ids: list[str]) -> dict[str, JsonValue]:
    schema = GenerationOutput.model_json_schema()
    definitions = schema["$defs"]
    definitions["EvidenceCard"]["properties"]["excerpt_ids"]["items"]["enum"] = allowed_excerpt_ids
    definitions["DraftIdea"]["properties"]["citation_excerpt_ids"]["items"]["enum"] = (
        allowed_excerpt_ids
    )
    return schema


def critique_schema(allowed_excerpt_ids: list[str]) -> dict[str, JsonValue]:
    schema = Critique.model_json_schema()
    schema["$defs"]["IdeaCritique"]["properties"]["evidence_excerpt_ids"]["items"]["enum"] = (
        allowed_excerpt_ids
    )
    return schema


def investigation_schema(allowed_source_ids: list[str]) -> dict[str, JsonValue]:
    schema = investigation_plan_schema()
    definitions = _json_object(schema["$defs"])
    enum_values: list[JsonValue] = []
    enum_values.extend(allowed_source_ids)
    for definition_name in (
        "EvidenceStatement",
        "InformationCompleteness",
        "NumericEstimate",
    ):
        definition = _json_object(definitions[definition_name])
        properties = _json_object(definition["properties"])
        source_refs = _json_object(properties["source_refs"])
        _json_object(source_refs["items"])["enum"] = enum_values
    source_reference = _json_object(definitions["SourceReference"])
    source_properties = _json_object(source_reference["properties"])
    _json_object(source_properties["paper_id"])["enum"] = enum_values
    return schema


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    raise SchemaShapeError("expected JSON object in generated schema")
