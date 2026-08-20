from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import yaml

from nsqd.domain.card import corpus_ingest_rejection

NSQD_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"
REQUIRED_OUTCOMES = (
    "snapshot_state",
    "snapshot_empty",
    "evidence",
    "nov",
    "mech",
    "fals",
    "dpred",
    "dval",
    "viability",
    "archive_eligible",
    "card_decision",
    "production_archive_empty",
)
ROLES = {
    "DATA-NSQD-01": "gamma-flow.yaml",
    "DATA-NSQD-02": "mechanism-free.yaml",
}


def test_smoke_requirement_cards_match_manifest_and_are_not_corpus() -> None:
    manifest = tomllib.loads((NSQD_DIR / "manifest.toml").read_text(encoding="utf-8"))
    fixtures = manifest["fixture"]
    for role, filename in ROLES.items():
        row = fixtures[role]
        assert row["kind"] == "candidate-requirement-card"
        assert row["never_corpus_record"] is True
        assert row["reviewer"] == "product"
        assert row["approval_revision"]
        assert str(row["approved_at"]).endswith("+00:00")
        path = NSQD_DIR / str(row["path"])
        assert path.name == filename
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["content_sha256"]
        payload = yaml.safe_load(raw.decode("utf-8"))
        assert payload["kind"] == "candidate-requirement-card"
        outcomes = payload["expected_outcomes"]
        for key in REQUIRED_OUTCOMES:
            assert key in outcomes
        assert outcomes["snapshot_state"] == "smoke_only"
        assert outcomes["evidence"] is None
        assert outcomes["viability"] == 0
        assert outcomes["archive_eligible"] is False
        assert corpus_ingest_rejection(payload) is not None


def test_pending_harvest_and_paper_fixtures_are_not_invented() -> None:
    manifest = (NSQD_DIR / "manifest.toml").read_text(encoding="utf-8")
    assert "DATA-NSQD-03" not in tomllib.loads(manifest)["fixture"]
    assert "DATA-NSQD-04" not in tomllib.loads(manifest)["fixture"]
    assert not (NSQD_DIR / "harvest-seed.toml").exists()
