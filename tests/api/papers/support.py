from collections.abc import Mapping

from pydantic import JsonValue

from gleansight.api.papers import operations
from gleansight.api.runtime import ApiRuntime


def call(runtime: ApiRuntime, name: str, parameters: Mapping[str, JsonValue]) -> JsonValue:
    return next(item for item in operations() if item.name == f"papers.{name}").invoke(
        runtime, parameters
    )


def identifier(result: JsonValue, key: str) -> str:
    assert isinstance(result, dict)
    value = result[key]
    assert isinstance(value, str)
    return value


def prompt_version(runtime: ApiRuntime) -> tuple[str, str]:
    prompt_id = identifier(call(runtime, "prompts.create", {"name": "Methods"}), "prompt_id")
    version_id = identifier(
        call(
            runtime,
            "prompts.create-version",
            {"prompt_id": prompt_id, "body": "Analyze methods", "output_format": "markdown_only"},
        ),
        "prompt_version_id",
    )
    return prompt_id, version_id


def record(
    runtime: ApiRuntime, name: str, parameters: Mapping[str, JsonValue]
) -> dict[str, JsonValue]:
    result = call(runtime, name, parameters)
    assert isinstance(result, dict)
    return result


def items(
    runtime: ApiRuntime, name: str, parameters: Mapping[str, JsonValue]
) -> list[dict[str, JsonValue]]:
    from pydantic import TypeAdapter

    return TypeAdapter(list[dict[str, JsonValue]]).validate_python(
        record(runtime, name, parameters)["items"]
    )
