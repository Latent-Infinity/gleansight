from __future__ import annotations

import hashlib
import json

import pytest

from nsqd.domain.project import canonical_reviewed_projection_digest, projection_record_id
from tests.nsqd.status_window_receipt_replay_support import _load_replay_module


def test_approved_projection_rows_use_exact_projection_record_identity(monkeypatch) -> None:
    replay = _load_replay_module()

    finance_manifest = {
        "fixture": {
            "ROW-1": {
                "id": "ROW-1",
                "kind": "corpus-paper-paraphrase",
                "path": "row-1.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": "c1",
                "reviewed_projection_sha256": "d1",
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
            "ROW-2": {
                "id": "ROW-2",
                "kind": "corpus-paper-paraphrase",
                "path": "row-2.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": "c2",
                "reviewed_projection_sha256": "d2",
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
        }
    }

    payloads = {
        "row-1.yaml": {
            "id": "ROW-1",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-1",
            "source_markdown_sha256": "md-1",
            "paraphrase_sha256": "para-1",
            "paraphrase": "one",
            "paraphrase_source": "model_assisted",
            "source": "doi:one",
            "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
        "row-2.yaml": {
            "id": "ROW-2",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-2",
            "source_markdown_sha256": "md-2",
            "paraphrase_sha256": "para-2",
            "paraphrase": "two",
            "paraphrase_source": "model_assisted",
            "source": "doi:two",
            "coordinates": {
                "mechanism": "flow-driven",
                "target": "drawdown",
                "horizon": "intraday",
            },
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
    }

    finance_manifest["fixture"]["ROW-1"]["content_sha256"] = hashlib.sha256(
        json.dumps(payloads["row-1.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    finance_manifest["fixture"]["ROW-1"]["reviewed_projection_sha256"] = (
        canonical_reviewed_projection_digest(payloads["row-1.yaml"])
    )
    finance_manifest["fixture"]["ROW-2"]["content_sha256"] = hashlib.sha256(
        json.dumps(payloads["row-2.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    finance_manifest["fixture"]["ROW-2"]["reviewed_projection_sha256"] = (
        canonical_reviewed_projection_digest(payloads["row-2.yaml"])
    )

    def fake_read_verified_repo_text(**kwargs):
        rel = kwargs["relative_path"].as_posix()
        if rel.endswith("final/manifest.toml") or rel.endswith("approved/nsqd/manifest.toml"):
            return "unused-manifest"
        raise AssertionError(rel)

    seen = 0

    def fake_tomllib_loads(_text: str):
        nonlocal seen
        seen += 1
        return finance_manifest if seen == 1 else {"fixture": {}}

    def fake_load_verified_yaml_mapping(**kwargs):
        rel = kwargs["relative_path"].name
        return dict(payloads[rel])

    def fake_read_verified_repo_file(**kwargs):
        rel = kwargs["relative_path"].name
        return json.dumps(payloads[rel], sort_keys=True).encode("utf-8")

    monkeypatch.setattr(replay, "read_verified_repo_text", fake_read_verified_repo_text)
    monkeypatch.setattr(replay.tomllib, "loads", fake_tomllib_loads)
    monkeypatch.setattr(replay, "load_verified_yaml_mapping", fake_load_verified_yaml_mapping)
    monkeypatch.setattr(
        replay, "read_verified_repo_file", fake_read_verified_repo_file, raising=False
    )

    rows = replay._approved_projection_rows()
    first_id = projection_record_id(payloads["row-1.yaml"])
    second_id = projection_record_id(payloads["row-2.yaml"])
    assert set(rows) == {first_id, second_id}
    assert rows[first_id]["coordinates"] != rows[second_id]["coordinates"]


def test_approved_projection_rows_reject_duplicate_projected_record_ids(monkeypatch) -> None:
    replay = _load_replay_module()
    payloads = {
        "row-1.yaml": {
            "id": "ROW-1",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-1",
            "source_markdown_sha256": "md-1",
            "paraphrase_sha256": "para-1",
            "paraphrase": "one",
            "paraphrase_source": "model_assisted",
            "source": "doi:one",
            "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
        "row-2.yaml": {
            "id": "ROW-2",
            "source_paper_id": "shared-paper",
            "domain_policy_id": "finance/1",
            "source_abstract_sha256": "abs-1",
            "source_markdown_sha256": "md-1",
            "paraphrase_sha256": "para-1",
            "paraphrase": "one",
            "paraphrase_source": "model_assisted",
            "source": "doi:one",
            "coordinates": {"mechanism": "behavioral", "target": "returns", "horizon": "daily"},
            "human_reviewer": "product",
            "human_approved_at": "2026-09-03T00:00:00+00:00",
            "review_status": "approved",
            "type": "paper",
        },
    }
    digest = canonical_reviewed_projection_digest(payloads["row-1.yaml"])
    content_sha_row_1 = hashlib.sha256(
        json.dumps(payloads["row-1.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    content_sha_row_2 = hashlib.sha256(
        json.dumps(payloads["row-2.yaml"], sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest = {
        "fixture": {
            "ROW-1": {
                "id": "ROW-1",
                "kind": "corpus-paper-paraphrase",
                "path": "row-1.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": content_sha_row_1,
                "reviewed_projection_sha256": digest,
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
            "ROW-2": {
                "id": "ROW-2",
                "kind": "corpus-paper-paraphrase",
                "path": "row-2.yaml",
                "domain_policy_id": "finance/1",
                "source_paper_id": "shared-paper",
                "content_sha256": content_sha_row_2,
                "reviewed_projection_sha256": digest,
                "review_status": "approved",
                "reviewer": "product",
                "approved_at": "2026-09-03T00:00:00+00:00",
            },
        }
    }
    seen = 0

    monkeypatch.setattr(replay, "read_verified_repo_text", lambda **kwargs: "unused-manifest")

    def fake_tomllib_loads(_text: str):
        nonlocal seen
        seen += 1
        return manifest if seen == 1 else {"fixture": {}}

    monkeypatch.setattr(replay.tomllib, "loads", fake_tomllib_loads)
    monkeypatch.setattr(
        replay,
        "load_verified_yaml_mapping",
        lambda **kwargs: dict(payloads[kwargs["relative_path"].name]),
    )
    monkeypatch.setattr(
        replay,
        "read_verified_repo_file",
        lambda **kwargs: json.dumps(payloads[kwargs["relative_path"].name], sort_keys=True).encode(
            "utf-8"
        ),
        raising=False,
    )

    with pytest.raises(ValueError, match="duplicate projected_record_id"):
        replay._approved_projection_rows()
