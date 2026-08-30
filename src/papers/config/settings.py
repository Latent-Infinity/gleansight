from __future__ import annotations

import math
import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from papers.domain.errors import ConfigurationError

_MISSING_DEPENDENCY_PREFIX = "Missing required dependency: "
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_QWEN_CHAT_MODEL = "qwen3.6:35b-a3b-q4_K_M"
DEFAULT_QWEN_EMBEDDING_MODEL = "qwen3-embedding:latest"
DEFAULT_QWEN_EMBEDDING_DIMENSION = 4096


def public_configuration_error_message(error: ConfigurationError) -> str:
    message = str(error)
    if message.startswith(_MISSING_DEPENDENCY_PREFIX):
        return f"Startup failed: {message}"
    return "Startup configuration failed"


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
    model: str = DEFAULT_QWEN_EMBEDDING_MODEL
    dimension: int = Field(default=DEFAULT_QWEN_EMBEDDING_DIMENSION, gt=0)
    text_slice_strategy: str
    base_url: str = DEFAULT_OLLAMA_BASE_URL

    @field_validator("model", "text_slice_strategy", "base_url", mode="before")
    @classmethod
    def _nonblank_string(cls, value: Any, info: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be blank")
        return text

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be a valid http or https URL")
        return value


class LLMSettings(BaseModel):
    default_profile: str
    default_model: str = DEFAULT_QWEN_CHAT_MODEL

    @field_validator("default_profile", "default_model", mode="before")
    @classmethod
    def _nonblank_string(cls, value: Any, info: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name} must be a string")
        text = value.strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be blank")
        return text


class ScholarSettings(BaseModel):
    api_key: str = ""
    rate_limit_per_second: int = Field(default=10, ge=1, le=100)
    require_open_access: bool = Field(
        default=True,
        description="Only return papers with open access PDFs (ArXiv, etc.)",
    )

    @field_validator("api_key", mode="before")
    @classmethod
    def _env_override_api_key(cls, value: Any) -> str:
        """Use env var SEMANTIC_SCHOLAR_API_KEY if set, otherwise use config value."""
        env_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")
        if env_key:
            return env_key
        return value if value else ""


class UISettings(BaseModel):
    search_max_results: int = Field(default=10, ge=1, le=100)


class PdfSettings(BaseModel):
    """Settings for PDF downloading."""

    unpaywall_email: str = ""
    download_rate_limit_per_second: float = Field(default=2.0, ge=0.1, le=10.0)
    download_max_retries: int = Field(default=3, ge=1, le=10)
    download_timeout_s: float = Field(default=120.0, ge=10.0, le=600.0)
    arxiv_export_rate_limit_per_second: float = Field(default=0.33, ge=0.01, le=2.0)
    arxiv_rate_limit_per_second: float = Field(default=0.067, ge=0.01, le=1.0)

    @field_validator("unpaywall_email", mode="before")
    @classmethod
    def _env_override_email(cls, value: Any) -> str:
        """Use env var UNPAYWALL_EMAIL if set, otherwise use config value."""
        env_email = os.environ.get("UNPAYWALL_EMAIL", "")
        if env_email:
            return env_email
        return value if value else ""


class NsqdSettings(BaseModel):
    enabled_operators: tuple[str, ...] = ("A",)
    novelty_threshold_tau: float = 0.45
    autonomous_tau: NsqdAutonomousTauSettings = Field(
        default_factory=lambda: NsqdAutonomousTauSettings()
    )

    @field_validator("enabled_operators", mode="before")
    @classmethod
    def _operator_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ("A",)
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
            raise ValueError("enabled_operators must be a list of operator ids")
        if any(not isinstance(item, str) for item in value):
            raise ValueError("enabled_operators must be a list of operator ids")
        items = tuple(item.strip() for item in value)
        if any(not item for item in items):
            raise ValueError("enabled_operators must be a list of operator ids")
        return items

    @field_validator("novelty_threshold_tau")
    @classmethod
    def _novelty_threshold_tau(cls, value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("tau must be a non-negative number or unset")
        normalized = float(value)
        if not math.isfinite(normalized) or normalized < 0:
            raise ValueError("tau must be a non-negative number or unset")
        return normalized


class NsqdAutonomousTauRouteSettings(BaseModel):
    agent_id: str
    provider: str
    model: str
    version: str
    profile: str
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    api_key: str = ""
    executable_path: str = ""
    reasoning_effort: str = ""

    @field_validator("agent_id", "provider", "profile", mode="before")
    @classmethod
    def _nonblank_string(cls, value: Any, info: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name} must be a string")
        text = value.strip()
        if not text:
            raise ValueError(f"{info.field_name} must not be blank")
        if info.field_name == "provider" and text not in {
            "ollama",
            "frontier",
            "codex_subscription",
        }:
            raise ValueError("provider must be ollama, frontier, or codex_subscription")
        return text

    @field_validator("model", "version", "executable_path", "reasoning_effort", mode="before")
    @classmethod
    def _optional_string(cls, value: Any, info: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name} must be a string")
        return value.strip()

    @field_validator("base_url", mode="before")
    @classmethod
    def _base_url_string(cls, value: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("base_url must be a string")
        return value.strip()

    @field_validator("api_key", mode="before")
    @classmethod
    def _api_key_string(cls, value: Any) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("api_key must be a string")
        return value.strip()

    @model_validator(mode="after")
    def _validate_route_fields(self) -> NsqdAutonomousTauRouteSettings:
        if self.provider != "codex_subscription":
            if not self.model:
                raise ValueError("model must not be blank")
            if not self.version:
                raise ValueError("version must not be blank")
        return self


class NsqdAutonomousTauAuditSettings(BaseModel):
    sample_rate: float = Field(default=0.10, ge=0.0, le=0.10)
    policy_revision: str = "tau-audit/1"

    @field_validator("policy_revision", mode="before")
    @classmethod
    def _audit_revision(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("policy_revision must be a string")
        text = value.strip()
        if not text:
            raise ValueError("policy_revision must not be blank")
        return text


class NsqdAutonomousTauSettings(BaseModel):
    rounds: int = Field(default=4, ge=4, le=4)
    timeout_s: int = Field(default=300, ge=1, le=300)
    seed: int = Field(default=17, ge=0)
    writer: NsqdAutonomousTauRouteSettings = Field(
        default_factory=lambda: NsqdAutonomousTauRouteSettings(
            agent_id="tau-writer-local-v1",
            provider="ollama",
            model=DEFAULT_QWEN_CHAT_MODEL,
            version="2026-08-24",
            profile="tau-writer-local",
            base_url=DEFAULT_OLLAMA_BASE_URL,
            api_key="",
            executable_path="",
            reasoning_effort="",
        )
    )
    reviewer: NsqdAutonomousTauRouteSettings = Field(
        default_factory=lambda: NsqdAutonomousTauRouteSettings(
            agent_id="tau-reviewer-local-v1",
            provider="ollama",
            model=DEFAULT_QWEN_CHAT_MODEL,
            version="2026-08-24",
            profile="tau-reviewer-local",
            base_url=DEFAULT_OLLAMA_BASE_URL,
            api_key="",
            executable_path="",
            reasoning_effort="",
        )
    )
    adjudicator: NsqdAutonomousTauRouteSettings = Field(
        default_factory=lambda: NsqdAutonomousTauRouteSettings(
            agent_id="tau-adjudicator-frontier-v1",
            provider="codex_subscription",
            model="gpt-5.6-terra",
            version="config-2026-08-29",
            profile="tau-adjudicator-frontier",
            base_url="",
            api_key="",
            executable_path="codex",
            reasoning_effort="high",
        )
    )
    audit: NsqdAutonomousTauAuditSettings = Field(default_factory=NsqdAutonomousTauAuditSettings)

    @model_validator(mode="after")
    def _validate_identities(self) -> NsqdAutonomousTauSettings:
        if self.writer.agent_id == self.reviewer.agent_id:
            raise ValueError("writer and reviewer agent_id values must differ")
        if self.writer.profile == self.reviewer.profile:
            raise ValueError("writer and reviewer profile values must differ")
        adjudicator_ids = {self.writer.agent_id, self.reviewer.agent_id}
        if self.adjudicator.agent_id in adjudicator_ids:
            raise ValueError("adjudicator agent_id must differ from writer and reviewer")
        adjudicator_profiles = {self.writer.profile, self.reviewer.profile}
        if self.adjudicator.profile in adjudicator_profiles:
            raise ValueError("adjudicator profile must differ from writer and reviewer")
        return self


class Settings(BaseModel):
    data: DataPaths
    embeddings: EmbeddingSettings
    llm: LLMSettings
    scholar: ScholarSettings
    ui: UISettings
    pdf: PdfSettings = Field(default_factory=PdfSettings)
    nsqd: NsqdSettings = Field(default_factory=NsqdSettings)


@dataclass(frozen=True)
class SettingsSource:
    defaults_path: Path
    override_path: Path | None


def packaged_defaults_path() -> Path:
    return Path(__file__).resolve().parent / "defaults.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"Missing config file: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as exc:
        raise ConfigurationError(f"Unable to read .env file: {path}") from exc


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
    _load_dotenv(base_dir / ".env")
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
