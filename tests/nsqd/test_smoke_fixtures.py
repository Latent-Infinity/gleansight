from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path

import yaml

from nsqd.domain.card import corpus_ingest_rejection

APPROVED_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "approved"
NSQD_DIR = APPROVED_DIR / "nsqd"
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


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _fixture_path(base: Path, relative_path: object) -> Path:
    resolved_base = base.resolve()
    resolved_path = (resolved_base / str(relative_path)).resolve()
    assert resolved_path.is_relative_to(resolved_base)
    return resolved_path


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.casefold())


def _max_contiguous_overlap(left: str, right: str) -> int:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    previous = [0] * (len(right_tokens) + 1)
    best = 0
    for left_token in left_tokens:
        current = [0] * (len(right_tokens) + 1)
        for index, right_token in enumerate(right_tokens, start=1):
            if left_token == right_token:
                current[index] = previous[index - 1] + 1
                best = max(best, current[index])
        previous = current
    return best


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
        assert _sha256(raw) == row["content_sha256"]
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


def test_approved_paper_paraphrase_matches_source_and_review_contract() -> None:
    nsqd_manifest = tomllib.loads((NSQD_DIR / "manifest.toml").read_text(encoding="utf-8"))
    source_manifest = tomllib.loads((APPROVED_DIR / "manifest.toml").read_text(encoding="utf-8"))
    row = nsqd_manifest["fixture"]["DATA-NSQD-04"]
    source = source_manifest["fixture"]["DATA-01c"]

    sidecar_path = _fixture_path(NSQD_DIR, row["path"])
    excerpt_path = _fixture_path(NSQD_DIR, row["excerpt_path"])
    source_markdown_path = _fixture_path(APPROVED_DIR, source["markdown_path"])
    sidecar_raw = sidecar_path.read_bytes()
    excerpt_raw = excerpt_path.read_bytes()
    payload = yaml.safe_load(sidecar_raw.decode("utf-8"))

    assert _sha256(sidecar_raw) == row["content_sha256"]
    assert _sha256(excerpt_raw) == row["excerpt_sha256"]
    assert excerpt_raw == source_markdown_path.read_bytes()
    assert payload["source_excerpt_path"] == row["excerpt_path"]
    assert payload["kind"] == row["kind"] == "corpus-paper-paraphrase"
    assert payload["id"] == row["id"] == "DATA-NSQD-04"
    assert payload["source_fixture_id"] == row["source_fixture_id"] == source["id"]
    assert payload["domain_policy_id"] == row["domain_policy_id"] == "optimization/1"
    assert payload["paper_id"] == row["paper_id"] == source["paper_id"] == "paper-20"
    assert payload["source_paper_id"] == row["source_paper_id"] == source["source_paper_id"]
    assert payload["title"] == row["title"] == source["title"]
    assert payload["source_abstract_sha256"] == _sha256(source["abstract"].encode("utf-8"))
    assert payload["source_markdown_sha256"] == _sha256(excerpt_raw)
    assert payload["source_abstract_sha256"] == row["source_abstract_sha256"]
    assert payload["source_markdown_sha256"] == row["source_markdown_sha256"]

    paraphrase = payload["paraphrase"].strip()
    assert paraphrase != source["abstract"].strip()
    assert payload["paraphrase_sha256"] == _sha256(paraphrase.encode("utf-8"))
    assert payload["paraphrase_sha256"] == row["paraphrase_sha256"]
    assert payload["paraphrase_source"] == row["paraphrase_source"] == "model_assisted"
    assert payload["review_status"] == row["review_status"] == "approved"
    assert payload["review_workflow"] == row["review_workflow"] == "writer-reviewer/1"
    assert payload["review_rounds"] == row["review_rounds"] == 4
    assert payload["human_reviewer"] == row["reviewer"] == "product"
    assert payload["human_approved_at"] == row["approved_at"]
    assert str(row["approved_at"]).endswith("+00:00")

    source_text = f"{source['abstract']}\n{excerpt_raw.decode('utf-8')}"
    overlap = _max_contiguous_overlap(paraphrase, source_text)
    assert overlap == payload["overlap_check"]["max_contiguous_source_tokens"] == 7
    assert overlap < payload["overlap_check"]["limit"] == 8
    assert overlap == row["overlap_max"]
    assert payload["overlap_check"]["limit"] == row["overlap_limit"]


