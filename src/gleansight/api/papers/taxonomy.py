from __future__ import annotations

from pydantic import JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation
from gleansight.api.papers.common import Page, ProjectId, Query, TagId, database, one, page
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.taxonomy import (
    AttachPaperToProjectUseCase,
    AttachTagToPaperUseCase,
    CreateProjectUseCase,
    CreateTagUseCase,
)
from papers.domain.models import TagType
from papers.infra.piccolo.stores import (
    PiccoloPaperProjectStore,
    PiccoloPaperStore,
    PiccoloPaperTagStore,
    PiccoloProjectStore,
    PiccoloTagStore,
)


class CreateProject(Request):
    name: Identifier
    description: str | None = None


class CreateTag(Request):
    name: Identifier
    tag_type: TagType


class AttachProject(ProjectId):
    paper_id: Identifier
    label: str | None = None


class AttachTag(TagId):
    paper_id: Identifier
    confidence: float | None = None


class ProjectMembers(Page):
    project_id: Identifier
    label: str | None = None


class TagMembers(Page):
    tag_id: Identifier


class PaperMemberships(Page):
    paper_id: Identifier


def create_project(runtime: ApiRuntime, request: CreateProject) -> JsonValue:
    database(runtime)
    return {
        "project_id": CreateProjectUseCase(PiccoloProjectStore())(
            name=request.name, description=request.description
        )
    }


def create_tag(runtime: ApiRuntime, request: CreateTag) -> JsonValue:
    database(runtime)
    return {
        "tag_id": CreateTagUseCase(PiccoloTagStore())(
            name=request.name, tag_type=request.tag_type.value
        )
    }


def attach_project(runtime: ApiRuntime, request: AttachProject) -> JsonValue:
    database(runtime)
    AttachPaperToProjectUseCase(
        PiccoloPaperStore(), PiccoloProjectStore(), PiccoloPaperProjectStore()
    )(paper_id=request.paper_id, project_id=request.project_id, label=request.label)
    return {"attached": True}


def attach_tag(runtime: ApiRuntime, request: AttachTag) -> JsonValue:
    database(runtime)
    AttachTagToPaperUseCase(PiccoloPaperStore(), PiccoloTagStore(), PiccoloPaperTagStore())(
        paper_id=request.paper_id, tag_id=request.tag_id, confidence=request.confidence
    )
    return {"attached": True}


def project_members(runtime: ApiRuntime, request: ProjectMembers) -> JsonValue:
    one(
        runtime,
        Query("SELECT project_id FROM projects WHERE project_id = ?", (request.project_id,)),
    )
    query = Query(
        "SELECT * FROM paper_projects WHERE project_id = ? ORDER BY paper_id", (request.project_id,)
    )
    if request.label is not None:
        query = Query(
            "SELECT * FROM paper_projects WHERE project_id = ? AND label = ? ORDER BY paper_id",
            (request.project_id, request.label),
        )
    return page(runtime, query, request)


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.projects.create",
            "Create a project, reusing its name.",
            CreateProject,
            create_project,
            ("write",),
        ),
        Operation(
            "papers.projects.list",
            "List projects with pagination.",
            Page,
            lambda r, q: page(r, Query("SELECT * FROM projects ORDER BY project_id"), q),
        ),
        Operation(
            "papers.projects.get",
            "Get a project.",
            ProjectId,
            lambda r, q: one(
                r, Query("SELECT * FROM projects WHERE project_id = ?", (q.project_id,))
            ),
        ),
        Operation(
            "papers.projects.attach",
            "Attach a paper to a project.",
            AttachProject,
            attach_project,
            ("write",),
        ),
        Operation(
            "papers.projects.members",
            "List project paper memberships.",
            ProjectMembers,
            project_members,
        ),
        Operation(
            "papers.projects.for-paper",
            "List a paper's project memberships.",
            PaperMemberships,
            lambda r, q: page(
                r,
                Query(
                    "SELECT * FROM paper_projects WHERE paper_id = ? ORDER BY project_id",
                    (q.paper_id,),
                ),
                q,
            ),
        ),
        Operation(
            "papers.tags.create",
            "Create a tag, reusing its name and type.",
            CreateTag,
            create_tag,
            ("write",),
        ),
        Operation(
            "papers.tags.list",
            "List tags with pagination.",
            Page,
            lambda r, q: page(r, Query("SELECT * FROM tags ORDER BY tag_id"), q),
        ),
        Operation(
            "papers.tags.get",
            "Get a tag.",
            TagId,
            lambda r, q: one(r, Query("SELECT * FROM tags WHERE tag_id = ?", (q.tag_id,))),
        ),
        Operation(
            "papers.tags.attach", "Attach a tag to a paper.", AttachTag, attach_tag, ("write",)
        ),
        Operation(
            "papers.tags.members",
            "List tagged paper memberships.",
            TagMembers,
            lambda r, q: page(
                r,
                Query("SELECT * FROM paper_tags WHERE tag_id = ? ORDER BY paper_id", (q.tag_id,)),
                q,
            ),
        ),
        Operation(
            "papers.tags.for-paper",
            "List a paper's tag memberships.",
            PaperMemberships,
            lambda r, q: page(
                r,
                Query("SELECT * FROM paper_tags WHERE paper_id = ? ORDER BY tag_id", (q.paper_id,)),
                q,
            ),
        ),
    )
