from __future__ import annotations

import uuid
from dataclasses import dataclass

from papers.app import ports
from papers.domain.errors import ConflictError, NotFoundError, ValidationError


def _new_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class CreateTagUseCase:
    tag_store: ports.TagStore

    def __call__(self, *, name: str, tag_type: str) -> str:
        if not name.strip():
            raise ValidationError("tag name is required")
        existing = self.tag_store.get_by_name(name)
        if existing is not None:
            if existing.get("type") != tag_type:
                raise ConflictError("tag name already exists with a different type")
            return existing["tag_id"]
        tag_id = _new_id()
        self.tag_store.create_tag(tag_id, name, tag_type)
        return tag_id


@dataclass(frozen=True)
class AttachTagToPaperUseCase:
    paper_store: ports.PaperStore
    tag_store: ports.TagStore
    paper_tag_store: ports.PaperTagStore

    def __call__(self, *, paper_id: str, tag_id: str, confidence: float | None = None) -> None:
        if self.paper_store.get(paper_id) is None:
            raise NotFoundError("paper not found")
        if self.tag_store.get(tag_id) is None:
            raise NotFoundError("tag not found")
        if self.paper_tag_store.is_attached(paper_id, tag_id):
            return None
        self.paper_tag_store.attach(paper_id, tag_id, confidence)
        return None


@dataclass(frozen=True)
class CreateProjectUseCase:
    project_store: ports.ProjectStore

    def __call__(self, *, name: str, description: str | None = None) -> str:
        if not name.strip():
            raise ValidationError("project name is required")
        existing = self.project_store.get_by_name(name)
        if existing is not None:
            return existing["project_id"]
        project_id = _new_id()
        self.project_store.create_project(project_id, name, description)
        return project_id


@dataclass(frozen=True)
class AttachPaperToProjectUseCase:
    paper_store: ports.PaperStore
    project_store: ports.ProjectStore
    paper_project_store: ports.PaperProjectStore

    def __call__(self, *, paper_id: str, project_id: str, label: str | None = None) -> None:
        if self.paper_store.get(paper_id) is None:
            raise NotFoundError("paper not found")
        if self.project_store.get(project_id) is None:
            raise NotFoundError("project not found")
        if self.paper_project_store.is_attached(paper_id, project_id):
            return None
        self.paper_project_store.attach(paper_id, project_id, label)
        return None
