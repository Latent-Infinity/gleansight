from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from papers.app.use_cases.prompts import CreatePromptUseCase, CreatePromptVersionUseCase
from papers.domain.errors import InvalidExtractionSchemaError, NotFoundError, ValidationError


@dataclass
class FakePromptStore:
    prompts: dict[str, dict[str, Any]] = field(default_factory=dict)
    versions: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_prompts: list[dict[str, Any]] = field(default_factory=list)
    created_versions: list[dict[str, Any]] = field(default_factory=list)

    def create_prompt(
        self,
        prompt_id: str,
        name: str,
        description: str | None = None,
        domain: str | None = None,
        tags: list[str] | None = None,
        created_at: str | None = None,
    ) -> None:
        self.prompts[prompt_id] = {
            "prompt_id": prompt_id,
            "name": name,
            "description": description,
            "domain": domain,
            "tags": tags,
        }
        self.created_prompts.append(self.prompts[prompt_id])

    def get_prompt(self, prompt_id: str):
        return self.prompts.get(prompt_id)

    def get_latest_version(self, prompt_id: str):
        for version in self.versions.values():
            if version["prompt_id"] == prompt_id:
                return version
        return None

    def create_version(
        self,
        prompt_version_id: str,
        prompt_id: str,
        version: int,
        body: str,
        output_format: str,
        extraction_schema_json: dict | None = None,
    ) -> None:
        payload = {
            "prompt_version_id": prompt_version_id,
            "prompt_id": prompt_id,
            "version": version,
            "body": body,
            "output_format": output_format,
            "extraction_schema_json": extraction_schema_json,
        }
        self.versions[prompt_version_id] = payload
        self.created_versions.append(payload)


def test_create_prompt_stores_metadata() -> None:
    store = FakePromptStore()
    use_case = CreatePromptUseCase(prompt_store=store)

    prompt_id = use_case(
        name="Taxonomy",
        description="Analyze taxonomy",
        domain="nlp",
        tags=["prompt", "taxonomy"],
    )

    assert prompt_id in store.prompts
    assert store.prompts[prompt_id]["name"] == "Taxonomy"
    assert store.prompts[prompt_id]["description"] == "Analyze taxonomy"
    assert store.prompts[prompt_id]["domain"] == "nlp"
    assert store.prompts[prompt_id]["tags"] == ["prompt", "taxonomy"]


def test_create_prompt_version_increments_version() -> None:
    store = FakePromptStore(
        prompts={"prompt": {"prompt_id": "prompt", "name": "Prompt"}},
        versions={"pv1": {"prompt_id": "prompt", "version": 1}},
    )
    use_case = CreatePromptVersionUseCase(prompt_store=store)

    prompt_version_id, version = use_case(
        prompt_id="prompt",
        body="Body",
        output_format="json_only",
        extraction_schema_json={"type": "object", "properties": {"field": {"type": "string"}}},
    )

    assert version == 2
    assert store.versions[prompt_version_id]["version"] == 2
    assert store.versions[prompt_version_id]["output_format"] == "json_only"


def test_create_prompt_version_requires_prompt() -> None:
    store = FakePromptStore()
    use_case = CreatePromptVersionUseCase(prompt_store=store)

    with pytest.raises(NotFoundError):
        use_case(
            prompt_id="missing",
            body="Body",
            output_format="json_only",
        )


def test_create_prompt_version_rejects_markdown_schema() -> None:
    store = FakePromptStore(prompts={"prompt": {"prompt_id": "prompt", "name": "Prompt"}})
    use_case = CreatePromptVersionUseCase(prompt_store=store)

    with pytest.raises(ValidationError):
        use_case(
            prompt_id="prompt",
            body="Body",
            output_format="markdown_only",
            extraction_schema_json={"type": "object"},
        )


def test_create_prompt_version_rejects_invalid_output_format() -> None:
    store = FakePromptStore(prompts={"prompt": {"prompt_id": "prompt", "name": "Prompt"}})
    use_case = CreatePromptVersionUseCase(prompt_store=store)

    with pytest.raises(ValidationError):
        use_case(
            prompt_id="prompt",
            body="Body",
            output_format="xml",
        )


def test_create_prompt_version_rejects_invalid_schema() -> None:
    store = FakePromptStore(prompts={"prompt": {"prompt_id": "prompt", "name": "Prompt"}})
    use_case = CreatePromptVersionUseCase(prompt_store=store)

    with pytest.raises(InvalidExtractionSchemaError):
        use_case(
            prompt_id="prompt",
            body="Body",
            output_format="json_only",
            extraction_schema_json={"type": 123},
        )
