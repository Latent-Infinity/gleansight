from __future__ import annotations

from pydantic import JsonValue, TypeAdapter

from gleansight.api.models import Identifier, OperationError, Request
from gleansight.api.operation import Operation, RegisteredOperation
from gleansight.api.papers.common import Page, Query, database, one, page
from gleansight.api.runtime import ApiRuntime
from papers.infra.piccolo.stores import PiccoloProfileStore


class ProfileId(Request):
    profile_id: Identifier


def llm_profile(runtime: ApiRuntime, profile_id: str | None) -> dict[str, JsonValue]:
    database(runtime)
    profile = PiccoloProfileStore().get(profile_id or runtime.settings.llm.default_profile)
    if profile is None:
        raise OperationError("not_found", "LLM profile does not exist.")
    keys = {
        "api_key",
        "base_url",
        "chat_options",
        "executable_path",
        "profile_id",
        "provider",
        "reasoning_effort",
    }
    return TypeAdapter(dict[str, JsonValue]).validate_python(
        {key: value for key, value in profile.items() if key in keys}
    )


def operations() -> tuple[RegisteredOperation, ...]:
    fields = "profile_id, name, default_model, is_active, created_at, updated_at"
    return (
        Operation(
            "papers.profiles.list",
            "List configured profile metadata without credentials or endpoint URLs.",
            Page,
            lambda r, q: page(
                r, Query(f"SELECT {fields} FROM endpoint_profiles ORDER BY profile_id"), q
            ),
        ),
        Operation(
            "papers.profiles.get",
            "Read configured profile metadata without credentials or endpoint URLs.",
            ProfileId,
            lambda r, q: one(
                r,
                Query(
                    f"SELECT {fields} FROM endpoint_profiles WHERE profile_id = ?", (q.profile_id,)
                ),
            ),
        ),
    )
