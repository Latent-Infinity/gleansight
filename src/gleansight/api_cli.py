from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import JsonValue, TypeAdapter, ValidationError

from gleansight.api import ApiConfiguration, Failure, GleansightAPI, OperationError, Success
from gleansight.api.models import ErrorData, Result
from gleansight.api.operation import json_result
from papers.config.settings import DEFAULT_OLLAMA_BASE_URL

app = typer.Typer(add_completion=False, help="Schema-driven JSON API for automation.")
MAX_REQUEST_BYTES = 1024 * 1024


@app.callback()
def configure(
    ctx: typer.Context,
    repo_root: Annotated[Path, typer.Option("--repo-root")] = Path("."),
    config: Annotated[Path | None, typer.Option("--config")] = None,
    nsqd_db: Annotated[Path | None, typer.Option("--nsqd-db")] = None,
    nsqd_index: Annotated[Path | None, typer.Option("--nsqd-index")] = None,
    llm_base_url: Annotated[str, typer.Option("--llm-base-url")] = DEFAULT_OLLAMA_BASE_URL,
    allow_approvals: Annotated[
        bool,
        typer.Option("--allow-approvals", help="Enable explicitly human-authorized approvals."),
    ] = False,
) -> None:
    ctx.obj = GleansightAPI(
        ApiConfiguration(
            repo_root=repo_root,
            config_path=config,
            nsqd_db=nsqd_db,
            nsqd_index=nsqd_index,
            llm_base_url=llm_base_url,
            allow_approvals=allow_approvals,
        )
    )


def _client(ctx: typer.Context) -> GleansightAPI:
    if not isinstance(ctx.obj, GleansightAPI):
        raise RuntimeError("API context was not initialized")
    return ctx.obj


def _emit(result: Result) -> None:
    typer.echo(result.model_dump_json())
    if isinstance(result, Failure):
        code = 2 if result.error.code in {"invalid_request", "unknown_operation"} else 1
        raise typer.Exit(code=code)


def _failure(operation: str, code: str, message: str) -> Failure:
    return Failure(operation=operation, error=ErrorData(code=code, message=message))


@app.command("operations")
def list_operations(
    ctx: typer.Context,
    namespace: Annotated[str | None, typer.Option("--namespace")] = None,
    with_schemas: Annotated[bool, typer.Option("--with-schemas")] = False,
) -> None:
    descriptions = _client(ctx).operations(namespace=namespace)
    rows = [
        item.model_dump(mode="json", exclude=set() if with_schemas else {"input_schema"})
        for item in descriptions
    ]
    _emit(Success(operation="api.operations", data=json_result(rows)))


@app.command("describe")
def describe_operation(ctx: typer.Context, operation: str) -> None:
    try:
        description = _client(ctx).describe(operation)
    except OperationError as exc:
        _emit(_failure(operation, exc.code, str(exc)))
    else:
        _emit(Success(operation=operation, data=json_result(description.model_dump(mode="json"))))


def _parameters(input_json: str | None, input_file: Path | None) -> dict[str, JsonValue]:
    if input_json is not None and input_file is not None:
        raise ValueError("Choose either --input-json or --input-file.")
    if input_file is not None:
        if str(input_file) == "-":
            content = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        else:
            with input_file.open("rb") as stream:
                content = stream.read(MAX_REQUEST_BYTES + 1)
    else:
        content = (input_json if input_json is not None else "{}").encode("utf-8")
    if len(content) > MAX_REQUEST_BYTES:
        raise ValueError("API request exceeds the 1 MiB byte limit.")
    return TypeAdapter(dict[str, JsonValue]).validate_json(content, strict=True)


@app.command("call")
def call_operation(
    ctx: typer.Context,
    operation: str,
    input_json: Annotated[str | None, typer.Option("--input-json")] = None,
    input_file: Annotated[Path | None, typer.Option("--input-file")] = None,
) -> None:
    try:
        parameters = _parameters(input_json, input_file)
    except ValidationError:
        _emit(_failure(operation, "invalid_request", "Input must be a valid JSON object."))
    except (ValueError, UnicodeError) as exc:
        _emit(_failure(operation, "invalid_request", str(exc)))
    except OSError:
        _emit(_failure(operation, "io_error", "Unable to read the request file."))
    else:
        _emit(_client(ctx).call(operation, parameters))
