from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from papers.app.use_cases.taxonomy import (
    AttachPaperToProjectUseCase,
    AttachTagToPaperUseCase,
    CreateProjectUseCase,
    CreateTagUseCase,
)
from papers.domain.errors import ConflictError, NotFoundError, ValidationError


@dataclass
class FakePaperStore:
    papers: set[str]

    def get(self, paper_id: str) -> dict[str, Any] | None:
        return {"paper_id": paper_id} if paper_id in self.papers else None


@dataclass
class FakeTagStore:
    tags_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    tags_by_name: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_tag(self, tag_id: str, name: str, tag_type: str, created_at: str | None = None) -> None:
        payload = {"tag_id": tag_id, "name": name, "type": tag_type}
        self.tags_by_id[tag_id] = payload
        self.tags_by_name[name] = payload

    def get(self, tag_id: str) -> dict[str, Any] | None:
        return self.tags_by_id.get(tag_id)

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        return self.tags_by_name.get(name)


@dataclass
class FakePaperTagStore:
    attached: set[tuple[str, str]] = field(default_factory=set)

    def is_attached(self, paper_id: str, tag_id: str) -> bool:
        return (paper_id, tag_id) in self.attached

    def attach(self, paper_id: str, tag_id: str, confidence: float | None = None) -> None:
        self.attached.add((paper_id, tag_id))


@dataclass
class FakeProjectStore:
    projects_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    projects_by_name: dict[str, dict[str, Any]] = field(default_factory=dict)

    def create_project(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        created_at: str | None = None,
    ) -> None:
        payload = {"project_id": project_id, "name": name, "description": description}
        self.projects_by_id[project_id] = payload
        self.projects_by_name[name] = payload

    def get(self, project_id: str) -> dict[str, Any] | None:
        return self.projects_by_id.get(project_id)

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        return self.projects_by_name.get(name)


@dataclass
class FakePaperProjectStore:
    attached: set[tuple[str, str]] = field(default_factory=set)

    def is_attached(self, paper_id: str, project_id: str) -> bool:
        return (paper_id, project_id) in self.attached

    def attach(self, paper_id: str, project_id: str, label: str | None = None) -> None:
        self.attached.add((paper_id, project_id))


def test_create_tag_is_idempotent_by_name() -> None:
    tag_store = FakeTagStore(tags_by_name={"methods": {"tag_id": "tag-1", "type": "method"}})
    use_case = CreateTagUseCase(tag_store=tag_store)

    tag_id = use_case(name="methods", tag_type="method")

    assert tag_id == "tag-1"


def test_create_tag_requires_name() -> None:
    tag_store = FakeTagStore()
    use_case = CreateTagUseCase(tag_store=tag_store)

    with pytest.raises(ValidationError):
        use_case(name=" ", tag_type="method")


def test_create_tag_creates_new() -> None:
    tag_store = FakeTagStore()
    use_case = CreateTagUseCase(tag_store=tag_store)

    tag_id = use_case(name="methods", tag_type="method")

    assert tag_id in tag_store.tags_by_id
    assert tag_store.tags_by_id[tag_id]["name"] == "methods"


def test_create_tag_rejects_conflict() -> None:
    tag_store = FakeTagStore(tags_by_name={"methods": {"tag_id": "tag-1", "type": "subject"}})
    use_case = CreateTagUseCase(tag_store=tag_store)

    with pytest.raises(ConflictError):
        use_case(name="methods", tag_type="method")


def test_attach_tag_to_paper_idempotent() -> None:
    paper_store = FakePaperStore(papers={"paper-1"})
    tag_store = FakeTagStore(tags_by_id={"tag-1": {"tag_id": "tag-1", "type": "method"}})
    paper_tag_store = FakePaperTagStore(attached={("paper-1", "tag-1")})

    use_case = AttachTagToPaperUseCase(
        paper_store=paper_store,
        tag_store=tag_store,
        paper_tag_store=paper_tag_store,
    )

    use_case(paper_id="paper-1", tag_id="tag-1", confidence=0.9)

    assert ("paper-1", "tag-1") in paper_tag_store.attached