def test_approved_finance_projection_matches_source_and_review_contract() -> None:
    nsqd_manifest = tomllib.loads((NSQD_DIR / "manifest.toml").read_text(encoding="utf-8"))
    source_manifest = tomllib.loads((APPROVED_DIR / "manifest.toml").read_text(encoding="utf-8"))
    row = nsqd_manifest["fixture"]["DATA-NSQD-03"]
    source = source_manifest["fixture"]["DATA-01d"]

    sidecar_path = _fixture_path(NSQD_DIR, row["path"])
    excerpt_path = _fixture_path(NSQD_DIR, row["excerpt_path"])
    source_markdown_path = _fixture_path(APPROVED_DIR, source["markdown_path"])
    sidecar_raw = sidecar_path.read_bytes()
    excerpt_raw = excerpt_path.read_bytes()
    payload = yaml.safe_load(sidecar_raw.decode("utf-8"))

    assert _sha256(sidecar_raw) == row["content_sha256"]
    assert _sha256(excerpt_raw) == row["excerpt_sha256"]
    assert excerpt_raw == source_markdown_path.read_bytes()
    assert payload["source_excerpt_path"] == row["excerpt_path"]
    assert payload["kind"] == row["kind"] == "corpus-paper-paraphrase"
    assert payload["id"] == row["id"] == "DATA-NSQD-03"
    assert payload["source_fixture_id"] == row["source_fixture_id"] == source["id"]
    assert payload["domain_policy_id"] == row["domain_policy_id"] == "finance/1"
    assert payload["paper_id"] == row["paper_id"] == source["paper_id"] == "paper-40"
    assert payload["source_paper_id"] == row["source_paper_id"] == source["source_paper_id"]
    assert payload["title"] == row["title"] == source["title"] == "Gamma Fragility"
    assert payload["source"] == "doi:10.2139/ssrn.3725454"
    assert payload["coordinates"] == {
        "mechanism": "flow-driven",
        "target": "drawdown",
        "horizon": "intraday",
    }
    assert payload["source_abstract_sha256"] == _sha256(source["abstract"].encode("utf-8"))
    assert payload["source_markdown_sha256"] == _sha256(excerpt_raw)
    assert payload["source_abstract_sha256"] == row["source_abstract_sha256"]
    assert payload["source_markdown_sha256"] == row["source_markdown_sha256"]

    paraphrase = payload["paraphrase"].strip()
    assert paraphrase != source["abstract"].strip()
    assert payload["paraphrase_sha256"] == _sha256(paraphrase.encode("utf-8"))
    assert payload["paraphrase_sha256"] == row["paraphrase_sha256"]
    assert payload["paraphrase_source"] == row["paraphrase_source"] == "model_assisted"
    assert payload["review_status"] == row["review_status"] == "approved"
    assert payload["review_workflow"] == row["review_workflow"] == "writer-reviewer/1"
    assert payload["review_rounds"] == row["review_rounds"] == 4
    assert payload["human_reviewer"] == row["reviewer"] == "product"
    assert payload["human_approved_at"] == row["approved_at"]
    assert str(row["approved_at"]).endswith("+00:00")

    source_text = f"{source['abstract']}\n{excerpt_raw.decode('utf-8')}"
    overlap = _max_contiguous_overlap(paraphrase, source_text)
    assert overlap == payload["overlap_check"]["max_contiguous_source_tokens"]
    assert overlap < payload["overlap_check"]["limit"] == 8
    assert overlap == row["overlap_max"]
    assert payload["overlap_check"]["limit"] == row["overlap_limit"]
    assert not (NSQD_DIR / "harvest-seed.toml").exists()
