"""Explicitly selected verified research outputs; no experiment execution."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field, JsonValue

from gleansight.api.models import OperationError, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime
from papers.infra.piccolo.database import PiccoloDatabase
from research.catalog.models import Digest
from research.catalog.output import write_comparison
from research.catalog.store import CatalogStore


class BundleRequest(Request):
    bundle_path: Path


class ListRequest(Request):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class CompareRequest(Request):
    run_ids: tuple[Digest, ...] = Field(min_length=2, max_length=10)


def catalog(runtime: ApiRuntime) -> ResearchCatalog:
    try:
        from research.catalog.service import ResearchCatalog
    except ModuleNotFoundError as exc:
        if exc.name is not None and exc.name.partition(".")[0] in {"numpy", "torch"}:
            raise OperationError(
                "missing_dependency",
                "Research verification requires the optional research "
                "dependencies. Install them with: uv sync --group research",
            ) from exc
        raise
    database = PiccoloDatabase(runtime.settings.data.db_path, bind_on_init=False)
    return ResearchCatalog(CatalogStore(database), runtime.repo_root)


def verify(runtime: ApiRuntime, request: BundleRequest) -> JsonValue:
    return json_result(catalog(runtime).verify(request.bundle_path).model_dump(mode="json"))


def index(runtime: ApiRuntime, request: BundleRequest) -> JsonValue:
    return json_result(catalog(runtime).index(request.bundle_path).model_dump(mode="json"))


def list_runs(runtime: ApiRuntime, request: ListRequest) -> JsonValue:
    return json_result(
        {
            "runs": [
                item.model_dump(mode="json")
                for item in catalog(runtime).list(limit=request.limit, offset=request.offset)
            ]
        }
    )


def compare(runtime: ApiRuntime, request: CompareRequest) -> JsonValue:
    report = catalog(runtime).compare(request.run_ids)
    path = write_comparison(runtime.repo_root, report)
    return json_result(
        {
            "bundle_path": str(path.relative_to(runtime.repo_root)),
            "comparison": report.model_dump(mode="json"),
        }
    )


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "research.runs.verify",
            "Verify an explicitly selected owned research bundle.",
            BundleRequest,
            verify,
        ),
        Operation(
            "research.runs.index",
            "Verify and index an explicitly selected research bundle.",
            BundleRequest,
            index,
            ("write",),
        ),
        Operation(
            "research.runs.list",
            "Reverify indexed bundles and expose stale identities.",
            ListRequest,
            list_runs,
        ),
        Operation(
            "research.runs.compare",
            "Reverify runs and write a descriptive paired comparison without selecting a winner.",
            CompareRequest,
            compare,
            ("write",),
        ),
    )


if TYPE_CHECKING:
    from research.catalog.service import ResearchCatalog
