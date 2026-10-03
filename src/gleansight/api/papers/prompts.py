from __future__ import annotations

from pydantic import JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.papers.common import Page, PromptId, Query, database, one, page
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.prompts import CreatePromptUseCase, CreatePromptVersionUseCase
from papers.domain.models import OutputFormat
from papers.infra.piccolo.stores import PiccoloPromptStore


class CreatePrompt(Request):
    name: Identifier
    description: str | None = None
    domain: str | None = None
    tags: list[Identifier] | None = None


class CreateVersion(PromptId):
    body: Identifier
    output_format: OutputFormat
    extraction_schema_json: dict[str, JsonValue] | None = None


class Versions(Page):
    prompt_id: Identifier


class VersionId(Request):
    prompt_version_id: Identifier


def create(runtime: ApiRuntime, request: CreatePrompt) -> JsonValue:
    database(runtime)
    return {
        "prompt_id": CreatePromptUseCase(PiccoloPromptStore())(
            name=request.name,
            description=request.description,
            domain=request.domain,
            tags=request.tags,
        )
    }


def create_version(runtime: ApiRuntime, request: CreateVersion) -> JsonValue:
    database(runtime)
    version_id, version = CreatePromptVersionUseCase(PiccoloPromptStore())(
        prompt_id=request.prompt_id,
        body=request.body,
        output_format=request.output_format.value,
        extraction_schema_json=request.extraction_schema_json,
    )
    return {"prompt_version_id": version_id, "version": version}


def get(runtime: ApiRuntime, request: PromptId) -> JsonValue:
    one(runtime, Query("SELECT prompt_id FROM prompts WHERE prompt_id = ?", (request.prompt_id,)))
    return json_result(PiccoloPromptStore().get_prompt(request.prompt_id))


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation("papers.prompts.create", "Create a prompt.", CreatePrompt, create, ("write",)),
        Operation(
            "papers.prompts.create-version",
            "Create a validated immutable prompt version.",
            CreateVersion,
            create_version,
            ("write",),
        ),
        Operation(
            "papers.prompts.list",
            "List prompts with pagination.",
            Page,
            lambda r, q: page(r, Query("SELECT * FROM prompts ORDER BY prompt_id"), q),
        ),
        Operation("papers.prompts.get", "Get a prompt.", PromptId, get),
        Operation(
            "papers.prompts.versions",
            "List prompt versions.",
            Versions,
            lambda r, q: page(
                r,
                Query(
                    "SELECT * FROM prompt_versions WHERE prompt_id = ? ORDER BY version",
                    (q.prompt_id,),
                ),
                q,
            ),
        ),
        Operation(
            "papers.prompts.get-version",
            "Get a prompt version.",
            VersionId,
            lambda r, q: one(
                r,
                Query(
                    "SELECT * FROM prompt_versions WHERE prompt_version_id = ?",
                    (q.prompt_version_id,),
                ),
            ),
        ),
    )
