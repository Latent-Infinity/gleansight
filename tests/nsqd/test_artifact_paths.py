from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.trusted_files import read_verified_repo_file

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = REPO_ROOT / "evidence/archive/reviews/v1"
N11_ARCHIVE = ARCHIVE_ROOT / "nsqd-projection-review-2026-08-28/final"
N11_APPROVED = REPO_ROOT / "evidence/approved/nsqd/projections/n11/v1"
G_CONTRACT_ARCHIVE_V1 = (
    ARCHIVE_ROOT / "nsqd-operator-activation-2026-08-30/failure-record-contract.yaml"
)
G_CONTRACT_ARCHIVE_V2 = (
    ARCHIVE_ROOT
    / "nsqd-operator-g-failure-record-contract-2026-09-11-v2/failure-record-contract-v2.yaml"
)
G_CONTRACT_V1 = REPO_ROOT / "evidence/contracts/nsqd/operator-g/v1/failure-record-contract.yaml"
G_CONTRACT_V2 = REPO_ROOT / "evidence/contracts/nsqd/operator-g/v2/failure-record-contract-v2.yaml"


def test_resolve_artifact_path_maps_legacy_review_prefix(tmp_path: Path) -> None:
    logical_path = Path("docs/reviews/packet/manifest.json")

    resolved = resolve_artifact_path(tmp_path, logical_path)

    assert resolved == tmp_path / "evidence/archive/reviews/v1/packet/manifest.json"


def test_resolve_artifact_path_keeps_canonical_repo_relative_path(tmp_path: Path) -> None:
    logical_path = Path("evidence/approved/nsqd/projections/n11/v1/manifest.toml")

    resolved = resolve_artifact_path(tmp_path, logical_path)

    assert resolved == tmp_path / logical_path


@pytest.mark.parametrize(
    "logical_path",
    [Path("/docs/reviews/packet.json"), Path("docs/reviews/../secret.json")],
)
def test_resolve_artifact_path_rejects_unsafe_logical_path(
    tmp_path: Path, logical_path: Path
) -> None:
    with pytest.raises(ValueError, match="repo-relative without traversal"):
        resolve_artifact_path(tmp_path, logical_path)


def test_verified_read_reports_missing_legacy_artifact(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="artifact is missing"):
        read_verified_repo_file(
            repo_root=tmp_path,
            relative_path=Path("docs/reviews/missing.json"),
            expected_root=Path("docs/reviews"),
            field="artifact",
        )


def test_verified_read_ignores_resurrected_legacy_shadow(tmp_path: Path) -> None:
    archive = tmp_path / "evidence/archive/reviews/v1/packet"
    archive.mkdir(parents=True)
    (archive / "manifest.json").write_bytes(b"archived")
    legacy = tmp_path / "docs/reviews/packet"
    legacy.mkdir(parents=True)
    (legacy / "manifest.json").write_bytes(b"shadow")

    content = read_verified_repo_file(
        repo_root=tmp_path,
        relative_path=Path("docs/reviews/packet/manifest.json"),
        expected_root=Path("docs/reviews/packet"),
        field="artifact",
    )

    assert content == b"archived"


def test_review_archive_matches_frozen_v1_tree_identity() -> None:
    archive_entries = tuple(ARCHIVE_ROOT.rglob("*"))
    assert not (REPO_ROOT / "docs/reviews").exists()
    assert not any(path.is_symlink() for path in archive_entries)

    records: list[str] = []
    total_bytes = 0
    archive_files = (candidate for candidate in archive_entries if candidate.is_file())
    for path in sorted(archive_files, key=lambda candidate: candidate.as_posix()):
        content = path.read_bytes()
        total_bytes += len(content)
        records.append(
            f"{hashlib.sha256(content).hexdigest()}\t{len(content)}\t"
            f"{path.relative_to(ARCHIVE_ROOT)}\n"
        )

    assert len(records) == 370
    assert total_bytes == 28_822_465
    assert hashlib.sha256("".join(records).encode()).hexdigest() == (
        "66ab8846d5270861f1c37242697aa68997f04b17614ece238b8c116e6ef72041"
    )


def test_promoted_n11_bundle_is_byte_identical_to_approved_archive_source() -> None:
    archive_files = sorted(
        path.relative_to(N11_ARCHIVE) for path in N11_ARCHIVE.rglob("*") if path.is_file()
    )
    approved_files = sorted(
        path.relative_to(N11_APPROVED) for path in N11_APPROVED.rglob("*") if path.is_file()
    )

    assert approved_files == archive_files
    assert all(
        (N11_APPROVED / relative_path).read_bytes() == (N11_ARCHIVE / relative_path).read_bytes()
        for relative_path in archive_files
    )


@pytest.mark.parametrize(
    ("promoted", "archived"),
    [(G_CONTRACT_V1, G_CONTRACT_ARCHIVE_V1), (G_CONTRACT_V2, G_CONTRACT_ARCHIVE_V2)],
)
def test_promoted_operator_g_contract_is_byte_identical(promoted: Path, archived: Path) -> None:
    assert promoted.read_bytes() == archived.read_bytes()
