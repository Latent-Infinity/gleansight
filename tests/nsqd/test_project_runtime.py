from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from nsqd.composition import build_container
from nsqd.domain.project import canonical_reviewed_projection_digest
from nsqd.null_adapters import HashParaphraseEmbedder
from nsqd.project_runtime import run_project
from nsqd.runner import run_job

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"
HASH_EMBEDDER = HashParaphraseEmbedder()


def _copy_project_fixture_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    fixture_dir = tmp_path / "approved-nsqd"
    fixture_dir.mkdir()
    for name in (
        "manifest.toml",
        "paper-a.yaml",
        "paper-a.md",
        "gamma-fragility.yaml",
        "gamma-fragility.md",
    ):
        shutil.copy(FIXTURES / name, fixture_dir / name)
    return fixture_dir / "manifest.toml", fixture_dir / "paper-a.yaml", fixture_dir / "paper-a.md"


def _load_projection(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


class _FakeProductionEmbedder:
    def model_id(self) -> str:
        return "qwen3-embedding"

    def model_version(self) -> str:
        return "latest"

    def dimension(self) -> int:
        return 2

    def normalization_policy(self) -> str:
        return "l2"

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0] if "Gamma" in text else [0.0, 1.0]


def test_run_project_loads_approved_fixture_through_shared_queue_runner(tmp_path: Path) -> None:
    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    db_path = tmp_path / "nsqd.sqlite"
    index_path = tmp_path / "corpus.lancedb"

    result = run_project(
        projection_path=projection_path,
        manifest_path=manifest_path,
        db_path=db_path,
        index_path=index_path,
        embedder=HASH_EMBEDDER,
        as_of=AS_OF,
    )

    assert result["status"] == "succeeded"
    assert result["created"] is True

    finance = run_project(
        projection_path=projection_path.parent / "gamma-fragility.yaml",
        manifest_path=manifest_path,
        db_path=db_path,
        index_path=index_path,
        embedder=HASH_EMBEDDER,
        as_of=AS_OF,
    )
    assert finance["status"] == "succeeded"
    assert finance["created"] is True

    container = build_container(db_path=db_path, index_path=index_path)
    stored = container.ctx.records.get(str(result["record_id"]))
    assert stored is not None
    assert stored["domain_policy_id"] == "optimization/1"
    finance_record = container.ctx.records.get(str(finance["record_id"]))
    assert finance_record is not None
    assert finance_record["domain_policy_id"] == "finance/1"
    assert finance_record["source"] == "doi:10.2139/ssrn.3725454"
    assert finance_record["coordinates"] == {
        "mechanism": "flow-driven",
        "target": "drawdown",
        "horizon": "intraday",
    }

    production = run_job(
        container,
        "acquire",
        {
            "snapshot_id": finance["snapshot_id"],
            "domain_policy_id": "finance/1",
            "target": "production_valid",
        },
        AS_OF,
    )
    assert production["state"] == "production_valid"
    assert production["failures"] == ()

    job_row = container.database.fetchone(
        "SELECT status, payload_json FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is not None
    assert job_row["status"] == "succeeded"
    payload_json = str(job_row["payload_json"])
    assert str(manifest_path) not in payload_json
    assert "reviewed_projection_digest" not in payload_json


def test_run_project_rejects_tampered_fixture_bytes(tmp_path: Path) -> None:
    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    projection_path.write_text(projection_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    db_path = tmp_path / "tampered.sqlite"
    index_path = tmp_path / "tampered-index"

    with pytest.raises(ValueError, match="content hash"):
        run_project(
            projection_path=projection_path,
            manifest_path=manifest_path,
            db_path=db_path,
            index_path=index_path,
            embedder=HASH_EMBEDDER,
            as_of=AS_OF,
        )

    container = build_container(db_path=db_path, index_path=index_path)
    job_row = container.database.fetchone(
        "SELECT status, last_error FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is None

    gamma_projection = projection_path.parent / "gamma-fragility.yaml"
    gamma_excerpt = projection_path.parent / "gamma-fragility.md"
    gamma_excerpt.write_text(gamma_excerpt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source markdown hash"):
        run_project(
            projection_path=gamma_projection,
            manifest_path=manifest_path,
            db_path=db_path,
            index_path=index_path,
            embedder=HASH_EMBEDDER,
            as_of=AS_OF,
        )

    shutil.copy(FIXTURES / "gamma-fragility.md", gamma_excerpt)
    original_projection = gamma_projection.read_text(encoding="utf-8")
    tampered_projection = original_projection.replace("We build on", "We alter", 1)
    gamma_projection.write_text(tampered_projection, encoding="utf-8")
    original_hash = hashlib.sha256(original_projection.encode("utf-8")).hexdigest()
    tampered_hash = hashlib.sha256(tampered_projection.encode("utf-8")).hexdigest()
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert original_hash in manifest_text
    manifest_path.write_text(
        manifest_text.replace(original_hash, tampered_hash, 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source abstract hash"):
        run_project(
            projection_path=gamma_projection,
            manifest_path=manifest_path,
            db_path=db_path,
            index_path=index_path,
            embedder=HASH_EMBEDDER,
            as_of=AS_OF,
        )


def test_run_project_rejects_missing_manifest_approval(tmp_path: Path) -> None:
    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    manifest_text = manifest_path.read_text(encoding="utf-8")
    marker = "[fixture.DATA-NSQD-04]"
    start = manifest_text.index(marker)
    manifest_text = manifest_text[:start].rstrip() + "\n"
    manifest_path.write_text(manifest_text, encoding="utf-8")
    db_path = tmp_path / "missing.sqlite"

    with pytest.raises(ValueError, match="not approved in manifest"):
        run_project(
            projection_path=projection_path,
            manifest_path=manifest_path,
            db_path=db_path,
            index_path=tmp_path / "missing-index",
            embedder=HASH_EMBEDDER,
            as_of=AS_OF,
        )

    container = build_container(db_path=db_path, index_path=tmp_path / "missing-index")
    job_row = container.database.fetchone(
        "SELECT status, last_error FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is None


def test_load_verified_projection_rejects_non_mapping_and_oversize(tmp_path: Path) -> None:
    from nsqd.project_runtime import load_verified_projection

    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    projection_path.write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_verified_projection(
            projection_path=projection_path,
            manifest_path=manifest_path,
        )

    huge = tmp_path / "huge.yaml"
    huge.write_bytes(b"x" * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="too large"):
        load_verified_projection(projection_path=huge, manifest_path=manifest_path)


def test_load_verified_projection_rejects_manifest_and_excerpt_integrity(
    tmp_path: Path,
) -> None:
    from nsqd.project_runtime import load_verified_projection

    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    original_manifest = manifest_path.read_text(encoding="utf-8")
    original_projection = projection_path.read_text(encoding="utf-8")

    manifest_path.write_text(
        original_manifest.replace("[fixture.", "[other."),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fixture table is required"):
        load_verified_projection(projection_path=projection_path, manifest_path=manifest_path)

    manifest_path.write_text(
        original_manifest.replace('id = "DATA-NSQD-04"', 'id = ""', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fixture id is required"):
        load_verified_projection(projection_path=projection_path, manifest_path=manifest_path)

    manifest_path.write_text(
        original_manifest.replace('id = "DATA-NSQD-04"', 'id = "other-id"', 1),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="key must match"):
        load_verified_projection(projection_path=projection_path, manifest_path=manifest_path)

    block = original_manifest[original_manifest.index("[fixture.DATA-NSQD-04]") :]
    duplicate = block.replace("[fixture.DATA-NSQD-04]", "[fixture.DATA-NSQD-04-dup]", 1).replace(
        'id = "DATA-NSQD-04"', 'id = "DATA-NSQD-04-dup"', 1
    )
    manifest_path.write_text(original_manifest + "\n" + duplicate, encoding="utf-8")
    with pytest.raises(ValueError, match="ambiguous"):
        load_verified_projection(projection_path=projection_path, manifest_path=manifest_path)

    escaped = original_manifest.replace(
        'excerpt_path = "paper-a.md"', 'excerpt_path = "../secret.md"', 1
    )
    projection_path.write_text(
        original_projection.replace(
            "source_excerpt_path: paper-a.md", "source_excerpt_path: ../secret.md"
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(escaped, encoding="utf-8")
    with pytest.raises(ValueError, match="escapes fixture directory|content hash"):
        load_verified_projection(projection_path=projection_path, manifest_path=manifest_path)


def test_project_job_payload_cannot_self_approve_through_shared_runner(tmp_path: Path) -> None:
    container = build_container(
        db_path=tmp_path / "self-approve.sqlite",
        index_path=tmp_path / "self-approve-index",
    )
    projection = _load_projection(FIXTURES / "paper-a.yaml")
    projection["reviewed_projection_digest"] = canonical_reviewed_projection_digest(projection)

    with pytest.raises(ValueError, match="approved reviewed projection"):
        run_job(
            container,
            "project",
            {
                "domain_policy_id": "optimization/1",
                "projection": projection,
            },
            AS_OF,
        )

    job_row = container.database.fetchone(
        "SELECT status, payload_json, last_error FROM nsqd_jobs WHERE type = 'project'"
    )
    assert job_row is not None
    assert job_row["status"] == "failed"
    assert "reviewed_projection_digest" in str(job_row["payload_json"])
    assert "approved reviewed projection" in str(job_row["last_error"])


def test_run_project_uses_injected_embedder_and_contract_scoped_index(tmp_path: Path) -> None:
    manifest_path, projection_path, _ = _copy_project_fixture_tree(tmp_path)
    embedder = _FakeProductionEmbedder()

    result = run_project(
        projection_path=projection_path.parent / "gamma-fragility.yaml",
        manifest_path=manifest_path,
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "corpus.lancedb",
        embedder=embedder,
        as_of=AS_OF,
    )

    assert result["status"] == "succeeded"
    qwen_container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "corpus.lancedb",
        embedder=embedder,
    )
    qwen_hits = qwen_container.ctx.index.query(
        str(result["snapshot_id"]),
        embedder.embed("Gamma fragility under dealer hedging."),
        k=5,
    )
    assert [hit.record_id for hit in qwen_hits] == [str(result["record_id"])]

    hermetic = HashParaphraseEmbedder()
    hermetic_container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "corpus.lancedb",
        embedder=hermetic,
    )
    assert (
        hermetic_container.ctx.index.query(
            str(result["snapshot_id"]),
            hermetic.embed("Gamma fragility under dealer hedging."),
            k=5,
        )
        == []
    )
