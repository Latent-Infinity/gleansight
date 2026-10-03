"""Bounded artifact reads with stored run, prompt, and schema identity checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from papers.domain.analysis_comparison import ArtifactView

MAX_ARTIFACT_BYTES: Final = 2 * 1024 * 1024
JSON_VALUE: Final = TypeAdapter(JsonValue)


class RunRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    run_id: str
    paper_id: str
    prompt_version_id: str
    profile_id: str
    model_name: str
    status: str | None = None
    error_message: str | None = None
    validation_issues_json: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    extraction_schema_json: str | None = None
    output_blob_path_md: str | None = None
    output_blob_path_json: str | None = None
    md_fingerprint_xxh64: str | None = None


class PromptMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    prompt_version_id: str
    extraction_schema_hash: str | None = None


class InputMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    md_fingerprint_xxh64: str | None = None


class ArtifactMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    run_id: str
    paper_id: str
    prompt: PromptMetadata
    input_provenance: InputMetadata | None = None


def bounded_text(path: Path) -> str:
    """Refuse non-files and oversize bytes without an unbounded read."""
    if path.is_symlink() or not path.is_file():
        message = f"Artifact is missing or is not a regular file: {path}"
        raise ValueError(message)
    with path.open("rb") as handle:
        raw = handle.read(MAX_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_ARTIFACT_BYTES:
        message = f"Artifact exceeds {MAX_ARTIFACT_BYTES} byte inspection limit: {path}"
        raise ValueError(message)
    return raw.decode("utf-8")


def inspect_artifact(row: RunRow, path_text: str | None) -> ArtifactView:
    """Expose read failures instead of replacing missing output with an empty string."""
    if not path_text:
        return ArtifactView(path=None, state="absent", error="No output artifact was recorded.")
    path = Path(path_text)
    try:
        if path.parent.name != row.run_id or path.name not in {"output.md", "output.json"}:
            message = "Stored artifact path does not match the run identity."
            raise ValueError(message)
        meta = ArtifactMetadata.model_validate_json(bounded_text(path.parent / "meta.json"))
        if (meta.run_id, meta.paper_id, meta.prompt.prompt_version_id) != (
            row.run_id,
            row.paper_id,
            row.prompt_version_id,
        ):
            message = "Artifact metadata identity does not match the stored run."
            raise ValueError(message)
        expected_schema = (
            hashlib.sha256(row.extraction_schema_json.encode()).hexdigest()
            if row.extraction_schema_json is not None
            else None
        )
        if meta.prompt.extraction_schema_hash != expected_schema:
            message = "Extraction schema has changed since the output was recorded."
            raise ValueError(message)
        provenance = meta.input_provenance
        if (
            provenance is not None
            and row.md_fingerprint_xxh64 is not None
            and provenance.md_fingerprint_xxh64 != row.md_fingerprint_xxh64
        ):
            message = "Source paper Markdown has changed since this analysis."
            raise ValueError(message)
        text = bounded_text(path)
        if path.suffix == ".json" and text:
            JSON_VALUE.validate_json(text)
        return ArtifactView(
            path=path_text,
            state="available" if text else "empty",
            text=text,
            sha256=hashlib.sha256(text.encode()).hexdigest(),
        )
    except (OSError, ValueError) as exc:
        return ArtifactView(path=path_text, state="unavailable", error=str(exc))


class RecordedUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None


class RecordedPricing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    input_price_per_1k_tokens: float | None = None
    output_price_per_1k_tokens: float | None = None


class RecordedEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    pricing: RecordedPricing | None = None


class CostMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    usage: RecordedUsage | None = None
    endpoint: RecordedEndpoint | None = None


def recorded_cost(row: RunRow) -> float | None:
    """Only display a recorded amount backed by recorded pricing and provider usage."""
    if row.cost_usd is None or not row.output_blob_path_md:
        return None
    try:
        meta = CostMetadata.model_validate_json(
            bounded_text(Path(row.output_blob_path_md).parent / "meta.json")
        )
    except (OSError, ValueError):
        return None
    usage = meta.usage
    pricing = meta.endpoint.pricing if meta.endpoint is not None else None
    if usage is None or pricing is None:
        return None
    if (
        usage.tokens_in is None
        or usage.tokens_out is None
        or pricing.input_price_per_1k_tokens is None
        or pricing.output_price_per_1k_tokens is None
        or usage.cost_usd != row.cost_usd
        or (usage.tokens_in, usage.tokens_out) != (row.tokens_in, row.tokens_out)
    ):
        return None
    return row.cost_usd
