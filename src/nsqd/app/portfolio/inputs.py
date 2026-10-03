from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from pydantic import JsonValue, TypeAdapter

from nsqd.domain.acquisition_portfolio import PortfolioError, digest_json
from nsqd.domain.contribution import FrozenProjectionInput
from nsqd.project_runtime import MAX_PROJECT_FILE_BYTES, load_verified_projection


def freeze_input(projection: Path, manifest: Path) -> FrozenProjectionInput:
    projection, manifest = projection.resolve(), manifest.resolve()
    common = Path(os.path.commonpath((projection.parent, manifest.parent)))
    files: dict[str, str] = {}
    for path in (projection, manifest):
        if path.is_file():
            files[str(path.relative_to(common))] = _bounded_text(path)
    if projection.is_file():
        try:
            loaded = yaml.safe_load(files[str(projection.relative_to(common))])
        except yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            excerpt_name = loaded.get("source_excerpt_path")
            if isinstance(excerpt_name, str):
                excerpt = (projection.parent / excerpt_name).resolve()
                if excerpt.is_relative_to(projection.parent) and excerpt.is_file():
                    files[str(excerpt.relative_to(common))] = _bounded_text(excerpt)
    identity: dict[str, JsonValue] = {
        "projection_path": str(projection.relative_to(common)),
        "manifest_path": str(manifest.relative_to(common)),
        "files": {key: value for key, value in files.items()},
    }
    return FrozenProjectionInput.model_validate({**identity, "sha256": digest_json(identity)})


def _bounded_text(path: Path) -> str:
    with path.open("rb") as stream:
        content = stream.read(MAX_PROJECT_FILE_BYTES + 1)
    if len(content) > MAX_PROJECT_FILE_BYTES:
        raise PortfolioError("Projection input exceeds the existing 256 KiB limit")
    return content.decode("utf-8")


def verified_input(value: FrozenProjectionInput) -> dict[str, JsonValue]:
    identity = value.model_dump(mode="json", exclude={"sha256"})
    if digest_json(identity) != value.sha256:
        raise PortfolioError("Frozen projection input digest changed")
    with TemporaryDirectory(prefix="gleansight-portfolio-input-") as directory:
        root = Path(directory)
        for name in (*value.files, value.projection_path, value.manifest_path):
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise PortfolioError("Frozen input path escapes its replay directory")
        for name, text in value.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        try:
            return TypeAdapter(dict[str, JsonValue]).validate_python(
                load_verified_projection(
                    projection_path=root / value.projection_path,
                    manifest_path=root / value.manifest_path,
                )
            )
        except OSError as exc:
            name = Path(exc.filename).name if exc.filename else type(exc).__name__
            raise PortfolioError(f"Frozen input unavailable: {name}") from exc
