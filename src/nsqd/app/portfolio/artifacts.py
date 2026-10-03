from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from nsqd.domain.acquisition_portfolio import PortfolioError
from nsqd.domain.contribution import ArtifactReference
from papers.domain.ideation_bundle import atomic_bundle, read_verified_text, write_manifest


def write_artifact(root: Path, workflow: str, value: BaseModel) -> ArtifactReference:
    with atomic_bundle(root, workflow) as (staging, published):
        content = value.model_dump_json(indent=2).encode()
        (staging / "report.json").write_bytes(content)
        write_manifest(staging, ("report.json",))
    return ArtifactReference(
        bundle_path=str(published.relative_to(root.resolve())),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def read_artifact[T: BaseModel](root: Path, path: Path, model: type[T]) -> T:
    requested = path if path.is_absolute() else root / path
    resolved = requested.resolve()
    if requested.is_symlink() or not resolved.is_relative_to((root / "output").resolve()):
        raise PortfolioError("Portfolio artifact must be inside workspace output")
    if {entry.name for entry in resolved.iterdir()} != {"report.json", "manifest.json"}:
        raise PortfolioError("Portfolio artifact set changed")
    hashes = TypeAdapter(dict[str, str]).validate_json(
        read_verified_text(resolved / "manifest.json")
    )
    if set(hashes) != {"report.json"}:
        raise PortfolioError("Portfolio manifest does not bind the report")
    return model.model_validate_json(
        read_verified_text(resolved / "report.json", hashes["report.json"])
    )
