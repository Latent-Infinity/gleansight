"""Discover persisted local artifact references without rewriting their content."""

import json
import sqlite3
import tomllib
from pathlib import Path
from typing import assert_never

import yaml
from pydantic import JsonValue, TypeAdapter

from gleansight.workspaces.database import quote_identifier, tables


def path_key(key: str) -> bool:
    return (
        key
        in {"path", "output_blob_path_md", "output_blob_path_json", "plan_bundle", "handoff_bundle"}
        or key.endswith("_path")
    ) and key not in {
        "field_path",
        "json_path",
        "db_path",
        "index_path",
        "executable_path",
        "model_path",
    }


def json_paths(value: JsonValue) -> tuple[str, ...]:
    match value:
        case dict():
            paths: list[str] = []
            for key, child in value.items():
                match child:  # noqa: MATCH_OK - non-path values recurse through exhaustive json_paths
                    case str() if path_key(key) and child and "://" not in child:
                        paths.append(child)
                    case _:
                        paths.extend(json_paths(child))
            return tuple(paths)
        case list():
            return tuple(path for child in value for path in json_paths(child))
        case str() | int() | float() | bool() | None:
            return ()
        case unreachable:
            assert_never(unreachable)


def database_references(connection: sqlite3.Connection) -> tuple[str, ...]:
    paths: list[str] = []
    for table in tables(connection):
        columns = tuple(
            row[1] for row in connection.execute(f"PRAGMA table_info({quote_identifier(table)})")
        )
        for column in columns:
            if not (path_key(column) or column.endswith("_json")):
                continue
            condition = " AND status = 'queued'" if table in {"jobs", "nsqd_jobs"} else ""
            for (value,) in connection.execute(
                f"SELECT {quote_identifier(column)} FROM {quote_identifier(table)} "
                f"WHERE {quote_identifier(column)} IS NOT NULL" + condition
            ):
                text = TypeAdapter(str).validate_python(value)
                if not text:
                    continue
                if path_key(column):
                    paths.append(text)
                else:
                    paths.extend(json_paths(TypeAdapter(JsonValue).validate_json(text)))
    return tuple(paths)


def artifact_references(path: Path) -> tuple[str, ...]:
    match path.suffix.lower():  # noqa: MATCH_OK - arbitrary file extensions are permitted
        case ".json":
            value = TypeAdapter(JsonValue).validate_json(path.read_bytes())
        case ".yaml" | ".yml":
            value = TypeAdapter(JsonValue).validate_python(
                yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
            )
        case ".toml":
            value = TypeAdapter(JsonValue).validate_json(
                json.dumps(tomllib.loads(path.read_text(encoding="utf-8")), default=str)
            )
        case _:
            return ()
    return json_paths(value)
