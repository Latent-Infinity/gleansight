from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from papers.domain.errors import ConfigurationError


class DataPaths(BaseModel):
    root: Path = Field(..., description="Base data directory")
    db_path: Path = Field(..., description="SQLite database path")
    blobs_dir: Path = Field(..., description="Root blobs directory")
    blobs_pdf_dir: Path = Field(..., description="PDF blob directory")
    blobs_md_dir: Path = Field(..., description="Markdown blob directory")
    blobs_analysis_dir: Path = Field(..., description="Analysis artifacts directory")
    lancedb_dir: Path = Field(..., description="LanceDB directory")

    @field_validator(
        "root",
        "db_path",
        "blobs_dir",
        "blobs_pdf_dir",
        "blobs_md_dir",
        "blobs_analysis_dir",
        "lancedb_dir",
        mode="before",
    )
    @classmethod
    def _ensure_path(cls, value: Any) -> Path:
        if value is None:
            raise ValueError("Path is required")
        return Path(value)


class EmbeddingSettings(BaseModel):
    model: str
    dimension: int
    text_slice_strategy: str


class LLMSettings(BaseModel):
    default_profile: str


class ScholarSettings(BaseModel):
    api_key: str = ""
    rate_limit_per_second: int = Field(default=10, ge=1, le=100)


class Settings(BaseModel):
    data: DataPaths
    embeddings: EmbeddingSettings
    llm: LLMSettings
    scholar: ScholarSettings


@dataclass(frozen=True)
class SettingsSource:
    defaults_path: Path
    override_path: Path | None


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"Missing config file: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_paths(config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    data = dict(config.get("data", {}))
    for key, value in data.items():
        path = Path(value)
        if not path.is_absolute():
            data[key] = (base_dir / path).resolve()
        else:
            data[key] = path
    config = dict(config)
    config["data"] = data
    return config


def load_settings(
    *,
    defaults_path: Path,
    override_path: Path | None = None,
    base_dir: Path | None = None,
) -> Settings:
    base_dir = base_dir or Path.cwd()
    defaults = _load_toml(defaults_path)
    combined = defaults
    if override_path:
        overrides = _load_toml(override_path)
        combined = _merge_dicts(defaults, overrides)
    combined = _resolve_paths(combined, base_dir)
    try:
        return Settings.model_validate(combined)
    except Exception as exc:  # pragma: no cover - pydantic error types vary by version
        raise ConfigurationError(str(exc)) from exc
