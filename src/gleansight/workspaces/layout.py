"""Resolve configured resources into a portable, secret-free restored layout."""

from pathlib import Path

from gleansight.api.runtime import ApiRuntime
from gleansight.workspaces.models import Resource, Workspace
from papers.domain.errors import ValidationError


def workspace_layout(runtime: ApiRuntime) -> Workspace:
    root = runtime.repo_root
    settings = runtime.settings

    def resource(path: Path, fallback: str) -> Resource:
        resolved = path.resolve()
        target = str(resolved.relative_to(root)) if resolved.is_relative_to(root) else fallback
        return Resource(source=resolved, target=target)

    data = settings.data
    db = resource(data.db_path, "data/db/app.sqlite")
    nsqd = resource(runtime.nsqd_db, "data/nsqd/nsqd.sqlite")
    blobs = tuple(
        resource(path, fallback)
        for path, fallback in (
            (data.blobs_dir, "data/blobs"),
            (data.blobs_pdf_dir, "data/blobs/pdf"),
            (data.blobs_md_dir, "data/blobs/md"),
            (data.blobs_analysis_dir, "data/blobs/analysis"),
        )
    )
    indexes = (
        resource(data.lancedb_dir, "data/lancedb"),
        resource(runtime.nsqd_index, "data/nsqd/corpus.lancedb"),
    )
    databases = tuple({item.source: item for item in (db, nsqd) if item.source.is_file()}.values())
    if not databases:
        raise ValidationError("No existing workspace databases were found.")
    paths = {"root": "data", "db_path": db.target, "lancedb_dir": indexes[0].target}
    paths.update(
        zip(
            ("blobs_dir", "blobs_pdf_dir", "blobs_md_dir", "blobs_analysis_dir"),
            (item.target for item in blobs),
            strict=True,
        )
    )
    return Workspace(
        root=root,
        databases=databases,
        blob_roots=blobs,
        indexes=indexes,
        data_paths=paths,
        nsqd_db=nsqd.target,
        nsqd_index=indexes[1].target,
        embedding_model=settings.embeddings.model,
        embedding_dimension=settings.embeddings.dimension,
        text_slice_strategy=settings.embeddings.text_slice_strategy,
    )