def test_attach_tag_to_paper_happy_path() -> None:
    paper_store = FakePaperStore(papers={"paper-1"})
    tag_store = FakeTagStore(tags_by_id={"tag-1": {"tag_id": "tag-1", "type": "method"}})
    paper_tag_store = FakePaperTagStore()

    use_case = AttachTagToPaperUseCase(
        paper_store=paper_store,
        tag_store=tag_store,
        paper_tag_store=paper_tag_store,
    )

    use_case(paper_id="paper-1", tag_id="tag-1", confidence=0.5)

    assert ("paper-1", "tag-1") in paper_tag_store.attached


def test_attach_tag_to_paper_requires_tag() -> None:
    paper_store = FakePaperStore(papers={"paper-1"})
    tag_store = FakeTagStore()
    paper_tag_store = FakePaperTagStore()

    use_case = AttachTagToPaperUseCase(
        paper_store=paper_store,
        tag_store=tag_store,
        paper_tag_store=paper_tag_store,
    )

    with pytest.raises(NotFoundError):
        use_case(paper_id="paper-1", tag_id="missing")


def test_attach_tag_to_paper_requires_paper() -> None:
    paper_store = FakePaperStore(papers=set())
    tag_store = FakeTagStore(tags_by_id={"tag-1": {"tag_id": "tag-1", "type": "method"}})
    paper_tag_store = FakePaperTagStore()

    use_case = AttachTagToPaperUseCase(
        paper_store=paper_store,
        tag_store=tag_store,
        paper_tag_store=paper_tag_store,
    )

    with pytest.raises(NotFoundError):
        use_case(paper_id="missing", tag_id="tag-1")


def test_create_project_is_idempotent_by_name() -> None:
    project_store = FakeProjectStore(
        projects_by_name={"Project": {"project_id": "proj-1", "description": None}}
    )
    use_case = CreateProjectUseCase(project_store=project_store)

    project_id = use_case(name="Project", description=None)

    assert project_id == "proj-1"


def test_create_project_requires_name() -> None:
    project_store = FakeProjectStore()
    use_case = CreateProjectUseCase(project_store=project_store)

    with pytest.raises(ValidationError):
        use_case(name=" ", description=None)


def test_create_project_creates_new() -> None:
    project_store = FakeProjectStore()
    use_case = CreateProjectUseCase(project_store=project_store)

    project_id = use_case(name="Project", description="Desc")

    assert project_id in project_store.projects_by_id
    assert project_store.projects_by_id[project_id]["description"] == "Desc"


def test_attach_paper_to_project_idempotent() -> None:
    paper_store = FakePaperStore(papers={"paper-1"})
    project_store = FakeProjectStore(projects_by_id={"proj-1": {"project_id": "proj-1"}})
    paper_project_store = FakePaperProjectStore(attached={("paper-1", "proj-1")})

    use_case = AttachPaperToProjectUseCase(
        paper_store=paper_store,
        project_store=project_store,
        paper_project_store=paper_project_store,
    )

    use_case(paper_id="paper-1", project_id="proj-1", label="seed")

    assert ("paper-1", "proj-1") in paper_project_store.attached


def test_attach_paper_to_project_happy_path() -> None:
    paper_store = FakePaperStore(papers={"paper-1"})
    project_store = FakeProjectStore(projects_by_id={"proj-1": {"project_id": "proj-1"}})
    paper_project_store = FakePaperProjectStore()

    use_case = AttachPaperToProjectUseCase(
        paper_store=paper_store,
        project_store=project_store,
        paper_project_store=paper_project_store,
    )

    use_case(paper_id="paper-1", project_id="proj-1", label="seed")

    assert ("paper-1", "proj-1") in paper_project_store.attached


def test_attach_paper_to_project_requires_project() -> None:
    paper_store = FakePaperStore(papers={"paper-1"})
    project_store = FakeProjectStore()
    paper_project_store = FakePaperProjectStore()

    use_case = AttachPaperToProjectUseCase(
        paper_store=paper_store,
        project_store=project_store,
        paper_project_store=paper_project_store,
    )

    with pytest.raises(NotFoundError):
        use_case(paper_id="paper-1", project_id="missing")


def test_attach_paper_to_project_requires_paper() -> None:
    paper_store = FakePaperStore(papers=set())
    project_store = FakeProjectStore(projects_by_id={"proj-1": {"project_id": "proj-1"}})
    paper_project_store = FakePaperProjectStore()

    use_case = AttachPaperToProjectUseCase(
        paper_store=paper_store,
        project_store=project_store,
        paper_project_store=paper_project_store,
    )

    with pytest.raises(NotFoundError):
        use_case(paper_id="missing", project_id="proj-1")
