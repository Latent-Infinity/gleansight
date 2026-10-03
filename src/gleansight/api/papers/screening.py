"""Public saved-discovery, attributed screening, import and scheduling operations."""

from pydantic import JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime
from papers.app.use_cases.saved_discovery import SavedDiscoveryService
from papers.app.use_cases.saved_discovery.actions import import_selection, schedule
from papers.domain.screening import ImportSelection, ReviewRequest, SaveSearch, ScheduleRequest
from papers.infra.scholar_s2.adapter import build_s2_client


class Save(SaveSearch, Request):
    pass


class SearchId(Request):
    search_id: Identifier


class Rerun(SearchId):
    run_id: Identifier | None = None


class ListSearches(Request):
    project_id: Identifier | None = None


class Review(ReviewRequest, Request):
    pass


class Import(ImportSelection, Request):
    pass


class Schedule(ScheduleRequest, Request):
    pass


def service(runtime: ApiRuntime, *, provider: bool = False) -> SavedDiscoveryService:
    client = None
    if provider:
        settings = runtime.settings.scholar
        client = build_s2_client(
            api_key=settings.api_key or None, rate_limit_per_second=settings.rate_limit_per_second
        )
    return SavedDiscoveryService(runtime.paper_database, client)


def save(runtime: ApiRuntime, request: Save) -> JsonValue:
    return json_result(service(runtime).save(request).model_dump(mode="json"))


def list_searches(runtime: ApiRuntime, request: ListSearches) -> JsonValue:
    return json_result(
        [item.model_dump(mode="json") for item in service(runtime).list(request.project_id)]
    )


def get(runtime: ApiRuntime, request: SearchId) -> JsonValue:
    return json_result(service(runtime).get(request.search_id).model_dump(mode="json"))


def rerun(runtime: ApiRuntime, request: Rerun) -> JsonValue:
    return json_result(
        service(runtime, provider=True)
        .rerun(request.search_id, request.run_id)
        .model_dump(mode="json")
    )


def review(runtime: ApiRuntime, request: Review) -> JsonValue:
    return json_result(service(runtime).review(request).model_dump(mode="json"))


def import_candidates(runtime: ApiRuntime, request: Import) -> JsonValue:
    return json_result(import_selection(service(runtime).store, request).model_dump(mode="json"))


def schedule_runs(runtime: ApiRuntime, request: Schedule) -> JsonValue:
    return json_result(schedule(service(runtime).store, request).model_dump(mode="json"))


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "papers.screening.save", "Save a project discovery query.", Save, save, ("write",)
        ),
        Operation(
            "papers.screening.list", "List persisted project searches.", ListSearches, list_searches
        ),
        Operation(
            "papers.screening.get",
            "Read query reruns and attributed screening history.",
            SearchId,
            get,
        ),
        Operation(
            "papers.screening.rerun",
            "Discover new, seen and changed candidates.",
            Rerun,
            rerun,
            ("write", "external"),
        ),
        Operation(
            "papers.screening.review",
            "Append an attributed include, exclude or maybe revision.",
            Review,
            review,
            ("write",),
        ),
        Operation(
            "papers.screening.import",
            "Import current inclusions with atomic project and tag attachment.",
            Import,
            import_candidates,
            ("write",),
        ),
        Operation(
            "papers.screening.schedule",
            "Queue bounded future discovery runs for the managed worker.",
            Schedule,
            schedule_runs,
            ("write",),
        ),
    )
