from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from papers.app import ports
from papers.domain.errors import InvalidExtractionSchemaError, NotFoundError, ValidationError
from papers.domain.models import OutputFormat


def _new_id() -> str:
    return str(uuid.uuid4())


def _validate_output_format(output_format: str) -> OutputFormat:
    try:
        return OutputFormat(output_format)
    except ValueError as exc:
        raise ValidationError(f"unsupported output_format: {output_format}") from exc


def _validate_schema(schema: dict[str, Any]) -> None:
    try:
        import jsonschema
    except Exception as exc:  # pragma: no cover - optional dependency
        raise InvalidExtractionSchemaError("jsonschema is required for schema validation") from exc
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.exceptions.SchemaError as exc:
        raise InvalidExtractionSchemaError(str(exc)) from exc


@dataclass(frozen=True)
class CreatePromptUseCase:
    prompt_store: ports.PromptStore

    def __call__(
        self,
        *,
        name: str,
        description: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        if not name.strip():
            raise ValidationError("prompt name is required")
        prompt_id = _new_id()
        self.prompt_store.create_prompt(
            prompt_id,
            name,
            description=description,
            domain=domain,
            tags=tags,
        )
        return prompt_id


@dataclass(frozen=True)
class CreatePromptVersionUseCase:
    prompt_store: ports.PromptStore

    def __call__(
        self,
        *,
        prompt_id: str,
        body: str,
        output_format: str,
        extraction_schema_json: dict[str, Any] | None = None,
    ) -> tuple[str, int]:
        if not body.strip():
            raise ValidationError("prompt body is required")
        prompt = self.prompt_store.get_prompt(prompt_id)
        if prompt is None:
            raise NotFoundError("prompt not found")
        parsed_format = _validate_output_format(output_format)
        if parsed_format is OutputFormat.markdown_only and extraction_schema_json is not None:
            raise ValidationError("markdown_only output cannot define extraction_schema_json")
        if extraction_schema_json is not None:
            _validate_schema(extraction_schema_json)
        latest = self.prompt_store.get_latest_version(prompt_id)
        next_version = 1 if latest is None else int(latest["version"]) + 1
        prompt_version_id = _new_id()
        self.prompt_store.create_version(
            prompt_version_id,
            prompt_id,
            next_version,
            body,
            parsed_format.value,
            extraction_schema_json,
        )
        return prompt_version_id, next_version
